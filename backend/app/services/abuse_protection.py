"""
Abuse protection state + /scan enforcement dependency (W1).

Three layers, cheapest first:
  1. Global daily-spend circuit breaker — trips /scan to 503 when aggregate
     estimated Vision+LLM spend for the UTC day exceeds DAILY_SPEND_LIMIT_USD.
  2. Identity — one of: a verified App Attest assertion (iOS, account-less),
     or the server-side web proxy secret (X-Api-Client-Secret, for the
     Next.js server route which cannot do App Attest). Enforcement mode via
     APP_ATTEST_ENFORCE: "off" (default; dev/tests), "log" (observe, admit
     unattested callers), "require" (401 without a valid credential).
  3. Per-device daily quota — DEVICE_DAILY_SCAN_LIMIT scans/day per identity
     (429 above it). A *safety* cap, distinct from the 5/month monetization
     limit which is client-side.

State lives in a dedicated SQLite file (ABUSE_PROTECTION_DB, defaults next
to wines.db). Deliberately NOT in wines.db / Alembic: wines.db is re-downloaded
from GCS on cold start, so operational counters don't belong in it. State is
per-instance — service.yaml pins maxScale so per-instance == global. The
upgrade path at real scale is Redis/Firestore, not more SQLite.
"""

import base64
import logging
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

from ..config import Config
from . import app_attest

logger = logging.getLogger(__name__)


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


class ChallengeStore:
    """In-memory, single-use, TTL-bound challenges for attest/assert flows."""

    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds
        self._challenges: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self) -> str:
        challenge = base64.b64encode(secrets.token_bytes(32)).decode()
        with self._lock:
            self._challenges[challenge] = time.monotonic() + self._ttl
            # Opportunistic cleanup keeps the dict bounded.
            if len(self._challenges) > 10_000:
                now = time.monotonic()
                self._challenges = {c: t for c, t in self._challenges.items() if t > now}
        return challenge

    def consume(self, challenge: str) -> bool:
        with self._lock:
            expiry = self._challenges.pop(challenge, None)
        return expiry is not None and expiry > time.monotonic()


@dataclass
class AttestedDevice:
    key_id: str
    public_key_pem: str
    counter: int


class DeviceRegistry:
    """Attested device keys (key_id → public key + assertion counter)."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        with _connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS attested_devices (
                       key_id TEXT PRIMARY KEY,
                       public_key_pem TEXT NOT NULL,
                       counter INTEGER NOT NULL,
                       created_at TEXT NOT NULL,
                       last_seen TEXT NOT NULL
                   )"""
            )

    def register(self, key_id: str, public_key_pem: str, counter: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO attested_devices
                       (key_id, public_key_pem, counter, created_at, last_seen)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key_id) DO UPDATE SET
                       public_key_pem = excluded.public_key_pem,
                       counter = excluded.counter,
                       last_seen = excluded.last_seen""",
                (key_id, public_key_pem, counter, now, now),
            )

    def get(self, key_id: str) -> Optional[AttestedDevice]:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT key_id, public_key_pem, counter FROM attested_devices"
                " WHERE key_id = ?", (key_id,),
            ).fetchone()
        if row is None:
            return None
        return AttestedDevice(row["key_id"], row["public_key_pem"], row["counter"])

    def update_counter(self, key_id: str, counter: int) -> None:
        with _connect(self._db_path) as conn:
            conn.execute(
                "UPDATE attested_devices SET counter = ?, last_seen = ? WHERE key_id = ?",
                (counter, datetime.now(timezone.utc).isoformat(), key_id),
            )


class QuotaTracker:
    """Per-identity daily scan counts."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        with _connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS device_scan_counts (
                       device_key TEXT NOT NULL,
                       day TEXT NOT NULL,
                       count INTEGER NOT NULL,
                       PRIMARY KEY (device_key, day)
                   )"""
            )

    def increment(self, device_key: str, day: Optional[str] = None) -> int:
        day = day or _utc_day()
        with _connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO device_scan_counts (device_key, day, count)
                   VALUES (?, ?, 1)
                   ON CONFLICT(device_key, day) DO UPDATE SET count = count + 1""",
                (device_key, day),
            )
            row = conn.execute(
                "SELECT count FROM device_scan_counts WHERE device_key = ? AND day = ?",
                (device_key, day),
            ).fetchone()
        return row["count"]


class SpendTracker:
    """Aggregate estimated spend per UTC day."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        with _connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS daily_spend (
                       day TEXT PRIMARY KEY,
                       usd REAL NOT NULL
                   )"""
            )

    def add(self, usd: float, day: Optional[str] = None) -> None:
        if usd <= 0:
            return
        day = day or _utc_day()
        with _connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO daily_spend (day, usd) VALUES (?, ?)
                   ON CONFLICT(day) DO UPDATE SET usd = usd + excluded.usd""",
                (day, usd),
            )

    def today_total(self) -> float:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT usd FROM daily_spend WHERE day = ?", (_utc_day(),),
            ).fetchone()
        return row["usd"] if row else 0.0


# === Singletons ===

def _db_path() -> str:
    default = str(Path(Config.database_path()).parent / "abuse_protection.db")
    return os.getenv("ABUSE_PROTECTION_DB", default)


@lru_cache(maxsize=1)
def get_challenge_store() -> ChallengeStore:
    return ChallengeStore()


@lru_cache(maxsize=1)
def get_device_registry() -> DeviceRegistry:
    return DeviceRegistry(_db_path())


@lru_cache(maxsize=1)
def get_quota_tracker() -> QuotaTracker:
    return QuotaTracker(_db_path())


@lru_cache(maxsize=1)
def get_spend_tracker() -> SpendTracker:
    return SpendTracker(_db_path())


def reset_singletons_for_tests() -> None:
    get_challenge_store.cache_clear()
    get_device_registry.cache_clear()
    get_quota_tracker.cache_clear()
    get_spend_tracker.cache_clear()


# === /scan enforcement dependency ===

def _verify_attest_headers(request: Request) -> str:
    """Verify App Attest headers; returns the device identity key.

    Raises HTTPException 403 on any verification failure — a genuine client
    never sends invalid credentials, so failures are rejected in every mode.
    """
    key_id_b64 = request.headers["x-attest-key-id"]
    assertion_b64 = request.headers["x-attest-assertion"]
    challenge_b64 = request.headers["x-attest-challenge"]

    if not get_challenge_store().consume(challenge_b64):
        raise HTTPException(status_code=403, detail="Unknown or expired challenge")

    device = get_device_registry().get(key_id_b64)
    if device is None:
        raise HTTPException(
            status_code=403, detail="Unknown device key; register via /device/register"
        )
    try:
        new_counter = app_attest.verify_assertion(
            base64.b64decode(assertion_b64),
            base64.b64decode(challenge_b64),
            device.public_key_pem,
            app_id=Config.app_attest_app_id(),
            last_counter=device.counter,
        )
    except (app_attest.AttestationError, ValueError):
        raise HTTPException(status_code=403, detail="Assertion verification failed")

    get_device_registry().update_counter(key_id_b64, new_counter)
    return f"attest:{key_id_b64}"


def enforce_abuse_protection(request: Request) -> str:
    """FastAPI dependency guarding paid endpoints. Returns the identity key."""
    # 1. Global spend circuit breaker (cheapest check, protects everything).
    limit_usd = Config.daily_spend_limit_usd()
    if limit_usd > 0:
        spent = get_spend_tracker().today_total()
        if spent >= limit_usd:
            logger.critical(
                f"SPEND BREAKER TRIPPED: ${spent:.2f} >= ${limit_usd:.2f} today — "
                f"refusing scans until UTC midnight"
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please try again later.",
            )

    mode = Config.app_attest_enforce()
    if mode == "off":
        return "unenforced"

    # 2. Identity.
    device_key: Optional[str] = None
    if "x-attest-key-id" in request.headers:
        device_key = _verify_attest_headers(request)
    elif "x-api-client-secret" in request.headers:
        expected = Config.api_client_secret()
        if not expected or not secrets.compare_digest(
            request.headers["x-api-client-secret"], expected
        ):
            raise HTTPException(status_code=401, detail="Invalid client credential")
        suffix = request.headers.get("x-device-id") or (
            request.client.host if request.client else "unknown"
        )
        device_key = f"web:{suffix}"

    if device_key is None:
        if mode == "require":
            raise HTTPException(
                status_code=401,
                detail="Device attestation required",
                headers={"WWW-Authenticate": "AppAttest"},
            )
        # mode == "log": admit, but key the quota on best-effort identity.
        suffix = request.headers.get("x-device-id") or (
            request.client.host if request.client else "unknown"
        )
        device_key = f"unattested:{suffix}"
        logger.info(f"abuse_protection: unattested scan admitted (log mode): {device_key}")

    # 3. Per-identity daily quota.
    limit = Config.device_daily_scan_limit()
    if limit > 0:
        count = get_quota_tracker().increment(device_key)
        if count > limit:
            logger.warning(
                f"abuse_protection: quota exceeded for {device_key}: {count} > {limit}"
            )
            raise HTTPException(
                status_code=429, detail="Daily scan limit reached. Try again tomorrow."
            )
    return device_key


def record_scan_spend(cost_usd: Optional[float]) -> None:
    """Accumulate a completed scan's estimated cost into the daily total."""
    if cost_usd and cost_usd > 0:
        get_spend_tracker().add(cost_usd)
