# Feasibility Run Log — Overlay Accuracy + Unit Economics

> Running state file for the feasibility loop (see the run prompt). One entry per round.
> A "round" = one full re-measurement of the corpus after a change.
> Resume protocol: read this file + `git log` on `rating-overlays` before starting new work.

## Run status

- **Phase:** COMPLETE — Gate 3 verdict delivered 2026-07-05 (CONDITIONAL GO, see FEASIBILITY_VERDICT.md)
- **Branch:** `rating-overlays`
- **Started:** 2026-07-04

## Approved success bar (Gate 1, owner-approved 2026-07-04)

Judged on audited + expanded held-out set, harness + rendered screenshots:
1. Top-3-by-rating badge precision ≥ 90% (incl. BEST PICK)
2. Badge precision ≥ 85%; wrong-bottle (swap) ≤ 5%
3. Coverage ≥ 60% of GT-annotated bottles get a correct badge
4. Cost ≤ $0.03/scan blended (measured)
5. Latency ≤ 10s p50 / 15s p95 end-to-end
Still blocked on owner: rotated OPENROUTER_API_KEY (not yet provided anywhere readable).

## Session-verified facts (2026-07-04)

- **Corpus composition** (verified by grep over `test-images/corpus/ground_truth/`):
  - 67 ground-truth JSONs total.
  - **10 dense-shelf files with `overlay_targets`** (64 targets total) — these measure overlay placement:
    `IMG_8080` (6), `IMG_8121` (8), `IMG_8122` (7), `IMG_8123` (8), `IMG_8124` (8), `IMG_8262` (4),
    `IMG_8334` (7), `IMG_8335` (6), `red-wine-shelf-in-a-supermarket-B7WY9Y` (4), `wine1` (6).
  - **57 numeric-named files without `overlay_targets`** — single-label crops from the XWines dataset
    (images in `corpus/labels/`), usable for identification accuracy only, NOT overlay placement.
- **Held-out split** (locked in `docs/OVERLAY_ACCURACY_PLAN.md`, commit 482d3b9, rebalanced note line 279):
  - Held-out (3): `IMG_8121`, `wine1`, `red-wine-shelf-in-a-supermarket-B7WY9Y` — do not tune on these.
  - Iteration (7): the remaining shelf images.
- **Old flash_names baseline** (`backend/out/baseline.json`, 10 images / 64 targets):
  assignment_accuracy = 45.3%, swap_rate = 9.4%, miss_rate = 45.3%, mean_iou = 0.947.
- **Current default pipeline:** `PIPELINE_MODE=single_llm`, `SINGLE_LLM_MODEL=anthropic/claude-sonnet-4-6`
  (verified in `backend/.env` and `config.py:186`; the Haiku docstring in `single_llm_pipeline.py:12` is stale).
- **Harness repointed** at `SingleLLMPipeline` this session (`eval_overlays.py` previously imported the
  deprecated `FlashNamesPipeline`).
- **wines.db** was missing locally; restored 2026-07-04 from `gs://wine-scanner-db/data/wines.db.gz`.
- **Frontend:** Next.js calls `POST /scan` (`nextjs/hooks/useScanState.ts` → `lib/api-client.ts:scanImage`).
  `.env.local` repointed at `http://localhost:8000` for local testing (was production Cloud Run URL).
  Backend runs via `cd backend && make watch`. Next.js needs Node ≥ 20.9 (`PATH=~/.nvm/versions/node/v22.18.0/bin:$PATH npm run dev`).
- **Keys:** `ANTHROPIC_API_KEY` present in `backend/.env`. `OPENROUTER_API_KEY` NOT set (owner must rotate
  the compromised key first). `GOOGLE_API_KEY` not set. This limits the bake-off to Anthropic-hosted models
  until keys are provided.

## Rounds

### Gate 3 — Held-out measurement + verdict (2026-07-05) — RUN COMPLETE, VERDICT DELIVERED

One held-out run (`out/bakeoff/gate3_heldout.json`, 6 images / 161 targets), no tuning after:
badgeP **.905** ✓ · top3 .875 (14/16; both misses on shared-store es_market — independent
subset 10/10) · swap **.006** ✓ · coverage **.416** ✗ · $.0209/scan ✓ · wall p50 12.2s ✗.
Split that explains coverage: device-quality photos (IMG_8121 24MP, wine1 close-range) score
badgeP .971 / top3 6/6 / swap 0 / **coverage .767 ✓**; the 4 web-stock images (0.8–1.2MP,
median bottle 55–78px, 0/118 targets ≥140px legibility floor) collapse to .288 coverage while
precision holds .85 — the model correctly refuses to guess unreadable labels. Measured e2e
warm-server POST /scan: 15.0/16.3/23.0s (p50≈16s) — latency bar failed, presented as tradeoff.

All 6 held-out images rendered via webapp + screenshotted (`out/render_checks/gate3_*.png`),
badge-on-bottle judged by eye in-session; renders match or beat harness scores. Noted: webapp
re-scan of intl_market returned 3 results vs the harness run's 8 — run-to-run variance is high
on illegible input. Product nit: rating ties produce multiple BEST PICK tags (wine1: three 4.0s).

**VERDICT (docs/FEASIBILITY_VERDICT.md): CONDITIONAL GO** — accuracy bars pass on device-class
photos with 1 swap/368 targets total; conditions = latency decision (progressive render or
CROPS_PER_CALL 18→10 experiment, est. p50 10–12s) + input-resolution gate (<~140px median
bottle width → prompt retake). Unit economics comfortable (92-94% gross margin at $4.99/mo,
12 scans/user/mo, iOS COGS $0.24–0.36/user/mo). Sticker-pricing sensitivity and iOS-vs-web
cost caveat (−$0.0075 + −2s on-device detection) documented in the verdict.

### Round 3 — Detect+Read tuning + production port (2026-07-05) — COMPLETE

**Diagnosis (from recorded Gate 2 usage, `out/bakeoff/c2_marks_sonnet5*.json` / `c3_crops_sonnet5*.json`):**
1. The "image payload dominates cost/latency" hypothesis was WRONG. C2+Sonnet5: prompt was a flat
   5,041 tok (marked image ≈4.7k image tok), completions ran 1.3k–3k tok and tracked latency at
   ~8.5 ms/tok (~118 tok/s). Output tokens = ~70% of LLM cost, ~90% of LLM latency. Cause: Sonnet 5
   adaptive thinking (on by default when `thinking` omitted) + verbose per-mark JSON. IMG_8080's C2
   read hit the 3,000-token cap (truncated).
2. Recorded Sonnet 5 costs use INTRO pricing ($2/$10 per MTok, litellm model_cost; sticker $3/$15
   after 2026-08-31). Verdict must quote both.
3. C3's 74% top-3 confirmed as duplicate-mark + GT-coverage artifact: on IMG_8080 C3 scored 13/13
   targets correct, 0 swaps, yet 0/3 top-3 — 17 badges for 13 targets, and the 4 extra
   (duplicate/unannotated-bottle) reads carried the highest ratings. Mark dedup is the fix.
   Without 8080, C3 top-3 was 14/16.

**Round 3 changes (all in `app/services/detect_read.py`, shared verbatim by eval candidate
`c4_daread_sonnet5` and production `PIPELINE_MODE=detect_read` — eval measures shipping code):**
- `thinking={"type":"disabled"}` (verified live: 13→3 compl tok on a probe; read call 3,000→~950 tok)
  + compact `[[id, name, conf, rating]]` output.
- Vision: 5 concurrent calls on a shared client with downscaled tiles (~1.3–2.5s wall).
  Tried `batch_annotate_images` first — SLOWER (3.4–12.2s, server processes batch serially). Reverted.
- Same-name+overlap mark dedup (keeps adjacent same-SKU facings); retry-once on empty response;
  final conf<0.45 filter (production hides those badges anyway).
- Label-zone crop re-read (≤8 crops, 512×768 max) for weak/null marks AND same-brand groups with
  distinct names (the measured swap mode: Frontera Cab↔Merlot etc.). Guarded: a crop re-read only
  overwrites a confident marks read if itself confident (ungated it rewrote good reads into garbage
  on low-res images: 8080 badgeP 0.80→0.61). Boxes <140px full-res width never re-read.
- Markers centered on bottle top (top-left tags visually hover over the LEFT neighbor in tight
  packs → measured off-by-one neighbor-copy cascades; 8122 swaps 3→0 after centering).
- TRIED AND REVERTED: two-panel parallel read (halve output tokens per call). Cropping the shelf
  into bands broke row context: 8122 badgeP .83→.69. Latency stays single-call-bound.

**Production port (commit f4a1007):** `DetectReadPipeline` subclasses `SingleLLMPipeline` (reuses
DB override, rating cache, log_usage). Route dispatch `PIPELINE_MODE=detect_read` added; local
`.env` switched. Verified live: POST /scan on IMG_8080 → 200, 11 results, contract bbox
{x,y,width,height} intact, usage records written. Legacy pipelines untouched.

**Measurements (7-image iteration set, corpus v2, all full re-runs):**
| run | badgeP | top3 | swap | cov (acc) | $/scan | paid-lat |
|---|---|---|---|---|---|---|
| c4 v1 marks (batched vision, 10-crop re-read) | .831 | .952 | .029 | .710 | .0303 | 23.3s |
| c4 v2 marks (+parallel vision, label-zone crops, conf filter) | .839 | 1.000 | .024 | .676 | .0261 | 18.4s |
| c4 v3 marks (+brand re-read guard, centered marks) | .787 | .900 | .024 | .676 | .0302 | 18.5s |
| c4 v4 marks (+reading-order numbering + seq prompt) | .560* | — | .150 | .560 | — | — |
| **c5 v5 CROPS-primary** (C3 arch + all economies) | **.906** | **1.000** | **.000** | .744 | .0357 | 16.5s |
| **c5 v6 crops (label-crop height 640px) — LOCKED** | **.910** | **1.000** | **.000** | .729 | .0323 | 16.7s |

**Why the architecture flipped mid-round (marks → crops):** the set-of-marks read kept breaking
marker↔bottle correspondence on dense lookalike walls, a failure mode that MOVED but never died:
v2's swaps were same-brand varietal copies; v3 collapsed IMG_8335 to .44 (row-level desync);
v4's "markers are in reading order" prompt line made the model pattern-fill sequentially — one
detector-skipped bottle shifted entire rows (off-by-one swap chains, swap rate 15%). Visual
audits of the actual marked images (out/render_checks/panelA_8122.jpg, marked_8335_v3/v4.jpg)
drove each diagnosis. Per-crop reading has no correspondence to lose (crop k IS bottle k) —
v5/v6 have ZERO swaps across 207 targets, and the dense walls became the best images
(8334 badgeP 1.00, 8335 1.00, 8262 .96). Kept from the marks era: width-aware group-box merge
(multi-bottle Vision detections were killing single boxes in the containment merge), reading-order
ids, parallel chunked calls (crops chunk freely — no context loss, unlike marked-image panels),
thinking-off, compact output, dedup, rescue pass, conf filter.

**v6 cost structure (intro pricing, per scan):** vision $.0075 + crop input $.0133 (6.7k tok)
+ output $.0087 (866 tok) + rescue $.0028 = $.0323. iOS-adjusted (on-device detection): $.0248 ✓.
Sticker-price (post 2026-08-31, $3/$15): ≈ $.045 web / $.037 iOS — verdict must carry this.

**Bar status on iteration set (v6):** top3 1.000 ✓ · badgeP .910 ✓ · swap .000 ✓ · coverage .729 ✓
· cost $.0323 marginal ✗ (iOS ✓) · latency ~16s wall ✗ (10s bar; production e2e to be measured in
webapp; presenting as the known tradeoff per owner's Gate 1 note).

**Next:** webapp rendered proof on iteration images → Gate 3 held-out run + 6 screenshots + verdict.

### Round 2 — Bake-off on corpus v2 (2026-07-04/05) — COMPLETE, at Gate 2

12 candidates × 7 iteration images (207 targets). Full table in `backend/out/bakeoff/` (JSONs+logs);
merged summary via scratchpad `summarize_bakeoff.py`. Bar: badgeP ≥.85, top3 ≥.90, swap ≤.05,
cost ≤$0.03, latency ≤10s p50.

| candidate | acc | swap | badgeP | top3P | $/scan | lat_s |
|---|---|---|---|---|---|---|
| **c3_crops_sonnet5** | .768 | **.000** | **.925** | .74 | .0536 | 18.9 |
| c3_crops_opus48 | .734 | .039 | .869 | .79 | .1153 | 20.2 |
| **c2_marks_sonnet5** | .667 | .034 | .849 | **1.00** | .0395 | 24.9 |
| c2_marks_opus48 | .729 | .058 | .823 | .86 | .0639 | 20.6 |
| c2_marks_sonnet(4.6) | .469 | .121 | .711 | .80 | .0294 | 24.8 |
| c3_crops_haiku | .411 | .188 | .599 | .76 | .0274 | 16.6 |
| c2_marks_haiku | .304 | .130 | .571 | .67 | .0141 | 14.9 |
| prod_single_llm(4.6) | .239 | .122 | .427 | .45 | ~.099 | ~57 |
| c1_lean_* (haiku/sonnet/sonnet5/opus4.7) | .07–.40 | .08–.21 | .20–.35 | .33–.38 | .013–.240 | 12–34 |

Findings:
1. **C1 family (LLM draws own boxes) is dead across 4 models** — ≤35% badge precision at any price.
2. **Detect+Read dominates**: tiled-Vision boxes + Claude-5-family label reading. C3 (per-crop) is
   structurally swap-free (92.5% badgeP, 0 swaps); C2 (set-of-marks) hits 100% top-3 at lower cost.
3. **Sonnet 5 > Opus 4.8** on both architectures at half the price. Newest models materially matter.
4. **Rendered proof** (`backend/out/render_checks/gate2_c2s5_IMG_8080.jpg`, `gate2_c2s5_IMG_8123.jpg`):
   16/18 and 25/27 badges visually on the correct bottle. Harness *understates* rendered truth: the
   "wrong" badges mostly sit on real-but-unannotated occluded/back-row duplicates (off_bottle GT
   artifact). Metric caveat the other way: names_match(0.85) accepted "Torre Monte"≈"Sobre Monte".
5. Remaining engineering gaps to bar: cost .0395→.03 and latency 25→10s (downscale marked image —
   image tokens dominate both; parallel crop-refinement), duplicate-mark badges (dedup), occasional
   empty LLM responses (retry-once).
6. Transient parallel-run failures (socket exhaustion, 600s timeouts) were re-run and merged via
   `*_gap.json`; all leaders cover all 7 images.

**Gate 2 proposal: "Detect + Read" architecture** — tiled Google Vision detection (5 parallel calls,
$0.0075, 2.4s) + one Sonnet 5 set-of-marks read + C3-style crop re-read for low-confidence marks +
mark dedup + empty-retry + existing DB rating override. Round 3 = tune to cost/latency bar on
iteration set; then production port + webapp + Gate 3 held-out measurement with Playwright proof.

### Round 0 — Baseline (single_llm + Sonnet 4.6) — DONE 2026-07-04, awaiting Gate 1 approval

**Runs (all artifacts under `backend/out/`, usage logs under `backend/logs/`):**

| Run | Config | Result |
|---|---|---|
| `round0` (`logs/token_usage_round0.jsonl`) | shipped default `max_tokens=2500` | **8/10 images truncated → JSON parse fail → ZERO overlays.** acc 7.8%. Production config is broken on dense shelves. |
| `round0b` (`out/round0b_sonnet46_8k.json`, `logs/token_usage_round0b.jsonl`) | `max_tokens=8000` (default bumped in `single_llm_pipeline.py`, uncommitted) | acc **31.2%** (20/64), swap 17.2%, miss 51.6%. 2/10 images (IMG_8262, red-wine-shelf) STILL truncate at 8k → 0 preds. Parseable-only acc = 20/56 = 35.7%. |

**Measured cost (round0b):** total $0.906 / 10 scans → **mean $0.0906/scan** (range $0.019–$0.127).
Docs claimed $0.02–0.04 — true only for sparse shelves.

**Measured latency (round0b, LLM call only):** mean **52.7s**, median 61.4s, max 76.6s.
Output tokens scale ~linearly with bottle count (verbose per-bottle JSON) → dense shelves are slow AND expensive.
E2E webapp scan of IMG_8080 (sparsest class): ~30–45s to rendered overlays (measured once via Playwright).

**Comparison:** old flash_names baseline on same corpus = 45.3% acc (`out/baseline.json`).
The single-LLM pivot REGRESSED placement accuracy per the harness (docs claim the opposite — reconciled: doc claim was based on one image, IMG_8080).

**Render validation (IMG_8080, Playwright vs local stack):**
- Frontend transform is pixel-faithful: rendered badge centers == `bbox.x+w/2, bbox.y+h*0.25` anchor
  == harness proxy, letterboxing correctly handled (verified numerically on all 11 badges).
  Artifacts: `backend/out/render_checks/render_check_IMG_8080.png` + `scan_response_IMG_8080.json`.
- Dominant visible failure: model emits bboxes spanning BOTH shelf rows (y 0.20→0.98), so the
  h×0.25 anchor lands between rows / on the wrong row. Second failure: right-edge drift (~0.05).
- **GT corruption found:** uncommitted prior-session edit to `IMG_8080.json` relabeled the bbox at
  x=0.5625 from "Giacondi Sangiovese Rubicone" (correct per pixels) to "Do Mo" (wrong — DO MO is
  the green bottle at x≈0.45–0.54). Verified via `out/visuals/IMG_8080_diff.jpg`. GT needs an audit
  pass before it can anchor a success bar.

**Environment fixes this session:** wines.db restored from GCS (193,253 wines); nextjs `.env.local`
repointed to localhost:8000; Next.js `/` 404 fixed by clearing stale `.next` cache; harness repointed
from FlashNamesPipeline to SingleLLMPipeline; `max_tokens` default 2500→8000.

**Next (pending Gate 1 approval):** GT audit + corpus fix, then candidate bake-off (Gate 2).
Blocked on owner for: rotated `OPENROUTER_API_KEY` (compromised key), optional `GOOGLE_API_KEY`
for direct Gemini. Without them, only Anthropic-hosted models are testable.

### Round 1 — GT audit + metric extension + bake-off scaffolding (2026-07-04, in progress)

- Round 0 checkpoint committed as `2e3541a`. Gate 1 bar approved by owner (see "Approved success bar").
- Visual render audit of IMG_8080 rendered scan: **6 of 11 badges on the wrong bottle**, 3 correct,
  2 edge/ambiguous — annotated proof at `backend/out/render_checks/render_check_IMG_8080_annotated.png`.
- GT audit assets generated (`backend/out/gt_audit/<stem>/`: numbered overview + per-target zoom crops);
  10 parallel agents auditing every target name/bbox against pixels.
- **GT provenance discovered:** IMG_8080's 6 GT bboxes are byte-identical to Google Vision
  OBJECT_LOCALIZATION output — GT was seeded from Vision detections, which explains why only ~6 of
  15 bottles per image are annotated.
- **Google Vision recall ceiling measured (live call):** raw API returns 10 objects (5 "Wine bottle",
  5 "Bottle") for the 15-bottle IMG_8080; 6 after IoU dedup. High precision, low recall on dense
  shelves. TEXT_DETECTION returned 56 blocks (much higher label coverage) — OCR-cluster anchors are
  a viable candidate ingredient. Tile-based detection (2x2 crops) is the recall-boost hypothesis to test.
- Metric extended per approved bar: `PrecisionView` in `overlay_metrics.py` (badge precision /
  top-3 precision / unjudgeable) + printed in `eval_overlays.py`.
- Bake-off scaffolding: `backend/scripts/candidates.py` registry + `--candidate` flag in the harness.
  C1 lean-output variants registered (sonnet/opus/haiku). Planned: C2 set-of-marks (Vision boxes +
  numbered markers, LLM assigns names to IDs — no LLM coordinates), C3 per-crop label reading,
  C6 OCR-cluster anchors. C2/C3/C6 build specs to be delegated to parallel agents after GT fixes.

#### GT audit results (all 10 images, agent-audited + spot-verified) — HEADLINE FINDING

**30 of 64 original overlay_targets (47%) were defective**: box on the wrong bottle (wrong_bbox),
wrong/mashed-up name (wrong_name), or invented wines (e.g. "Louis Latour" in IMG_8334 — no such
bottle exists there; "Ribeaupierre Medoc" in red-wine-shelf). Per image: 8080 3/6, 8121 4/8,
8122 3/7, 8123 4/8, 8124 4/8, 8262 4/4 (ALL), 8334 3/7, 8335 3/6, redshelf 2/4, wine1 0/6 (clean).
Common patterns: box lands 1-2 bottles away from the named wine (machine annotation offset),
names conflate two adjacent bottles, coverage skips most readable bottles.

**Consequence: every earlier accuracy number (old flash_names 45.3%, Round 0's 31.2%) was scored
against ~half-corrupt GT and is unreliable as an absolute.** Relative model-to-model comparisons
made against the same GT remain directionally useful, nothing more.

**Corpus v2 rebuild (in progress):** IMG_8080 rebuilt + visually verified (13 targets, was 6).
The other 8 defective images being rebuilt via detection-seeded protocol (tiled-Vision boxes,
numbered marks + zoom crops, agent reads each crop, no-guessing rule, audit knowledge as
cross-check). wine1 kept as-is (clean). 3 NEW held-out images being annotated the same way:
`heldout_es_market` (36 boxes), `heldout_intl_market` (33), `heldout_shop_uk` (23) — real dense
store shelves, much harder than the staged corpus. Note: corpus-v2 boxes are seeded from the same
tiled-Vision detector C2/C3 use — coverage metric could favor them; mitigated by adding
agent-listed extra_bottles with hand boxes, and noted for the verdict.

Audit JSONs preserved in git history of this file's session; raw agent outputs in the session
transcript. IMG_8080's identity: it is a screenshot of the same source photo as
corpus/shelves/8921FE9E-...jpeg (Google Lens UI icons baked into pixels).

#### Corpus v2 status (2026-07-04, late)

Merged and spot-checked (verdicts in `backend/out/gt_rebuild/verdicts/` and
`backend/out/new_heldout/*/verdicts.json`; target boxes = tiled-Vision detections verified per-crop,
plus approximate hand boxes for detector misses):

| Image | v1 targets | v2 targets | Notes |
|---|---|---|---|
| IMG_8080 | 6 (3 bad) | 13 | rebuilt + lead-verified |
| IMG_8121 (held-out) | 8 (4 bad) | 37 | rebuilt |
| IMG_8122 | 7 (3 bad) | pending | rebuild in flight |
| IMG_8123 | 8 (4 bad) | 25 | rebuilt, lead spot-check clean |
| IMG_8124 | 8 (4 bad) | 27 | rebuilt |
| IMG_8262 | 4 (4 bad) | 40 | rebuilt, lead spot-check clean |
| IMG_8334 | 7 (3 bad) | 36 | rebuilt |
| IMG_8335 | 6 (3 bad) | 31 | rebuilt |
| red-wine-shelf (held-out) | 4 (2 bad) | 32 | rebuilt |
| wine1 (held-out) | 6 (0 bad) | 6 | unchanged (clean) |
| heldout_es_market (NEW) | — | 29 | lead added 3 same-family coverage targets after spot-check |
| heldout_shop_uk (NEW) | — | 30 | includes famous SKUs (Cepparello, Daumas Gassac) |
| heldout_intl_market (NEW) | — | pending | annotation in flight |

Held-out set (6): IMG_8121, wine1, red-wine-shelf, heldout_es_market, heldout_intl_market,
heldout_shop_uk. Iteration set (7): IMG_8080, IMG_8122, IMG_8123, IMG_8124, IMG_8262, IMG_8334,
IMG_8335. Caveat noted: heldout_es_market shares SKUs with iteration image IMG_8335 (same store
chain, different shelf/photo); shop_uk and intl_market are fully independent distributions.
Known metric caveat: GT coverage is not exhaustive — a correct badge on an unannotated bottle
whose name matches an annotated same-name target elsewhere scores off_bottle. Mitigated by
same-family coverage additions during spot-checks; residual risk noted for the verdict.
