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

## W2-i — iOS pre-upload quality check — pending

## W3 — Staged waiting UX + warmup — pending

## W4 — Monthly reset, .storekit, remote paywall flag — pending

## Human gates (exact asks)

1. **Apple Developer Program / Team ID** — needed for: `DEVELOPMENT_TEAM` in the Xcode project
   (signing, W5), `APPLE_TEAM_ID` env on Cloud Run (App Attest verification; `/device/register`
   returns 503 until set), and real-device App Attest verification (the crypto is fully
   unit-tested against a synthetic CA; one TestFlight/device run must confirm Apple's real
   chain verifies — then flip nothing, it's already wired).
2. **App Store Connect products** — create ONE auto-renewable subscription group ("Pro") with:
   `com.wineshelfscanner.monthly` — $4.99/month, display name "Monthly";
   `com.wineshelfscanner.annual` — $29.99/year, display name "Annual" ("SAVE 50%" framing is
   client-side). Submit them **with** the v1 binary. The local `.storekit` file mirrors these
   for pre-ASC testing.
3. **Liquor-store photo trip (W2-A)** — ≥20 device-quality shelf photos (24MP iPhone,
   close range) from real stores, for the held-out accuracy re-proof
   (gate: badge precision ≥ 90%, swap ≤ 2%, coverage ≥ 60%). The eval harness is ready;
   current evidence is 2 device-quality images / 43 bottles + the rollout session's
   confirmatory run on repo images (stream 6, in flight).
4. **Webapp proxy secret (before flipping APP_ATTEST_ENFORCE=require)** — move the Next.js
   scan calls behind a server-side route that adds `X-Api-Client-Secret`, set
   `API_CLIENT_SECRET` on Cloud Run + Vercel. Until then prod runs `log` mode
   (quota + spend breaker active; attestation optional).

## Deploy — blocked on W0-B + W1 + gate-conflict resolution
