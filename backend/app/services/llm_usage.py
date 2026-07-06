"""
Per-LLM-call token usage logging.

Emits one structured `event=llm_usage` record per successful multimodal call:
  - Always to stdout via `logger.info(json.dumps(record))` so Cloud Run's
    Cloud Logging captures it as a queryable jsonPayload in production.
  - Optionally appended to a local JSONL file when `log_path` is non-empty,
    so during development Claude / a human can `cat | jq` the file directly.

Concurrency: a single `f.write(line + "\n")` is atomic on POSIX local
filesystems for payloads under PIPE_BUF (4096 bytes); records are ~300
bytes, so no lock is needed. Cross-process ordering is not guaranteed —
that's fine for an audit log.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# Prices in USD per 1M tokens. Sourced 2026-05-02 from:
#   - https://www.anthropic.com/pricing#api
#   - https://ai.google.dev/pricing
# Refresh manually when costs drift.
_PRICES: dict[str, dict[str, float]] = {
    "anthropic/claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00, "cache_read": 0.30},
    "anthropic/claude-opus-4-7":           {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    "anthropic/claude-haiku-4-5-20251001": {"input": 1.00,  "output": 5.00,  "cache_read": 0.10},
    # Claude 5 family / Opus 4.8 (rates from litellm.model_cost, 2026-07-04)
    "anthropic/claude-sonnet-5":           {"input": 2.00,  "output": 10.00, "cache_read": 0.20},
    "anthropic/claude-opus-4-8":           {"input": 5.00,  "output": 25.00, "cache_read": 0.50},
    "gemini/gemini-2.5-pro":               {"input": 1.25,  "output": 5.00,  "cache_read": 0.31},
}


def compute_cost_usd(
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    cached_tokens: Optional[int],
) -> Optional[float]:
    """
    Compute USD cost for a single LLM call.

    Returns None if the model is not in `_PRICES` so analytics can filter
    `WHERE estimated_cost_usd IS NOT NULL` instead of summing zeros.

    Provider semantics: `prompt_tokens` from Anthropic/litellm includes
    cached tokens; subtract before applying the input rate so cached reads
    aren't billed twice.
    """
    rates = _PRICES.get(model)
    if rates is None:
        return None
    cached = cached_tokens or 0
    billable_input = max(0, (prompt_tokens or 0) - cached)
    return round(
        (billable_input              * rates["input"]      / 1_000_000)
      + (cached                       * rates["cache_read"] / 1_000_000)
      + ((completion_tokens or 0)    * rates["output"]     / 1_000_000),
        6,
    )


def log_usage(
    *,
    image_id: str,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    cached_tokens: Optional[int],
    latency_ms: int,
    truncated: bool,
    log_path: str,
) -> None:
    """
    Emit one usage record to stdout (always) and to `log_path` (if non-empty).
    """
    now = datetime.now(timezone.utc)
    record = {
        "event": "llm_usage",
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "image_id": image_id,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "latency_ms": latency_ms,
        "estimated_cost_usd": compute_cost_usd(
            model, prompt_tokens, completion_tokens, cached_tokens
        ),
        "truncated": truncated,
    }

    line = json.dumps(record, separators=(",", ":"))
    logger.info(line)

    if log_path:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
