"""
Tests for W1 abuse protection: App Attest verification, per-device daily
quota, and the global daily-spend circuit breaker.

Crypto tests build a synthetic Apple-style attestation chain (own root CA)
and inject it as the trust anchor, so the full verification path runs
without Apple hardware. Real-device attestation remains a launch gate.
"""

import base64
import hashlib
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import cbor2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.services import app_attest
from app.services.abuse_protection import (
    ChallengeStore,
    DeviceRegistry,
    QuotaTracker,
    SpendTracker,
)


# === Synthetic Apple-style attestation fixtures ===

APP_ATTEST_EXT_OID = x509.ObjectIdentifier("1.2.840.113635.100.8.2")
TEAM_ID = "TESTTEAM12"
BUNDLE_ID = "com.wineshelfscanner.app"
APP_ID = f"{TEAM_ID}.{BUNDLE_ID}"


def _make_cert(subject_name, issuer_name, public_key, signing_key, *, is_ca,
               extra_extensions=()):
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_name)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
    )
    for ext, critical in extra_extensions:
        builder = builder.add_extension(ext, critical=critical)
    return builder.sign(signing_key, hashes.SHA256())


class FakeAppleCA:
    """A self-made root + intermediate standing in for Apple's App Attest CA."""

    def __init__(self):
        self.root_key = ec.generate_private_key(ec.SECP384R1())
        self.root_cert = _make_cert(
            "Fake App Attestation Root CA", "Fake App Attestation Root CA",
            self.root_key.public_key(), self.root_key, is_ca=True,
        )
        self.intermediate_key = ec.generate_private_key(ec.SECP256R1())
        self.intermediate_cert = _make_cert(
            "Fake App Attestation CA 1", "Fake App Attestation Root CA",
            self.intermediate_key.public_key(), self.root_key, is_ca=True,
        )

    @property
    def root_pem(self) -> str:
        return self.root_cert.public_bytes(serialization.Encoding.PEM).decode()

    def issue_leaf(self, device_public_key, nonce: bytes):
        # Apple wraps the nonce in a DER SEQUENCE in extension
        # OID 1.2.840.113635.100.8.2; the verifier extracts the 32 bytes.
        der_value = b"\x30\x24\xa1\x22\x04\x20" + nonce  # SEQ > [1] > OCTET STRING(32)
        ext = x509.UnrecognizedExtension(APP_ATTEST_EXT_OID, der_value)
        return _make_cert(
            "Fake leaf", "Fake App Attestation CA 1",
            device_public_key, self.intermediate_key, is_ca=False,
            extra_extensions=[(ext, False)],
        )


def _key_id(device_public_key) -> bytes:
    point = device_public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return hashlib.sha256(point).digest()


def _auth_data(app_id: str, counter: int, aaguid: bytes, credential_id: bytes) -> bytes:
    rp_hash = hashlib.sha256(app_id.encode()).digest()
    flags = b"\x40"  # attested credential data present
    count = counter.to_bytes(4, "big")
    cred_len = len(credential_id).to_bytes(2, "big")
    cose_key = b"\xa0"  # empty CBOR map placeholder; verifier doesn't parse it
    return rp_hash + flags + count + aaguid + cred_len + credential_id + cose_key


def make_attestation(ca: FakeAppleCA, challenge: bytes, *,
                     app_id: str = APP_ID,
                     aaguid: bytes = app_attest.AAGUID_PRODUCTION,
                     counter: int = 0,
                     tamper_key_id: bytes | None = None):
    """Returns (attestation_cbor_bytes, key_id_bytes, device_key)."""
    device_key = ec.generate_private_key(ec.SECP256R1())
    key_id = tamper_key_id or _key_id(device_key.public_key())
    auth_data = _auth_data(app_id, counter, aaguid, key_id)
    nonce = hashlib.sha256(auth_data + hashlib.sha256(challenge).digest()).digest()
    leaf = ca.issue_leaf(device_key.public_key(), nonce)
    attestation = cbor2.dumps({
        "fmt": "apple-appattest",
        "attStmt": {
            "x5c": [
                leaf.public_bytes(serialization.Encoding.DER),
                ca.intermediate_cert.public_bytes(serialization.Encoding.DER),
            ],
            "receipt": b"",
        },
        "authData": auth_data,
    })
    return attestation, key_id, device_key


def make_assertion(device_key, client_data: bytes, counter: int,
                   app_id: str = APP_ID) -> bytes:
    rp_hash = hashlib.sha256(app_id.encode()).digest()
    auth_data = rp_hash + b"\x00" + counter.to_bytes(4, "big")
    # Real devices sign the nonce as an ECDSA-SHA256 *message* (double hash),
    # not as a prehashed digest — confirmed on hardware 2026-07-06.
    nonce = hashlib.sha256(auth_data + hashlib.sha256(client_data).digest()).digest()
    signature = device_key.sign(nonce, ec.ECDSA(hashes.SHA256()))
    return cbor2.dumps({"signature": signature, "authenticatorData": auth_data})


@pytest.fixture
def fake_ca(monkeypatch):
    ca = FakeAppleCA()
    monkeypatch.setattr(app_attest, "_root_ca_pem_override", ca.root_pem)
    return ca


# === Attestation verification ===

class TestVerifyAttestation:
    def test_valid_attestation_returns_public_key_and_counter(self, fake_ca):
        challenge = os.urandom(32)
        attestation, key_id, device_key = make_attestation(fake_ca, challenge)

        result = app_attest.verify_attestation(
            attestation, key_id, challenge, app_id=APP_ID,
        )

        assert result.counter == 0
        expected_pem = device_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        assert result.public_key_pem == expected_pem

    def test_wrong_challenge_rejected(self, fake_ca):
        attestation, key_id, _ = make_attestation(fake_ca, os.urandom(32))
        with pytest.raises(app_attest.AttestationError, match="nonce"):
            app_attest.verify_attestation(
                attestation, key_id, os.urandom(32), app_id=APP_ID,
            )

    def test_untrusted_chain_rejected(self, fake_ca):
        # Attestation issued by a DIFFERENT CA than the configured trust anchor.
        rogue = FakeAppleCA()
        challenge = os.urandom(32)
        attestation, key_id, _ = make_attestation(rogue, challenge)
        with pytest.raises(app_attest.AttestationError, match="chain"):
            app_attest.verify_attestation(
                attestation, key_id, challenge, app_id=APP_ID,
            )

    def test_key_id_mismatch_rejected(self, fake_ca):
        challenge = os.urandom(32)
        attestation, _, _ = make_attestation(
            fake_ca, challenge, tamper_key_id=os.urandom(32),
        )
        with pytest.raises(app_attest.AttestationError, match="key"):
            app_attest.verify_attestation(
                attestation, os.urandom(32), challenge, app_id=APP_ID,
            )

    def test_wrong_app_id_rejected(self, fake_ca):
        challenge = os.urandom(32)
        attestation, key_id, _ = make_attestation(fake_ca, challenge)
        with pytest.raises(app_attest.AttestationError, match="app"):
            app_attest.verify_attestation(
                attestation, key_id, challenge, app_id="OTHERTEAM0.com.other.app",
            )

    def test_development_aaguid_rejected_by_default(self, fake_ca):
        challenge = os.urandom(32)
        attestation, key_id, _ = make_attestation(
            fake_ca, challenge, aaguid=app_attest.AAGUID_DEVELOPMENT,
        )
        with pytest.raises(app_attest.AttestationError, match="environment"):
            app_attest.verify_attestation(
                attestation, key_id, challenge, app_id=APP_ID,
            )

    def test_development_aaguid_allowed_when_opted_in(self, fake_ca):
        challenge = os.urandom(32)
        attestation, key_id, _ = make_attestation(
            fake_ca, challenge, aaguid=app_attest.AAGUID_DEVELOPMENT,
        )
        result = app_attest.verify_attestation(
            attestation, key_id, challenge, app_id=APP_ID, allow_development=True,
        )
        assert result.counter == 0

    def test_nonzero_counter_rejected(self, fake_ca):
        challenge = os.urandom(32)
        attestation, key_id, _ = make_attestation(fake_ca, challenge, counter=7)
        with pytest.raises(app_attest.AttestationError, match="counter"):
            app_attest.verify_attestation(
                attestation, key_id, challenge, app_id=APP_ID,
            )


# === Assertion verification ===

class TestVerifyAssertion:
    def _registered_key(self, fake_ca):
        challenge = os.urandom(32)
        attestation, key_id, device_key = make_attestation(fake_ca, challenge)
        result = app_attest.verify_attestation(
            attestation, key_id, challenge, app_id=APP_ID,
        )
        return device_key, result.public_key_pem

    def test_valid_assertion_returns_new_counter(self, fake_ca):
        device_key, pem = self._registered_key(fake_ca)
        client_data = os.urandom(32)
        assertion = make_assertion(device_key, client_data, counter=1)

        new_counter = app_attest.verify_assertion(
            assertion, client_data, pem, app_id=APP_ID, last_counter=0,
        )
        assert new_counter == 1

    def test_bad_signature_rejected(self, fake_ca):
        device_key, pem = self._registered_key(fake_ca)
        other_key = ec.generate_private_key(ec.SECP256R1())
        assertion = make_assertion(other_key, b"data", counter=1)
        with pytest.raises(app_attest.AttestationError, match="signature"):
            app_attest.verify_assertion(
                assertion, b"data", pem, app_id=APP_ID, last_counter=0,
            )

    def test_stale_counter_rejected(self, fake_ca):
        device_key, pem = self._registered_key(fake_ca)
        assertion = make_assertion(device_key, b"data", counter=3)
        with pytest.raises(app_attest.AttestationError, match="counter"):
            app_attest.verify_assertion(
                assertion, b"data", pem, app_id=APP_ID, last_counter=3,
            )

    def test_wrong_rp_id_rejected(self, fake_ca):
        device_key, pem = self._registered_key(fake_ca)
        assertion = make_assertion(device_key, b"data", counter=1,
                                   app_id="OTHERTEAM0.com.other.app")
        with pytest.raises(app_attest.AttestationError, match="app"):
            app_attest.verify_assertion(
                assertion, b"data", pem, app_id=APP_ID, last_counter=0,
            )


# === Stores / trackers ===

class TestChallengeStore:
    def test_issue_and_consume_once(self):
        store = ChallengeStore(ttl_seconds=60)
        challenge = store.issue()
        assert store.consume(challenge) is True
        assert store.consume(challenge) is False  # single use

    def test_expired_challenge_rejected(self):
        store = ChallengeStore(ttl_seconds=-1)
        challenge = store.issue()
        assert store.consume(challenge) is False

    def test_unknown_challenge_rejected(self):
        store = ChallengeStore(ttl_seconds=60)
        assert store.consume(base64.b64encode(os.urandom(32)).decode()) is False


class TestQuotaTracker:
    def test_increments_per_device_per_day(self, tmp_path):
        tracker = QuotaTracker(str(tmp_path / "q.db"))
        assert tracker.increment("device-a") == 1
        assert tracker.increment("device-a") == 2
        assert tracker.increment("device-b") == 1

    def test_days_are_isolated(self, tmp_path):
        tracker = QuotaTracker(str(tmp_path / "q.db"))
        assert tracker.increment("device-a", day="2026-07-04") == 1
        assert tracker.increment("device-a", day="2026-07-05") == 1


class TestSpendTracker:
    def test_accumulates_today(self, tmp_path):
        tracker = SpendTracker(str(tmp_path / "s.db"))
        tracker.add(0.02)
        tracker.add(0.03)
        assert tracker.today_total() == pytest.approx(0.05)

    def test_other_days_do_not_count(self, tmp_path):
        tracker = SpendTracker(str(tmp_path / "s.db"))
        tracker.add(5.0, day="2026-01-01")
        assert tracker.today_total() == pytest.approx(0.0)


class TestDeviceRegistry:
    def test_register_get_update(self, tmp_path):
        reg = DeviceRegistry(str(tmp_path / "d.db"))
        reg.register("kid1", "PEM", 0)
        device = reg.get("kid1")
        assert device.public_key_pem == "PEM"
        assert device.counter == 0
        reg.update_counter("kid1", 5)
        assert reg.get("kid1").counter == 5
        assert reg.get("missing") is None


# === Route-level enforcement ===

def _png_upload():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (90, 30, 30)).save(buf, format="PNG")
    buf.seek(0)
    return {"image": ("test.png", buf, "image/png")}


@pytest.fixture
def enforcing_client(monkeypatch, fake_ca, tmp_path):
    """TestClient with APP_ATTEST_ENFORCE=require and isolated protection DB."""
    monkeypatch.setenv("APP_ATTEST_ENFORCE", "require")
    monkeypatch.setenv("APPLE_TEAM_ID", TEAM_ID)
    monkeypatch.setenv("DEVICE_DAILY_SCAN_LIMIT", "2")
    monkeypatch.setenv("ABUSE_PROTECTION_DB", str(tmp_path / "abuse.db"))
    import app.routes.scan as scan_route
    from app.services import abuse_protection
    abuse_protection.reset_singletons_for_tests()
    from main import app
    yield TestClient(app)
    abuse_protection.reset_singletons_for_tests()


def _register_device(client, fake_ca):
    challenge_b64 = client.post("/device/challenge").json()["challenge"]
    challenge = base64.b64decode(challenge_b64)
    attestation, key_id, device_key = make_attestation(fake_ca, challenge)
    resp = client.post("/device/register", json={
        "key_id": base64.b64encode(key_id).decode(),
        "attestation": base64.b64encode(attestation).decode(),
        "challenge": challenge_b64,
    })
    assert resp.status_code == 204, resp.text
    return key_id, device_key


def _attest_headers(client, key_id, device_key, counter):
    challenge_b64 = client.post("/device/challenge").json()["challenge"]
    assertion = make_assertion(
        device_key, base64.b64decode(challenge_b64), counter=counter,
    )
    return {
        "X-Attest-Key-Id": base64.b64encode(key_id).decode(),
        "X-Attest-Assertion": base64.b64encode(assertion).decode(),
        "X-Attest-Challenge": challenge_b64,
    }


class TestScanEnforcement:
    def test_unattested_scan_rejected_401(self, enforcing_client):
        resp = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(),
        )
        assert resp.status_code == 401

    def test_registered_device_with_assertion_passes(self, enforcing_client, fake_ca):
        key_id, device_key = _register_device(enforcing_client, fake_ca)
        headers = _attest_headers(enforcing_client, key_id, device_key, counter=1)
        resp = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(), headers=headers,
        )
        assert resp.status_code == 200, resp.text

    def test_invalid_assertion_rejected_403(self, enforcing_client, fake_ca):
        key_id, _ = _register_device(enforcing_client, fake_ca)
        rogue_key = ec.generate_private_key(ec.SECP256R1())
        headers = _attest_headers(enforcing_client, key_id, rogue_key, counter=1)
        resp = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(), headers=headers,
        )
        assert resp.status_code == 403

    def test_challenge_replay_rejected(self, enforcing_client, fake_ca):
        key_id, device_key = _register_device(enforcing_client, fake_ca)
        headers = _attest_headers(enforcing_client, key_id, device_key, counter=1)
        first = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(), headers=headers,
        )
        assert first.status_code == 200
        # Same challenge + a fresh valid assertion over it: still rejected.
        headers["X-Attest-Assertion"] = base64.b64encode(make_assertion(
            device_key, base64.b64decode(headers["X-Attest-Challenge"]), counter=2,
        )).decode()
        replay = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(), headers=headers,
        )
        assert replay.status_code == 403

    def test_quota_exceeded_returns_429(self, enforcing_client, fake_ca):
        key_id, device_key = _register_device(enforcing_client, fake_ca)
        for counter in (1, 2):  # DEVICE_DAILY_SCAN_LIMIT=2
            headers = _attest_headers(enforcing_client, key_id, device_key, counter)
            assert enforcing_client.post(
                "/scan?mock_scenario=full_shelf", files=_png_upload(), headers=headers,
            ).status_code == 200
        headers = _attest_headers(enforcing_client, key_id, device_key, counter=3)
        resp = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(), headers=headers,
        )
        assert resp.status_code == 429

    def test_scan_stream_unattested_rejected_401(self, enforcing_client, monkeypatch):
        """/scan/stream is a paid endpoint too — same enforcement dependency."""
        monkeypatch.setenv("PIPELINE_MODE", "detect_read")
        resp = enforcing_client.post("/scan/stream", files=_png_upload())
        assert resp.status_code == 401

    def test_web_client_secret_passes(self, enforcing_client, monkeypatch):
        monkeypatch.setenv("API_CLIENT_SECRET", "vercel-proxy-secret")
        resp = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(),
            headers={"X-Api-Client-Secret": "vercel-proxy-secret",
                     "X-Device-Id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200

    def test_wrong_web_secret_rejected(self, enforcing_client, monkeypatch):
        monkeypatch.setenv("API_CLIENT_SECRET", "vercel-proxy-secret")
        resp = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(),
            headers={"X-Api-Client-Secret": "wrong"},
        )
        assert resp.status_code == 401

    def test_spend_breaker_trips_503(self, enforcing_client, fake_ca, monkeypatch):
        monkeypatch.setenv("DAILY_SPEND_LIMIT_USD", "10")
        from app.services.abuse_protection import get_spend_tracker
        get_spend_tracker().add(10.01)
        key_id, device_key = _register_device(enforcing_client, fake_ca)
        headers = _attest_headers(enforcing_client, key_id, device_key, counter=1)
        resp = enforcing_client.post(
            "/scan?mock_scenario=full_shelf", files=_png_upload(), headers=headers,
        )
        assert resp.status_code == 503


class TestScanEnforcementOff:
    """Default mode: everything works exactly as before (no headers needed)."""

    def test_scan_needs_no_headers_when_off(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APP_ATTEST_ENFORCE", raising=False)
        monkeypatch.setenv("ABUSE_PROTECTION_DB", str(tmp_path / "abuse.db"))
        from app.services import abuse_protection
        abuse_protection.reset_singletons_for_tests()
        from main import app
        client = TestClient(app)
        resp = client.post("/scan?mock_scenario=full_shelf", files=_png_upload())
        assert resp.status_code == 200
        abuse_protection.reset_singletons_for_tests()
