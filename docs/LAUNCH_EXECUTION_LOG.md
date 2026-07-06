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

## W0-B — detect_read verification + deploy config — ✅ verified locally (2026-07-05)

- Live e2e against the local detect_read server (:8000): wine1.jpeg → 5 DB-matched results,
  `scan_quality: null`; badges rendered onto the photo land on the correct bottles
  (Crimson Ranch, Les Plants Nobles/Ropiteau, Vennstone, Willametter, Elouan — 0 swaps,
  1 un-badged bottle = the known coverage gap, not a misplacement).
- `service.yaml` updated on `launch-w1`: `PIPELINE_MODE=detect_read`, `DEBUG_MODE=false`,
  `maxScale=1` (makes per-instance quota/spend state exact), W1 env vars.
- `anthropic-api-key` secret confirmed populated (2 enabled versions, project wine-shelf-scanner).
- Prod URL alive; measured **~80s cold start** on /health (quantifies the W3 warmup need).
- Deploy itself: pending the deploy gate (see bottom).

## W0-i — iOS compile + localizations — ✅ DONE (merged as `1f0eb68`)

- pbxproj wired: `CornerBracketsView.swift` (the compile blocker), all orphaned test suites
  (ConfigTests, FeedbackServiceTests, ScanAPIClientTests, ScanViewModelTests, TestFixtures,
  new LocalizationTests), 3 UI-test files, and a 10-locale `Localizable.strings` variant group
  (10 lproj dirs exist on disk, not the 11 the plan assumed) + `knownRegions`.
- `Debug.xcconfig` trailing-space bug fixed; API_BASE_URL now deterministic:
  Debug → `http://localhost:8000`, Release → prod (verified in both built bundles).
- `ScanViewModel.debugMode` now `#if DEBUG` gated — off in Release. Release build compiles.
- **Verified:** `xcodebuild build` (Debug + Release) succeed; unit-test target
  **115/115 passed** (first run surfaced 24 failures — mock-injection and flag-routing
  issues in never-before-run tests — all fixed); localization proven via bundle contents +
  a passing runtime NSLocalizedString test + simulator screenshot (no raw keys).
- Machine caveats found: Xcode 26.5 needed `simctl runtime match set` to pair with the
  installed iOS 26.0 runtime; **host disk nearly full (~434 MiB free)** → simulator boot
  flakiness. UI-test suite has pre-existing logic failures (accessibility identifiers
  propagate onto child buttons; tests assume idle state but offline-cache restores results) —
  product-side work, reported not fixed.

## W1 — App Attest + quota + spend breaker — ✅ backend complete (commit `6f09eac`, branch `launch-w1`)

- Full App Attest attestation + assertion verification (cbor2 + cryptography; Apple root CA
  fetched from apple.com this session). Synthetic-CA injection means the entire crypto path is
  unit-tested; **real-device attestation is a human gate** (needs Apple Developer Team ID).
- `/device/challenge` + `/device/register`; `/scan` gains `enforce_abuse_protection`
  (modes off/log/require) + per-scan cost recording.
- **Live load-test proof** (server booted from the branch): scripted caller with
  `DEVICE_DAILY_SCAN_LIMIT=3` → `200,200,200,429,429,429`; fresh device → 200 (isolation);
  spend injected past `DAILY_SPEND_LIMIT_USD` → next scan `503`. Route tests cover
  `require`-mode 401 and challenge replay 403.
- 29 new tests; full backend suite in the worktree: **318 passed, 0 failed**.
- Deployment posture: `APP_ATTEST_ENFORCE=log` initially — the Next.js webapp calls /scan
  from the browser and cannot attest. Quota + breaker are active in log mode. Flip to
  `require` once (a) iOS ships attestation and (b) the webapp moves behind a Vercel proxy
  using `API_CLIENT_SECRET` (documented for the webapp/rollout session).
- W4 server piece also on `launch-w1` (commit `5e8f2be`): `GET /config` returns
  `feature_subscription` (env-flippable on Cloud Run — paywall activates without resubmission).

## W2-i — iOS input-quality UX — ✅ DONE (merged `19b129d`)

`ScanQuality` parsing (additive, older-server safe); guided-retake "Too far away" screen
replaces the fallback path when the backend gate fires (same copy as the webapp, 10 locales);
non-blocking <2MP pre-upload warning with "Scan Anyway". 12 new tests.

## W3 — Staged waiting UX + warmup — ✅ DONE (merged `19b129d`)

Pure `ScanProgressModel.stage(forElapsed:)` — "Finding bottles…" → "Reading labels…" →
"Ranking picks…" + reassurance line at 25s, TimelineView-driven, 10 locales.
`WarmupService.ping()` fires GET /health on scene-active (hides the Cloud Run wake-up).
10 new tests. (Staged-UI screenshot not capturable: mock scans resolve in 0.1s and UI
automation is broken on this host — the pure-function tests are the verification.)

## W4 — Monthly reset, .storekit, remote paywall flag — ✅ DONE (merged `19b129d`)

ScanCounter is now per-calendar-month (period key + injectable clock; 9 tests incl. month/yr
boundaries). `WineShelfScanner.storekit` with the two products, wired into the scheme —
**verified with a real SKTestSession**: SubscriptionManager loads both products with correct
names/prices. `RemoteFlagsService` fetches GET /config on launch and overrides
`feature_subscription`; failures leave the persisted state untouched. 6 tests.
iOS `AppAttestManager` (W1 client): registers + asserts per scan, all failures degrade to an
unattested scan (server admits in log mode); scan-403 clears registration for self-heal;
11 tests. **All 164 unit tests pass — independently re-run by the session lead.**

## Human gates (exact asks)

1. **Apple Developer Program / Team ID** — ✅ MOSTLY CLOSED (2026-07-05 evening): owner enrolled,
   Team ID `3STS9R446B` wired into all 6 Xcode config blocks + App Attest entitlement
   (production) + `APPLE_TEAM_ID`/`APP_ATTEST_ALLOW_DEV=true` deployed to Cloud Run (PR #55,
   deploy verified: `/device/register` now answers 403 unknown-challenge, not 503
   not-configured). **Remaining:** sign into Xcode with the Apple ID, run on a physical
   iPhone once to confirm Apple's real attestation chain verifies; flip
   `APP_ATTEST_ALLOW_DEV=false` at public launch.
2. **App Store Connect products** — ✅ CREATED by owner (2026-07-05 evening): app record
   ("Wine Shelf Scanner", `com.wineshelfscanner.app`, iOS only) + subscription group "Pro"
   with `com.wineshelfscanner.monthly` $4.99/mo and `.annual` $29.99/yr, matching the
   hardcoded product IDs. **Remaining:** review screenshot per subscription (paywall
   screenshot, can be produced from the simulator) and submitting them with the v1 binary.
3. **Liquor-store photo trip (W2-A)** — ≥20 device-quality shelf photos (24MP iPhone,
   close range) from real stores, for the held-out accuracy re-proof
   (gate: badge precision ≥ 90%, swap ≤ 2%, coverage ≥ 60%). The eval harness is ready;
   current evidence is 2 device-quality images / 43 bottles + the rollout session's
   confirmatory run on repo images (stream 6, in flight).
4. **Webapp proxy secret (before flipping APP_ATTEST_ENFORCE=require)** — move the Next.js
   scan calls behind a server-side route that adds `X-Api-Client-Secret`, set
   `API_CLIENT_SECRET` on Cloud Run + Vercel. Until then prod runs `log` mode
   (quota + spend breaker active; attestation optional).

## Deploy — ✅ LIVE (2026-07-05)

The owner exercised the rollout plan's sign-off gate: PR #51 and follow-up #52
(rating-overlays → main, containing all backend W0/W1/W2/W4-server work merged by this
session plus the rollout session's streams) were merged; the GitHub Actions **Deploy
workflow succeeded**. The gate conflict noted at the top of this log resolved itself —
the owner merged, so no unilateral deploy decision was needed from this session.

**Production smoke test (this session, post-deploy):**
- `GET /health` → healthy (warm instance, minScale=1).
- `GET /config` → `{"feature_subscription": false}` — W4 remote paywall flag live, off.
- `POST /device/challenge` → issues challenges — W1 endpoints live.
- `POST /scan` (wine1.jpeg, unattested with X-Device-Id, log mode) → **6 detect_read
  results in 7.6s** (correct wines incl. one the local run missed; `scan_quality: null`).
  Quota + spend breaker armed (40/day/identity, $25/day global).
- Stream 6 (rollout session) independently confirmed accuracy on an unseen 24.5MP device
  photo: badge precision .941, 0 swaps, coverage .762, $0.0285/scan.
