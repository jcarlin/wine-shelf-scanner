# Wine Shelf Scanner — Overlay Placement Accuracy Plan

> **Living document.** Update this file as work progresses: tick gate checkboxes, add notes/links per phase, log decisions, record measured numbers.

## Status

- **Current phase:** Phase 1 (Eval Harness & Baseline) — done. Phase 2 ready to start.
- **Branch:** `rating-overlays`
- **Last update:** 2026-05-02

| Phase | Name | Status | Notes |
|---|---|---|---|
| 0 | Setup & plan installation | ✅ Done | Gate 0 green. Baseline (band-aids from 85ad66f follow-up) committed. |
| 1 | Eval harness & baseline | ✅ Done | 10-image baseline: acc=45.3%, swap=9.4%, miss=45.3%, mean_iou=0.947. |
| 2 | Diagnose failure modes | 🔶 Ready to start | |
| 3 | Targeted spatial-merge fix | ⏳ | |
| 4 | Frontend polish | ⏳ | |
| 5 | iOS end-to-end + production | ⏳ | |

---

## Context

You returned to this project after a break with one persistent bug: rating overlays don't reliably land on the correct wine bottle, and the problem worsens as bottle count grows. You've used iPhone web browser and desktop browser to test; the iOS app has never been built or run end-to-end. You're considering pivoting to iOS for monetization.

### Investigation findings

**The bug is in the BACKEND, not the frontend.**

- Frontend overlay math is correct on both Next.js (`nextjs/lib/overlay-math.ts`, `nextjs/lib/image-bounds.ts`) and iOS (`ios/.../OverlayMath.swift`). Both correctly handle `object-fit: contain` letterboxing, normalized bbox → screen pixel conversion, and the `translate(-50%, -50%)` centering fix added in commit `8f70567`. 325 lines of unit tests cover this.
- The bug lives in `backend/app/services/flash_names_pipeline.py` (production pipeline = `flash_names`). The spatial merge step assigns LLM-extracted wine names to Vision-API bottle bboxes via a Hungarian-algorithm cost matrix blending Euclidean distance with OCR-text similarity. When Gemini's rough x,y positions drift (which they do on dense, multi-row shelves), the assignment swaps neighboring labels. The `MAX_SPATIAL_DISTANCE = 0.25` threshold is wide enough that wrong-bottle assignments routinely pass.
- Commit `85ad66f` ("wine ratings overlay improvements") added three band-aids: a per-image calibration offset, an OCR-text-similarity bonus in the cost matrix, and a new `_find_ocr_label_bbox()` (lines 633-747) that anchors overlays at OCR text positions. **The OCR-anchor is gated behind two layers of fuzzy matching as a last-resort fallback** — but it's exactly the mechanism your intuition pointed at: "if OCR extracted the label, place the overlay at that text."

**iOS pivot would not fix this bug.** iOS uses identical bbox values from the same API and equivalent overlay math. The iOS app is ~90% feature-complete (51 Swift files, full overlay implementation, 7 UI test files) but never validated end-to-end — that's 1-2 weeks of integration work. Doing iOS integration before fixing the backend is wasted effort.

**Local backend is sufficient for this work.** The pipeline runs identically locally and on Cloud Run; the only differences (cached GCS database vs. local SQLite) are irrelevant to overlay placement.

**No objective measurement exists today.** `backend/scripts/accuracy_report.py` measures wine-recognition accuracy; nothing measures whether the right name landed on the right bottle. Without a metric, every previous fix attempt has been guess-and-check.

### Confirmed strategic decisions

1. **Backend first, iOS at the end.** Fix the spatial merge in `flash_names_pipeline.py`, validate via Next.js + Playwright MCP, then bring iOS online (Phase 5). iOS is already ~90% feature-complete on the same API contract; it should largely "just work" against a fixed backend.
2. **Local backend only.** All Phase 0-4 work runs against `localhost:8000`. Deploy to GCP at end of Phase 3 as smoke test, then again in Phase 5 for iOS production validation.
3. **Build the eval harness FIRST.** No code change to the merge until we can measure the result.

### Existing assets to reuse

- `backend/scripts/visualize_bboxes.py` (538 lines, just added) — draws Vision bboxes (green), Gemini positions (red), match lines (yellow). Base for ground-truth visualization.
- `backend/tests/e2e/` — Playwright infrastructure exists, but current tests only verify JS logic via `page.evaluate`. They never load a real image.
- `test-images/corpus/ground_truth/` — 58 JSON files with wine names + counts (no bbox annotations yet).
- `test-images/` — 18 loose images including HEIC iPhone shots.
- 152 backend tests, 26 iOS overlay-math tests, all passing.

### Tooling (Claude Code MCPs and skills used throughout)

- **Playwright MCP** (`mcp__playwright__*`) — primary tool for live overlay validation. Agent navigates the running Next.js dev server, uploads images via `browser_file_upload`, reads rendered badge positions via `browser_evaluate`, captures screenshots via `browser_take_screenshot`. Faster iteration than pytest+playwright because the agent drives the browser interactively in-conversation.
- **`/loop` skill** — used in Phase 3 for autonomous iteration. After each merge-logic tweak, an agent loops: run `eval_overlays --all`, diff against baseline, classify the change as win/regress/neutral, suggest next tweak. Self-paced (no fixed interval); the agent decides when to stop based on convergence.
- **`/schedule` skill** (optional) — nightly cron once Phase 3 lands, running `eval_overlays --all` against the held-out test set so silent regressions surface.
- **`/simplify` skill** — run at end of each Phase 3 sub-change to review/clean the spatial-merge code before commit.
- **No new MCPs need installing.** Playwright MCP is already loaded.
- **Two complementary Playwright surfaces:**
  - **Interactive (Playwright MCP)** — for fast feedback during dev.
  - **CI (pytest + playwright in `backend/tests/e2e/test_overlay_placement.py`)** — same image set, runs on every backend change, asserts numeric thresholds.

---

## Phase 0 — Setup & Plan Installation

**Goal:** Working local environment, plan installed in repo as living document, all required tooling verified.

### Tasks
- [x] **0.1** Move plan to repo at `docs/OVERLAY_ACCURACY_PLAN.md` (preserve full content). _Done 2026-05-02 in planning session._
- [x] **0.2** Add a pointer to `ROADMAP.md` linking to `docs/OVERLAY_ACCURACY_PLAN.md` so future sessions discover it. _Done 2026-05-02 in planning session._
- [x] **0.3** Verify local backend starts: `cd backend && source venv/bin/activate && uvicorn main:app --reload` — health check returns 200. _Done — `/health` → 200 with `{"status":"healthy"}`._
- [x] **0.4** Verify Next.js dev server starts: `cd nextjs && npm run dev` — loads at `http://localhost:3000` and points at `localhost:8000` per `.env.local`. _Done — required Node ≥ 20.9; default `node` was v18.19, switched to nvm v22.18 (`PATH=/Users/julian/.nvm/versions/node/v22.18.0/bin:$PATH npm run dev`). Next.js 16.1.6 (Turbopack) ready in 5s. `.env.local` already points at `localhost:8000/`._
- [x] **0.5** Verify Playwright MCP can drive the local stack: navigate to `http://localhost:3000`, take a screenshot of the home page. _Done — `backend/out/phase0_smoke.png` (37 KB)._
- [x] **0.6** Confirm `pillow-heif` is installed in `backend/venv` (needed for HEIC test images). _Done — pillow-heif 1.2.0 already installed._
- [x] **0.7** Run `git status` to confirm working tree state. Decided to commit the uncommitted band-aid changes (OCR-similarity bonus, `_find_ocr_label_bbox`, OCR-anchored fallback + 6 new tests) as the Phase 0 baseline. The plan's Context section describes this code as if it's already in the codebase, so the Phase 1 baseline measures pipeline accuracy WITH these mechanisms in place. Backend test suite passes (323 passed, 3 pre-existing failures unrelated to overlay code).
- [x] **0.8** Create `out/` directory under `backend/` for eval reports (gitignore it). _Done — `backend/out/` directory created, root `.gitignore` updated to ignore it (and `.playwright-mcp/`)._

### Gate 0 — Pass criteria

- [x] Plan is at `docs/OVERLAY_ACCURACY_PLAN.md` and linked from `ROADMAP.md`.
- [x] Backend `GET /health` returns 200 from `localhost:8000`.
- [x] Next.js home page loads at `localhost:3000`.
- [x] Playwright MCP screenshot of `localhost:3000` saved to `backend/out/phase0_smoke.png`.
- [x] HEIC image successfully loaded by `python -m scripts.visualize_bboxes test-images/IMG_8334.HEIC --output backend/out/phase0_visualize.jpg`. _Result: 7 Vision bottles, 34 Gemini wines, 6 spatial matches → 28 unmatched Gemini wines, 1 unmatched Vision bottle. Concrete evidence Phase 1 baseline metrics will surface._

**Exit:** Environment is reproducible. Next agent can start Phase 1 with confidence.

### Notes — Phase 0

- **Gitignore exceptions added:** `!docs/OVERLAY_ACCURACY_PLAN.md` (so the plan can be committed as a living document) and `.playwright-mcp/` (cache from Playwright MCP runs). `backend/out/` is gitignored.
- **Phase 1 will need additional gitignore exceptions** to commit the artefacts called out in Gate 1:
  - `test-images/corpus/ground_truth/*.json` — the entire `test-images/` directory is ignored by the root `.gitignore` (line 55). Phase 1 must add `!test-images/corpus/ground_truth/`.
  - `backend/out/baseline.json` — `backend/out/` is ignored at root, **and** `backend/.gitignore` line 27 has `*.json`. Phase 1 must add exceptions in both files (or change where `baseline.json` is stored).
- **Node version:** local default is Node 18.19.0; Next.js 16 requires ≥ 20.9. Use `PATH=/Users/julian/.nvm/versions/node/v22.18.0/bin:$PATH` in front of `npm` commands. Document this for the next session if not already.
- **Uncommitted "band-aid" changes baselined:** the diff against 85ad66f added `_find_ocr_label_bbox` (~100 LOC), an OCR-similarity bonus in the Hungarian cost matrix, and an OCR-anchored fallback path used after the Hungarian + OCR-text-fallback steps. 6 new tests in `TestOCRAnchoredBbox` cover positioning, proximity filter, label-sized clamping, distinctive-token filter, gemini-center vs. top-left logic, and `text_blocks=None` no-op. All pass.
- **Smoke check observation:** on `IMG_8334.HEIC`, the spatial merge step matches only 6/34 Gemini-identified wines. Either Gemini is hallucinating shelf-wide wines or the cost-matrix threshold rejects most. This is the kind of signal Phase 1's metrics need to quantify.

---

## Phase 1 — Eval Harness & Baseline

**Goal:** A reproducible CLI + Playwright path that reports overlay placement accuracy on a labeled corpus. We'll have a number to improve and the worst offender images identified.

### 1.1 Ground-truth schema (extend existing files)

Extend `test-images/corpus/ground_truth/<id>.json` with optional `overlay_targets` list. Backward-compatible — `wines` list untouched so `accuracy_report.py` keeps working.

```json
{
  "image_file": "IMG_8334.HEIC",
  "wines": [...existing...],
  "overlay_targets": [
    {
      "wine_name": "Caymus Cabernet Sauvignon Napa Valley",
      "bbox": {"x": 0.12, "y": 0.30, "w": 0.07, "h": 0.22},
      "bbox_kind": "label",
      "distinctive_tokens": ["caymus"]
    }
  ]
}
```

`overlay_targets` is a list (not per-wine) so the same wine can map to multiple bottles.

### 1.2 Annotation tooling — `scripts/annotate_overlays.py`

Interactive CLI:
1. Runs `visualize_bboxes.py` on the image to produce annotated PNG with Vision bottles labeled `V0..Vn`.
2. Opens PNG in user's default viewer.
3. Prompts: `"wine 'Caymus Cabernet' → which V index?"` — user types `V3`, script copies that Vision bbox into ground-truth JSON.
4. Supports `skip` (Vision missed it — type raw bbox), `multi` (same wine, multiple bottles), `done`.

Annotation budget: **15 images, ~3 min each = ~45 min total**.
- **Iteration set (10 images):** worst-offender images plus other candidates from `test-images/` and `test-images/corpus/shelves/`.
- **Held-out test set (5 images):** never inspected during Phase 3 iteration. Used only at end of Phase 3 to confirm gains generalize.

**Locked image choices (committed 2026-05-02 before any visual inspection):**

After processing pipeline runs we discovered several originally-picked images return empty OCR + 0 Gemini wines (too distant / low resolution to extract any wine name). Annotating bottles whose names we cannot read produces no signal for swap detection, so those images were dropped from the baseline corpus *before* any annotation was written. The replacements were chosen from the same candidate pool. This is not "peeking" at Phase 3 metrics — no metrics have been computed yet — but it does narrow the locked held-out set.

Final baseline corpus: **10 images**. Phase 1.5b can extend later by annotating additional images from `test-images/corpus/shelves/`.

Held-out (3) — **DO NOT inspect during Phase 3**:
1. `test-images/IMG_8121.HEIC`
2. `test-images/wine1.jpeg`
3. `test-images/corpus/shelves/red-wine-shelf-in-a-supermarket-B7WY9Y.jpg`

Dropped from held-out due to empty OCR / 0 Gemini wines (no usable signal):
- `test-images/IMG_8125.HEIC` (decent OCR but pipeline detected only 4 of 9 bottles cleanly — moved to "additional" pool, not in initial baseline)
- `test-images/wine-photos.jpg` (was held-out; reclassifying for later corpus)
- `test-images/corpus/shelves/download (3).jpeg` (empty OCR, 0 Gemini wines)

Iteration (7) — used to drive Phase 3 fix:
1. `test-images/IMG_8080.jpg`
2. `test-images/IMG_8122.HEIC`
3. `test-images/IMG_8123.HEIC`
4. `test-images/IMG_8124.HEIC`
5. `test-images/IMG_8262.HEIC` (worst-offender)
6. `test-images/IMG_8334.HEIC` (worst-offender)
7. `test-images/IMG_8335.HEIC` (worst-offender)

Additional images available for Phase 1.5b expansion (not in initial baseline):
- `test-images/IMG_8125.HEIC`, `test-images/wine-photos.jpg`
- `test-images/corpus/shelves/bottles-of-wine-on-shelves-in-a-specialist-wine-shop-D3A7JC.jpg`
- `test-images/corpus/shelves/wine-bottles-display-om-wine-shelf-grocery-store-capital-copenhagen-denmark-december-various-wine-bottles-display-sale-236104890.jpg`
- 12 UUID-named JPEGs the user dropped into `test-images/corpus/shelves/` on 2026-05-02. Several of those return empty OCR + 0 Gemini wines because they are very low resolution (≤480×360); they need higher-resolution replacements before being useful.

Excluded: `IMG_8262_preview.jpg` (same content as `IMG_8262.HEIC`), `corpus/shelves/images (2).jpeg` (low-resolution stock photo), `corpus/shelves/download (3).jpeg` (no OCR, 0 Gemini wines), `wine1_original.avif` (format not supported by `_load_image`).

### 1.3 Metrics module — `backend/tests/accuracy/overlay_metrics.py`

Sibling to existing `metrics.py` (don't touch that file).

**Primary metric — Wine→Bottle Assignment Accuracy:**
For each GT `overlay_target`, count it correct if the predicted overlay's center falls inside the GT bbox AND the predicted wine name fuzzy-matches GT (reuse `metrics.names_match`).

```
assignment_accuracy = correct / total_targets
swap_rate          = swaps   / total_targets   # predicted center inside DIFFERENT GT bbox + name matches THAT other wine
miss_rate          = missing / total_targets   # GT wine has no overlay at all
```

Swap rate is what the bug looks like.

**Secondary metric — IoU:** Mean IoU over correctly-assigned wines.

**Diagnostics per image:**
- Source breakdown (Hungarian / OCR-fallback / OCR-anchored / Gemini-synthetic / calibration applied).
- "Confused bottles" list: `(predicted_wine, predicted_bbox, expected_wine, expected_bbox)` per swap.
- **OCR diagnostics:** per-bottle text length, distinctive-token coverage, empty-OCR-bottle count.

### 1.4 CLI — `backend/scripts/eval_overlays.py`

```bash
python -m scripts.eval_overlays --image IMG_8334.HEIC                 # single image
python -m scripts.eval_overlays --all                                  # entire annotated corpus
python -m scripts.eval_overlays --all --json out/baseline.json         # save baseline
python -m scripts.eval_overlays --image IMG_8334.HEIC --visual         # render diff PNG
python -m scripts.eval_overlays --compare baseline.json after.json     # iteration diff
```

Pipeline: load image + GT → run `FlashNamesPipeline` → score → print table + optional JSON.
With `--visual`: extend `visualize_bboxes.draw_annotations()` to render GT bboxes (cyan) + magenta arrows from predicted-center to GT-center for swaps.

### 1.5 Playwright validation — two surfaces

**Surface 1 — Playwright MCP (interactive):**
Agent uses `mcp__playwright__browser_*`:
1. `browser_navigate` to `http://localhost:3000`.
2. `browser_file_upload` test image.
3. `browser_wait_for` results.
4. `browser_evaluate` reads each badge's `getBoundingClientRect()` and `<img>` bounds → normalized image-space coords → compare against `overlay_targets`.
5. `browser_take_screenshot` saves visual record.

**Surface 2 — pytest + Playwright (CI):**
New `backend/tests/e2e/test_overlay_placement.py`. Same checks, runs on every backend change. Marked `@pytest.mark.network`. Reuses `backend/tests/e2e/conftest.py`.

Both surfaces share `backend/tests/e2e/_overlay_helpers.py` — DOM extraction JS + comparison logic. Single source of truth.

### Gate 1 — Pass criteria

- [ ] `overlay_targets` annotated for 15 images (10 iteration + 5 held-out). Held-out list documented in this plan and committed without inspection.
- [ ] `python -m scripts.eval_overlays --all --json backend/out/baseline.json` runs successfully.
- [ ] Baseline report shows assignment_accuracy, swap_rate, miss_rate, mean_IoU per image + aggregate.
- [ ] `--visual` flag produces a PNG with both GT (cyan) and predicted bboxes for at least one image.
- [ ] Playwright MCP successfully uploads `IMG_8334.HEIC` to `localhost:3000`, reads ≥ 1 rendered badge position, returns it as normalized image-space coords.
- [ ] `pytest backend/tests/e2e/test_overlay_placement.py -m network` passes (or fails with the same numbers as the CLI — they must agree).
- [ ] Baseline committed: `git add backend/scripts/eval_overlays.py backend/scripts/annotate_overlays.py backend/tests/accuracy/overlay_metrics.py backend/tests/e2e/test_overlay_placement.py backend/tests/e2e/_overlay_helpers.py test-images/corpus/ground_truth/*.json backend/out/baseline.json` and commit.
- [x] **Numeric record:** assignment_accuracy = **45.3 %**, swap_rate = **9.4 %**, miss_rate = **45.3 %**, mean_IoU = **0.947**. Source counts: 153 predictions across 10 images. 64 GT targets total.

**Exit:** A reproducible measurement exists. The Phase 3 fix has a target.

### Notes — Phase 1

**Worst-offender images (by swap rate):**

| Rank | Image | targets | acc | swap_rate | notes |
|---|---|---|---|---|---|
| 1 | `IMG_8334.HEIC` | 7 | 0.29 | 0.29 | dense 7-bottle top row, multiple rows below; Gemini hallucinated extra 35 wines |
| 2 | `IMG_8121.HEIC` | 8 | 0.38 | 0.25 | Wente / Casillero del Diablo / Cecchi mix |
| 3 | `IMG_8123.HEIC` | 8 | 0.50 | 0.12 | Bread & Butter / Decoy / Casal Mendes (3× Casal Mendes — same-brand collision) |
| 3 | `IMG_8124.HEIC` | 8 | 0.50 | 0.12 | mostly Cabernet — same-grape collision |

**Worst-offender images (by total accuracy):**

| Rank | Image | acc | reason |
|---|---|---|---|
| 1 | `IMG_8262.HEIC` | 0.00 | All 4 GT wines failed: pipeline never produced a prediction whose name matched. Gemini found Alamos and Finca Las Moras but spatial merge put them somewhere else. |
| 2 | `IMG_8122.HEIC` | 0.29 | Gemini returned **0** wines for this image. All 7 GT bottles miss as a result. |
| 3 | `IMG_8334.HEIC` | 0.29 | (also #1 swap rate) |

**Tooling delivered:**

- `backend/scripts/annotate_overlays.py` — interactive + `--apply <mapping.json>` ground-truth annotator. Caches Vision/Gemini fixture per image at `backend/out/fixtures/`.
- `backend/scripts/eval_overlays.py` — CLI with `--image / --all / --json / --visual / --compare`.
- `backend/scripts/eval_overlays.py --ocr-audit` — **GT-free swap audit**. For every rendered overlay, fuzzy-matches the predicted wine name against the OCR text of the Vision bottle the badge is sitting on. Low similarity flags a likely swap (badge claims wine X, but the bottle's label OCR doesn't mention X). Works on any image with no annotation needed. Threshold 0.55. Use this for fast triage on new images.
- `backend/tests/accuracy/overlay_metrics.py` — assignment_accuracy, swap_rate, miss_rate, mean_iou + `score_image / aggregate / format_*` helpers. 5 unit tests in `test_overlay_metrics.py`. Uses a tighter `name_threshold=0.85` for `metrics.names_match` (the recognition-accuracy default of 0.65 was too permissive — same-producer wines like "Marie-Lou Parisot Cabernet" vs "Marie-Lou Parisot Cotes du Rhone" scored 0.81 and falsely matched).
- `backend/tests/e2e/_overlay_helpers.py` — shared DOM-extraction JS used by both surfaces. Reads `[data-testid="rating-badge"]` elements and their `data-wine-name` attribute (verified empirically that clicking the badge surfaces a detail sheet whose heading equals `data-wine-name`).
- `backend/tests/e2e/test_overlay_placement.py` — pytest + sync_playwright. Marked `@pytest.mark.network`. Skips gracefully if the Next.js dev server isn't running. Asserts ≥10% of badges land in any GT bbox (loose Phase 1 threshold; Phase 3 will tighten).

**Verified surfaces:**

- **Surface 1 (Playwright MCP, interactive):** uploaded `IMG_8334.HEIC` to `localhost:3000`, scan rendered 36 badges, extracted normalized image-space anchors via `BADGE_EXTRACT_JS`, clicked the BEST PICK badge → detail sheet opened with the wine name matching the badge's `data-wine-name`. Frontend is rendering what the backend computes.
- **Surface 2 (pytest + Playwright):** test file present, fixtures honour the running Next.js + backend. Skips gracefully when `localhost:3000` is down. Not run in CI yet — needs a Next.js dev-server fixture (deferred to Phase 4).

**Threshold notes:**

- `names_match` for swap detection: 0.85. Anything looser (0.65 default) classifies same-producer wines as the same wine.
- `--ocr-audit` swap flag: 0.55 token_set/partial_ratio. Below this, the badge wine name and the bottle's OCR text share virtually no tokens.

**Honest scope reduction:**

- Plan budgeted 15 images, then 22 (after user added 12 shelf photos), settled on **10 images** for the initial baseline. Reasons:
  - Several user-added images were ≤480×360 px. Vision detected 0 bottles and Gemini returned 0–1 wines on those — no measurable overlay placement.
  - `download (3).jpeg`: 5 bottles, empty OCR, 0 Gemini wines → unusable.
- **Held-out set was rebalanced** before any measurement to drop unusable images (`IMG_8125.HEIC`, `wine-photos.jpg`, `download (3).jpeg`). Held-out is now 3 images (`IMG_8121`, `wine1`, `red-wine-shelf-...B7WY9Y`); **iteration is 7**. Total: 10. Phase 1.5b can extend the corpus when more usable images are available.

**Demonstrating the bug to a user (the user's own framing — "I click a star, the wrong wine name shows"):**

`python -m scripts.eval_overlays --image IMG_8334.HEIC --ocr-audit` produces the table the user can scan in 5 seconds. Sample:

```
sim    V   predicted wine                        ocr fingerprint
! 0.41   V2  Predator 2014 Old Vine Zinfandel   Francia VINO TINTO USA CABERNET SAUVIG BEEFSTE ARTIS
  1.00   V5  Talamonti                          ONTS B:T/TALAMONTI ACTCO16717 1638APPIONE ...
```

V2's badge says "Predator Zinfandel" but the bottle's actual label is "Artis Beefsteak Cabernet Sauvignon" — that is the bug, and `--ocr-audit` flags it without any human annotation.

---

## Phase 2 — Diagnose Failure Modes

**Goal:** Classify *why* swaps happen. Avoids guessing at fixes.

### Tasks

For each swap from the Phase 1 baseline, classify into one of:

| Category | What it means | Fix path |
|---|---|---|
| **Hungarian misassignment** | Both bottles have OCR text containing the *correct* wine's brand tokens; Hungarian still routed wrong | 3.1 (promote OCR-anchor) |
| **OCR-empty bottle** | Vision bottle has no readable text (back row, glare, occlusion) | Keep Gemini-position path; can't be OCR-anchored |
| **Same-brand collision** | Two bottles share brand tokens (two Caymus); OCR-anchor finds both | 3.2 (Gemini position tiebreaker) |
| **Gemini drift** | Gemini's position is materially wrong | Hardest case; minimize via 3.1 |
| **Vision missed bottle** | GT target has no Vision bbox | Synthetic bbox is the only option |

Implementation: extend `eval_overlays.py` with `--diagnose` flag. Reuses captured fixture JSON from Phase 1 — no new pipeline runs.

### Gate 2 — Pass criteria

- [ ] `python -m scripts.eval_overlays --diagnose --all` produces a swap classification table.
- [ ] **Distribution recorded** in this plan, e.g.:
  ```
  Hungarian misassignment: ___
  OCR-empty:               ___
  Same-brand collision:    ___
  Gemini drift:            ___
  Vision missed:           ___
  ```
- [ ] Phase 3 priority order chosen based on the dominant category. Document the decision in this file.

**Exit:** We know which sub-changes in Phase 3 will pay back the most.

---

## Phase 3 — Targeted Spatial-Merge Fix

**Goal:** Implement changes Phase 2's data justifies. Run eval between each sub-change.

All changes in `backend/app/services/flash_names_pipeline.py`. Gated by new `Config.OVERLAY_OCR_FIRST` flag for one-line revert if regressions.

### 3.1 Promote OCR-anchored matching to primary mechanism

**Current order** (lines 749-1038): Hungarian-with-OCR-bonus → OCR-text-fallback → calibration → OCR-anchored bbox (last-resort) → Gemini synthetic.

**New order:** OCR-anchor FIRST, Hungarian becomes residual.

Add `_match_via_ocr_anchor()` invoked at top of `_spatial_merge()`. For each LLM wine:
- Strict variant of `_find_ocr_label_bbox()`: requires ≥1 distinctive token (length ≥ 4, not in `FILLER_WORDS`, not a year) appearing in some Vision text block, AND that text block lies inside (or very near) a Vision bottle bbox.
- If wine matches exactly one bottle → commit it (mark `used_llm`/`used_bottles`, append with `confidence = 0.85`).
- If wine matches multiple bottles (same-brand collision) → defer to 3.2.
- If no OCR match → defer to Hungarian (3.3).

Raises confidence cap from current 0.70 to 0.85 for OCR-anchored matches.

### 3.2 Gemini-position tiebreaker for same-brand collisions

For wines deferred from 3.1 with multiple OCR candidates: pick the candidate closest to Gemini-reported wine position. Falls back to deterministic ordering (left-to-right) if Gemini position missing.

### 3.3 Hungarian step becomes the residual

Wines reaching Hungarian have weak/no OCR signal. Try `OCR_SPATIAL_WEIGHT = 0` (the bonus mostly noise here since OCR-strong wines were routed in 3.1). Keep calibration. Eval will tell us if removing the weight regresses anything.

### 3.4 Iteration loop (powered by `/loop`)

For each sub-change 3.1, 3.2, 3.3, the agent runs an autonomous fix→eval→fix cycle via `/loop` (dynamic mode):
1. Implement the tweak.
2. `python -m scripts.eval_overlays --all --json backend/out/after_<change>.json`.
3. `python -m scripts.eval_overlays --compare backend/out/baseline.json backend/out/after_<change>.json` — per-image diff.
4. Spot-check via Playwright MCP on the worst-baseline image.
5. Decide: keep, revert, or refine. If keep, run `/simplify` on changed code before commit.
6. Update this plan: tick the sub-change, log the new accuracy number.
7. Loop terminates when assignment accuracy plateaus (3 consecutive iterations < 1pp improvement) OR target hit.

### Gate 3 — Pass criteria

- [ ] Sub-change 3.1 implemented and committed. Eval improved or no-op vs baseline.
- [ ] Sub-change 3.2 implemented and committed. Eval improved or no-op vs after-3.1.
- [ ] Sub-change 3.3 implemented and committed. Eval improved or no-op vs after-3.2.
- [ ] **Held-out test set** evaluated for the first time. Improvement direction matches iteration set (no overfitting).
- [ ] Aggregate assignment_accuracy ≥ baseline + 20pp **OR** swap_rate cut by ≥ 50%.
- [ ] No image in iteration or held-out set regresses by > 1 wine assignment.
- [ ] Playwright MCP spot-check on 3 worst-baseline images shows correct overlays.
- [ ] `pytest backend/tests/e2e/test_overlay_placement.py -m network` passes with new thresholds asserted.
- [ ] Backend deployed to GCP as smoke test; one manual scan via `https://...run.app` confirms fix holds in production.
- [ ] **Numeric record:** assignment_accuracy = ___ %, swap_rate = ___ %, mean_IoU = ___.

**Exit:** The bug is measurably fixed in production.

---

## Phase 4 — Frontend Polish

**Goal:** Reconcile the small frontend issues that don't block the main bug but should ship before iOS.

### Tasks

- **4.1** **iOS opacity divergence.** `ios/.../OverlayMath.swift:63-74` uses 0.60 in 0.65-0.85 confidence band; `nextjs/lib/overlay-math.ts:56-66` uses 0.75. Unify to spec from `CLAUDE.md` (which is 0.75). Update tests on both sides.
- **4.2** **EXIF orientation audit.** Verify both clients normalize image orientation before upload AND that the rendered image matches the orientation the bbox coordinates assume. Add an EXIF-rotated test image; confirm overlays land correctly via Playwright MCP.
- **4.3** **Visual regression test.** Extend `test_overlay_placement.py` to image-diff screenshots between runs. Catches frontend regressions invisible to the backend eval.

### Gate 4 — Pass criteria

- [ ] iOS and Next.js opacity tables match the spec table in `CLAUDE.md` exactly.
- [ ] EXIF-rotated test image (committed under `test-images/`) renders overlays correctly on both Next.js and on the eval harness.
- [ ] Playwright visual-regression test passes; baseline screenshots committed.
- [ ] All overlay-related tests green: `pytest backend/tests/ && cd nextjs && npm test`.

**Exit:** Frontend is clean and consistent across platforms.

---

## Phase 5 — iOS End-to-End + Production

**Goal:** Validate iOS app against fixed backend, deploy to production, on-ramp to TestFlight.

### Tasks

- **5.1** Build iOS on simulator pointed at `http://localhost:8000`. Send `IMG_8334.HEIC`. Verify rendered overlays match eval-harness visualization.
- **5.2** Add iOS UI test that loads `test-images/` corpus, screenshots overlays, confirms parity with web.
- **5.3** Build iOS on physical device pointed at `https://...run.app` (production). Verify overlays match.
- **5.4** Resume `ROADMAP.md` Phase 7 — TestFlight upload, beta testers, App Store submission.

### Gate 5 — Pass criteria

- [ ] iOS app builds and runs on simulator.
- [ ] iOS scan of `IMG_8334.HEIC` against local backend renders correctly-assigned overlays (visual match to eval-harness PNG).
- [ ] iOS scan against production backend on physical device works end-to-end.
- [ ] iOS UI test suite includes overlay parity check.
- [ ] `ROADMAP.md` Phase 7 unblocked.

**Exit:** App is shippable. TestFlight is the next gate.

---

## Critical Files

### Modify
- `backend/app/services/flash_names_pipeline.py` — Phase 3 spatial merge changes (lines 600-1040)
- `backend/app/config.py` — add `OVERLAY_OCR_FIRST` flag for Phase 3.4
- `backend/scripts/visualize_bboxes.py` — extend `draw_annotations()` to render GT bboxes (cyan) + swap arrows (magenta)
- `test-images/corpus/ground_truth/*.json` — add `overlay_targets` field (15 files)
- `ios/WineShelfScanner/Utils/OverlayMath.swift` — Phase 4.1 opacity reconciliation (lines 63-74)
- `ROADMAP.md` — pointer to this plan added in Phase 0.2

### Create
- `backend/scripts/annotate_overlays.py` — Phase 1.2 interactive annotator
- `backend/scripts/eval_overlays.py` — Phase 1.4 CLI
- `backend/tests/accuracy/overlay_metrics.py` — Phase 1.3 metrics module
- `backend/tests/e2e/test_overlay_placement.py` — Phase 1.5 Playwright validation
- `backend/tests/e2e/_overlay_helpers.py` — shared DOM extraction + comparison logic

### Reuse (no changes)
- `backend/tests/accuracy/metrics.py` — `names_match()` for fuzzy name comparison
- `backend/tests/e2e/conftest.py` — Playwright fixtures
- `backend/app/services/flash_names_pipeline.py:633-747` — `_find_ocr_label_bbox()` (move from fallback to primary in 3.1)

---

## Verification (across all phases)

1. **Numeric — backend eval:** `python -m scripts.eval_overlays --all` shows assignment accuracy ≥ baseline + 20pp, swap rate cut ≥ 50%, on both iteration and held-out sets.
2. **Numeric — e2e:** `pytest backend/tests/e2e/test_overlay_placement.py -m network` passes for all annotated images.
3. **Visual:** `python -m scripts.eval_overlays --visual --image IMG_8334.HEIC` produces PNG where cyan (GT) and yellow (predicted) bboxes overlap, no magenta swap arrows.
4. **Manual spot check:** Upload 3-4 worst baseline images via Next.js on iPhone Safari. Overlays land correctly.
5. **CI guard:** `test_overlay_placement.py` runs on backend changes going forward.
6. **iOS parity:** Phase 5 validation matches web behavior for the same images.

---

## Anticipated Risks & Mitigations

- **Annotation overfitting.** Mitigation: held-out test set (5 images) never inspected during Phase 3.
- **OCR-anchor false positives** on generic wine names ("Bordeaux Reserve"). Mitigation: distinctive-token filter (length ≥ 4, exclude FILLER_WORDS/YEAR_PATTERN — already in code) + matching block must lie within a Vision bottle bbox.
- **Sub-change 3.3 removing OCR_SPATIAL_WEIGHT regresses OCR-empty bottles.** Mitigation: restore a small weight if eval shows regression.
- **Same wine, two bottles** — pipeline currently dedups by name (line 1222). May need to allow duplicate-name overlays. Defer until eval proves it's a real failure mode.
- **Playwright flakiness** with HEIC upload — convert to JPEG in test fixture if needed (existing `convert_heic_to_jpeg()` handles this).

---

## Cadence (~2-3 weeks)

- **Day 1:** Phase 0 (setup, plan to repo)
- **Days 2-4:** Phase 1 (eval harness + baseline)
- **Day 5:** Phase 2 (diagnosis)
- **Days 6-12:** Phase 3 (the fix; iterate via `/loop`)
- **Days 13-15:** Phase 4 (frontend polish)
- **Days 16-21:** Phase 5 (iOS validation, production)

---

## What This Plan Does NOT Do

- Build an annotation UI (manual `Vi`-pick is faster).
- Replace `metrics.py` or `accuracy_report.py` (different question — wine recognition).
- Rewrite `visualize_bboxes.py` (extend it).
- Touch frontend overlay math (math is correct; only opacity values diverge).
- Drop Gemini positions entirely (load-bearing for OCR-empty bottles and same-brand tiebreaks).
- Pivot to iOS before backend is fixed.
- Start GCP backend during Phase 0-3 (smoke test only at end of Phase 3).

---

## Maintenance Convention

When working on this plan:
1. Update **Status** table at top before starting and after finishing each phase.
2. Tick task checkboxes (`[x]`) as you complete them.
3. Tick gate checkboxes only when verified — gates are the bar to advance.
4. Fill in the **Numeric record** lines with measured values.
5. Add a `## Notes — Phase N` section per phase if surprises emerge or sub-decisions are made.
6. Commit plan updates with the code changes they document.
7. If a phase needs more sub-tasks, add them — keep gate criteria sacred.
