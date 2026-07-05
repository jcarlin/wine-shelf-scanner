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

## Stream 1 — Progressive rendering (SSE)

_(pending)_

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

_(pending)_

## Stream 4 — Error UX

_(pending)_

## Stream 5 — Deploy (gated)

_(pending — nothing reaches production before the owner gate)_

## Stream 6 — Confirmatory accuracy run

_(pending)_
