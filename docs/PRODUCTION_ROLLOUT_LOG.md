# Production Rollout Log — Detect+Read goes live

**Purpose:** discharge the CONDITIONAL GO conditions from `FEASIBILITY_VERDICT.md` and ship the
webapp to production. One entry per work stream: what changed, how it was verified, what's next.
If the session restarts, this file is the resume state.

**Branch:** `rating-overlays` (PR #51 → main). **Gate:** owner sign-off required once, before
anything reaches production (merge = deploy via `.github/workflows/deploy.yml`).

Streams: (1) progressive rendering (SSE), (2) input-quality gate, (3) rate limiting,
(4) error UX, (5) gated deploy, (6) confirmatory accuracy run on never-tuned repo images.

---

## Session setup (2026-07-05)

- Local servers: backend `cd backend && make watch` (:8000, healthy), frontend
  `cd nextjs && PATH=~/.nvm/versions/node/v22.18.0/bin:$PATH npm run dev` (:3000).
- **Fixed local-only webapp outage:** Next.js dev returned 404 on `/` and every locale route
  despite a clean git tree (middleware rewrote `/` → `/en` correctly; router still 404'd).
  Root cause: corrupt Turbopack dev cache in `nextjs/.next/dev` from a prior session.
  Fix: `rm -rf nextjs/.next`, restart. No code change. Verified: `/` returns 200, app renders
  in Playwright.
- Stream-6 image inventory (measured with PIL): `IMG_8125.HEIC` 4284×5712 (24.5MP, device photo),
  `wine-photos.jpg` 1300×1001 (1.3MP), `corpus/shelves/wine-bottles-display-om-...copenhagen...jpg`
  1600×1153 (1.8MP). The two medium-res images need a detection-based median-bottle-width check
  against the ~140px floor before annotation effort.

## Stream 1 — Progressive rendering (SSE) ✅ (2026-07-05)

**What changed (built from scratch — the SSE endpoint CLAUDE.md described did not exist):**
- `detect_read.py`: core refactored into `run_detect_read_stream(...)`, an async generator
  yielding a cumulative `DetectReadResult` snapshot (`partial=True`) as each parallel crop-read
  chunk completes (via `asyncio.as_completed`), then the final post-rescue result.
  `run_detect_read` now just consumes the generator — `/scan` and `/scan/stream` share one
  code path, and the eval harness measures the exact shipping code.
- `DetectReadPipeline.scan_stream()`: DB-matches each snapshot; final snapshot gets the full
  usage-logging/cache treatment (identical to `scan()`).
- New route `backend/app/routes/scan_stream.py` — `POST /scan/stream`, SSE events:
  `partial` (0+, complete cumulative ScanResponse), `done` (final, identical to POST /scan),
  `error` (in-band terminal signal after streaming began). Partial snapshots skip
  enrichment/DB-sync; the final does it all. 501 unless `PIPELINE_MODE=detect_read`
  (clients fall back). `POST /scan` unchanged (iOS).
- Next.js: `scanImageStream()` in `lib/api-client.ts` (fetch + manual SSE parse; falls back to
  `POST /scan` when the endpoint is missing/unreachable; keeps the last partial if the stream
  dies mid-scan rather than discarding rendered badges), `useScanState` streams by default
  (empty partials stay on the scanning overlay), `ResultsView` shows a "Reading labels…" pill
  (translated, 10 locales) while more chunks are in flight. jsdom TextDecoder polyfill added
  to jest.setup.ts for the SSE parser tests.

**Verified:**
- TDD: 4 generator/pipeline tests + 4 route tests (backend), 4 client tests (frontend) — all
  written failing-first. Backend 312 passed (remaining failures: known perf flakes + 2
  pre-existing missing-GT-fixture); frontend 84/84 + type-check clean.
- Live SSE timing (curl-level, wine1.jpeg): `partial` with 2 results at **7.1s**, partial
  6 results at 8.9s, `done` at 12.5s — vs 12.5s to first paint without streaming.
- Webapp E2E (Playwright, IMG_8121.HEIC 24MP, real scan): in-page sampler recorded first
  badge +22.1s, 19 badges +28.3s, done +30.4s (24MP HEIC pays upload + conversion +
  detection before the first chunk; typical-size photos hit the ~7-8s first-badge target).
  Screenshots: `rollout_stream_partial_8121.png` (1 badge + "Reading labels…" pill),
  `rollout_stream_final_8121.png` (19 badges, BEST PICK, ranks).

**Next:** none — discharges verdict condition 1 (perceived-latency mitigation shipped).

## Stream 2 — Input-quality gate ✅ (2026-07-05)

**What changed:**
- `detect_read.py`: `run_detect_read(min_bottle_px=...)` — after detection (before any LLM
  spend), computes median detected bottle width in full-res px; below the floor it returns
  early with `low_quality=True`. Param defaults to `None` so the eval harness measures ungated.
  Also fixed a ZeroDivisionError on degenerate (few-px) uploads: 2×2 tiles collapse to zero
  size; now the full frame alone covers tiny images.
- `Config.detect_read_min_bottle_px()` — env `DETECT_READ_MIN_BOTTLE_PX`, default 140, 0 disables.
- `ScanResponse.scan_quality` (new **optional, additive** field: `{status, median_bottle_px,
  bottles_detected}`) — frozen `results`/`fallback_list` contract untouched; iOS ignores
  unknown fields.
- Route: undecodable images (PIL `OSError`) now 400 instead of 500. The old
  `test_accepts_png` fixture was actually a corrupt PNG — replaced with a valid one, and a
  new `test_corrupt_image_returns_400` covers the corrupt case.
- Next.js: `LowQualityNotice` component ("Too far away / move closer / Retake Photo",
  translated in all 10 locales), rendered when `scan_quality.status === 'low_resolution'`
  and no visible results.

**Verified:**
- TDD: 8 backend tests (`tests/test_detect_read.py`) + 2 component tests, all green;
  backend suite has no regressions (remaining failures are the 2 pre-existing
  missing-GT-fixture ones); frontend 80/80 + type-check clean.
- E2E (real Vision call): 480×360 thumbnail → `scan_quality: {status: low_resolution,
  median_bottle_px: 31.0, bottles_detected: 25}`, zero LLM spend; webapp renders the retake
  screen — screenshot `backend/out/render_checks/rollout_quality_gate_lowres.png`.
- Negative control: wine1.jpeg (266px bottles) → 5 results, `scan_quality: null`.

**Next:** none — discharges verdict condition 2.

## Stream 3 — Rate limiting

**CLAIMED 2026-07-05 by the App-Store-launch session** (plan
`~/.claude/plans/you-are-an-apple-humble-owl.md`, workstream W1; execution log
`docs/LAUNCH_EXECUTION_LOG.md`). Scope expanded per that plan: account-less App Attest
verification on `/scan`, per-device daily quota (429), global daily-spend circuit breaker (503).
Work happens on worktree branch `launch-w1` and merges back here when green — please don't
start parallel rate-limiting work.

## Stream 4 — Error UX ✅ (2026-07-05)

**What changed:**
- `map_pipeline_error()` in `routes/scan.py` (shared with `/scan/stream`): litellm
  RateLimitError / InternalServerError (Anthropic 529 overloaded) / ServiceUnavailable /
  BadGateway / APIConnectionError → **503** with `Retry-After: 15` and "scanner is very busy…
  try again in a moment"; litellm/asyncio Timeout → **504** "took too long, try again";
  Google Vision `GoogleAPIError` → **503** "couldn't analyze the photo right now". Unknown
  exceptions keep the generic 500. `/scan/stream` emits the same mapped message in its
  in-band `error` event.
- Frontend `scanImage`: non-OK responses now surface the backend's `detail` message on the
  existing error screen (Try Again + Report an Issue link) instead of "Server returned 503".
  This also covers the launch-w1 session's upcoming 429s — their `detail` will render as-is.
- (From stream 2, same contract: undecodable image → 400 "Invalid or corrupted image file".)

**Verified:** 7 new backend route tests (each failure class → status/header/message,
unknown stays 500, stream error event carries mapped message) + 1 frontend test
(detail surfaced) — written failing-first, all green. Frontend 85/85, type-check clean.
The dead-end-free error screen itself (Try Again + report link) pre-existed and is unchanged.

**Next:** none for this stream. Note: retry-after isn't auto-honored client-side —
the user taps Try Again; deliberate (no silent auto-retry spend).

## Stream 5 — Deploy (gated)

**COORDINATION (from the App-Store-launch session, 2026-07-05):** stream 3 / W1 is
**code-complete and load-tested on branch `launch-w1`** (App Attest + per-device daily quota
429 + global daily-spend breaker 503; `/scan` gains `Depends(enforce_abuse_protection)`).
It merges into `rating-overlays` as soon as the tree is clean — please merge/rebase before
deploying so production never exposes the unprotected endpoint. service.yaml notes:
- **maxScale MUST be 1** while quota/spend state is per-instance SQLite (launch-w1 sets this);
  your uncommitted minScale=1 warm-instance change composes fine → `minScale=1, maxScale=1`.
- launch-w1 also sets `DEBUG_MODE=false`, `APP_ATTEST_ENFORCE=log` (webapp can't attest;
  quota+breaker still active in log mode), `DEVICE_DAILY_SCAN_LIMIT=40`,
  `DAILY_SPEND_LIMIT_USD=25`, and adds cbor2/cryptography to requirements.txt.
- `/scan/stream` needs the same dependency — the launch session adds it during the merge.
- To later flip `APP_ATTEST_ENFORCE=require`: webapp must call via a server-side proxy
  sending `API_CLIENT_SECRET`; browser-direct calls can't hold a secret.

_(nothing reaches production before the owner gate)_

## Stream 6 — Confirmatory accuracy run

_(pending)_
