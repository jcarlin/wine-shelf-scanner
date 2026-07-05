# Feasibility Verdict — Rating Overlays on the Correct Bottles

**Status: FINAL (Gate 3), 2026-07-05.** Branch `rating-overlays`. Round-by-round history in
`FEASIBILITY_RUN_LOG.md`.

## The question

Is it technically and economically feasible to reliably highlight the best-rated wines on a shelf
photo — with the star landing on the right bottle — and can we prove it in the Next.js webapp?
"Correct" is defined by rendered pixels: the badge the user sees must sit on, or right next to,
the correct bottle.

**Architecture shipped:** Detect + Read, crops-primary (`PIPELINE_MODE=detect_read`;
`backend/app/services/detect_read.py` + `detect_read_pipeline.py`; tiled Google Vision boxes →
Claude Sonnet 5 reads each bottle's label from a per-bottle crop; the LLM never emits coordinates).

---

## Verdict: CONDITIONAL GO

Every accuracy bar passes on device-quality photos — the product's actual input — with **1
wrong-bottle swap in 368 held-out + iteration targets (0.3%)**. The failure mode that motivated
this investigation (ratings on the wrong bottle) is solved. Two conditions stand between this and
an unconditional GO, both owner decisions rather than open research problems:

1. **Latency: measured 12–18s e2e vs the 10s p50 bar — the only quality bar failed on
   device-class photos.** Mitigations identified and sized below.
2. **Low-resolution inputs need a product guard.** Photos ≤1.2MP (median bottle ≤80px) drop
   coverage below the bar because label text is physically illegible at that scale. An
   input-quality check ("move closer / retake") is a UX task, not a research risk.

---

## 1. Held-out accuracy (one run, no tuning after: `backend/out/bakeoff/gate3_heldout.json`)

Approved bar (Gate 1): top-3 badge precision ≥ 90% · badge precision ≥ 85% · wrong-bottle ≤ 5% ·
coverage ≥ 60% · cost ≤ $0.03/scan · latency ≤ 10s p50 / 15s p95.

| Split | n | badge prec. | top-3 | swap | coverage | $/scan | wall p50 |
|---|---|---|---|---|---|---|---|
| **All 6 held-out** | 6 | **.905 ✓** | .875 ✗ (14/16) | **.006 ✓** | .416 ✗ | **$.0209 ✓** | 12.2s ✗ |
| Without shared-store images¹ | 4 | **.923 ✓** | **1.000 ✓** (10/10) | **.000 ✓** | .457 ✗ | $.0225 ✓ | 13.0s ✗ |
| **Device-quality photos²** | 2 | **.971 ✓** | **1.000 ✓** (6/6) | **.000 ✓** | **.767 ✓** | $.0268 ✓ | 19.3s ✗ |
| Web low-res (0.8–1.2MP)³ | 4 | .850 ✓ | .800 | .008 ✓ | .288 ✗ | $.0179 | 7.2s |

¹ `heldout_es_market` shares a store/SKUs with iteration image IMG_8335; `heldout_intl_market`
with IMG_8334. Both top-3 misses in the aggregate sit on `heldout_es_market`; the fully
independent subset is perfect on top-3. No leakage inflation — the shared-store images scored
*worse* than the independent ones.
² IMG_8121 (24MP iPhone HEIC, 37 targets — badge precision .97, coverage .76) and wine1
(1.2MP but close-range, 266px-wide bottles — 1.00 / .83). Neither was ever tuned on.
³ red-wine-shelf, es_market, intl_market, shop_uk: 0.8–1.2MP stock/library photos with median
bottle widths of **55–78px** — zero of their 118 targets reach the ~140px width where label text
is legible. The pipeline correctly refuses to guess (precision holds ≥ .85) but cannot name what
isn't readable, so coverage collapses. This is an input-resolution floor, not an architecture
failure: the same store wall photographed at 24MP (IMG_8335, iteration set) scored 1.00 badge
precision. **Strictly read, the full-aggregate coverage bar (.416 vs .60) fails — the GO is
conditional precisely because the product must gate these inputs out, and 4 of 6 held-out images
turned out to be out-of-distribution for a camera-first product.**

**Iteration set for comparison** (7 images, 207 targets, corpus v2): badge precision .910,
top-3 1.000 (19/19), swaps 0, coverage .729, $.0323/scan, wall mean 16.7s
(`out/bakeoff/c5_crops_sonnet5_v6.json`). Tuned-vs-held-out gap on badge precision: .910 → .905 —
no overfit.

### Rendered proof (webapp screenshots, `backend/out/render_checks/`)

All six held-out images were uploaded through the local webapp (Playwright) and screenshotted:
`gate3_IMG_8121.png` (19 badges, all on correct bottles by eye), `gate3_wine1.png` (6/6 perfect),
`gate3_redshelf.png`, `gate3_es_market.png` (sparse but correctly placed), `gate3_intl_market.png`,
`gate3_shop_uk.png` (sparse, on-bottle, BEST PICK correct). Iteration renders:
`webapp_8122_v6.png` (21 badges, on-bottle, row-correct), `webapp_8334_v6.png` (26 badges on the
densest wall, matching the harness's 1.00). As at Gate 2, rendered truth looks *better* than the
harness: most "off_bottle" badges sit on real but GT-unannotated duplicate bottles.

**Product polish item found during visual review:** rating ties produce multiple "BEST PICK"
tags (three tied 4.0s on wine1). Needs a frontend tie-break.

---

## 2. Measured cost (recorded per-call usage, not estimates)

From run-JSON `pipeline_info.usage` records, Sonnet 5 at **intro pricing $2/$10 per MTok** (what
litellm bills today; intro ends 2026-08-31):

| Component | Dense iteration mix | Held-out mix |
|---|---|---|
| Google Vision (5 tiled calls @ $1.50/1k) | $0.0075 | $0.0075 |
| Crop-read input (~6.7k tok dense) | $0.0133 | ~$0.008 |
| Read output (~870 tok dense) | $0.0087 | ~$0.005 |
| Rescue pass | $0.0028 | ~$0.001 |
| **Total web** | **$0.0323** | **$0.0209** |
| **Total iOS** (detection free on-device via Apple Vision) | **$0.0248** | **$0.0134** |

**Sticker-price sensitivity** (after 2026-08-31, $3/$15/MTok): web ≈ $0.045 dense / $0.028
typical; iOS ≈ $0.037 dense / $0.020 typical. The $0.03 bar holds on iOS at typical density even
at sticker; dense-wall web scans exceed it. Untried levers: smaller crop cap, cheaper-tier read
for high-confidence crops. **The web demo overstates mobile COGS by ~$0.0075/scan + ~2s (Apple
Vision runs detection free and locally on iOS).**

**Measured latency:** warm-server e2e `POST /scan`: 15.0 / 16.3 / 23.0s on three dense iteration
images (p50 ≈ 16s); held-out harness wall p50 12.2s, max 19.3s. **The 10s/15s bar is failed.**
Structure: Vision ~2s → parallel crop-read calls 6–13s (Anthropic generation-speed variance
dominates) → rescue 0–5s. Mitigations, by leverage:
1. **Progressive render** (SSE `phase1` plumbing already exists in the codebase): first badges at
   ~6–8s while the rest stream in — perceived latency, not pipeline latency, is the product bar.
2. ~~Smaller chunks~~ **Measured and disproven** (`CROPS_PER_CALL` 18→10, `c5_crops_v7_chunks10.json`):
   p50 16.6s — unchanged. The wall is the slowest parallel call (per-request generation-speed
   variance), not chunk size. Precision nudged up (.926) at identical cost, so 10 was kept, but
   **pipeline latency is floored at ~12–18s with this model; progressive render is the path.**
3. iOS on-device detection: −2s and −$0.0075.

---

## 3. App Store unit economics (model — assumptions labeled)

Assumptions: $4.99/mo subscription (Vivino is free but per-bottle; the value here is the
10-second whole-shelf decision), Apple small-business rate 15% → **$4.24 net/user/mo**;
typical 2 store visits/week × 1–2 scans ≈ **12 scans/user/mo**, heavy user 30.

| Scenario | COGS/user/mo | Gross margin |
|---|---|---|
| iOS, intro pricing, 12 scans (~$0.020) | $0.24 | 94% |
| iOS, sticker pricing, 12 scans (~$0.030) | $0.36 | 92% |
| iOS, sticker, heavy user (30 scans) | $0.90 | 79% |
| Free-trial user (5 scans, no revenue) | ~$0.15 acquisition cost | — |

Break-even ≈ 140 scans/user/mo at sticker pricing — an order of magnitude above heavy usage.
**Unit economics are comfortable and not a feasibility risk.**

---

## 4. What was proven, what changed, what remains

**Proven:**
- Wrong-bottle placement — the product-killing failure — is solved by construction: the LLM never
  emits coordinates, each crop maps to exactly one detected box. 1 swap / 368 targets (0.3%)
  across held-out + iteration.
- Set-of-marks reading (numbered boxes on one image) is a dead end at shelf density: three
  distinct measured correspondence failures (run log Round 3); per-crop reading is load-bearing.
- The eval harness understates rendered quality; every rendered spot-check matched or beat its
  harness number.
- Round 0 baseline for contrast: the shipped single-LLM pipeline measured **31.2% placement
  accuracy, 17.2% swaps, $0.0906/scan, 52.7s mean LLM latency**, and returned zero overlays on
  8/10 corpus images at shipped settings. The new pipeline beats it on every axis.

**Conditions / next steps if GO is exercised:**
1. Owner decision on latency: the chunk-size experiment is measured and dead (see §2) —
   accepting ~12–18s means shipping progressive render (SSE) for perceived latency.
2. Input-quality gate: warn/reject when median detected bottle width < ~140px (boxes are known
   before any LLM spend, so the check is free).
3. Re-cut the held-out set with device-quality photos (4/6 of the current set are web stock) for
   a confirmatory ~$0.15 run before public accuracy claims.
4. ~~Frontend BEST PICK tie-break~~ — fixed 2026-07-05 (`nextjs/lib/shelf-rankings.ts`: ordinal
   ranking with confidence/name tie-break; 78/78 frontend tests pass). Phase G legacy-pipeline
   deletion remains separately gated.

**Post-verdict verification (2026-07-05):** the owner manually clicked every rendered badge on
IMG_8121 in the webapp and confirmed each detail sheet's wine matches the bottle under the badge.

**Caveats carried from the run log:** corpus-v2 GT boxes are seeded from the same tiled detector
the pipeline uses (coverage may be flattered; mitigated with hand-added extra bottles);
`names_match(0.85)` is slightly generous; GT omits unreadable bottles, so some correct badges
score "off_bottle" (harness understates).

---

## Runnable demo

```bash
# backend (terminal 1) — .env already has PIPELINE_MODE=detect_read
cd backend && make watch
# frontend (terminal 2)
cd nextjs && PATH=~/.nvm/versions/node/v22.18.0/bin:$PATH npm run dev
# open http://localhost:3000 and upload a shelf photo (HEIC/JPEG/PNG)
```

Evidence index: run JSONs `backend/out/bakeoff/gate3_heldout.json` (held-out) and
`c5_crops_sonnet5_v6.json` (iteration); screenshots `backend/out/render_checks/gate3_*.png`,
`webapp_*_v6.png`; per-call cost/latency in each run JSON's `pipeline_info.usage`; production
usage via `log_usage` JSONL. History: `docs/FEASIBILITY_RUN_LOG.md`, commits `2e3541a`..HEAD
(prefix `feasibility:`).
