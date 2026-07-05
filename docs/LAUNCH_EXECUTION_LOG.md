# App Store Launch — Execution Log (W0–W4)

**Session:** App-Store-launch critical path (plan: `~/.claude/plans/you-are-an-apple-humble-owl.md`).
**Scope this run:** W0 (green build + right pipeline live), W1 (abuse protection), W2 (input gate),
W3 (waiting UX), W4 (monetization plumbing). Human-only launch ops (signing, screenshots,
submission) are out of scope.

**Coordination note (2026-07-05):** a parallel session (swarm `session-965b1f8c`) is executing
`docs/PRODUCTION_ROLLOUT_LOG.md` on this same branch/checkout — streams 1 (SSE), 2 (input gate,
done), 6 (accuracy) are theirs. This session claims **stream 3 (rate limiting, expanded to full
W1: App Attest + per-device quota + spend breaker)** and the **entire iOS track** (untouched by
the swarm). Backend W1 work happens on an isolated worktree branch to avoid tree collisions;
iOS work likewise. Deploy (their stream 5 / my task 8) has conflicting gates — their log requires
owner sign-off; my brief authorizes merge+deploy after W0+W1 verification. Resolution recorded
below when reached.

---

## W2-B — Input-quality gate — ✅ DONE (by swarm stream 2, commit `edfc820`)

Backend `min_bottle_px` gate (140px floor, before LLM spend) + `ScanResponse.scan_quality`
(additive) + Next.js retake screen, all locales. Verified independently this session:
`pytest tests/test_detect_read.py` green, Next.js 80/80 + type-check clean; only pre-existing
failures remain (3 perf-timing flakes, 2 missing-GT real-image fixtures).
Remaining W2 pieces for this session: iOS pre-upload heuristic + retake UX (W2-i);
the ≥20-photo accuracy re-proof (W2-A) is a **human gate** (photo trip).

## W0-B — detect_read verification + deploy config — in progress

## W0-i — iOS compile + localizations — in progress (subagent, isolated worktree)

## W1 — App Attest + quota + spend breaker — in progress (this session, worktree `launch-w1`)

## W2-i — iOS pre-upload quality check — pending

## W3 — Staged waiting UX + warmup — pending

## W4 — Monthly reset, .storekit, remote paywall flag — pending

## Deploy — blocked on W0-B + W1 + gate-conflict resolution
