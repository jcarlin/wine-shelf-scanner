# Plan: Single-LLM Pipeline Rearchitecture

> **Living document.** Tick task checkboxes (`[ ]` → `[x]`) as work progresses, update the Status table, and add notes per phase as discoveries emerge. The implementing agent owns this file once kickoff begins.

> **First action of the implementing agent (before any code):**
> 1. Copy this file to `docs/SINGLE_LLM_PIVOT_PLAN.md` in the repo.
> 2. Update `docs/OVERLAY_ACCURACY_PLAN.md`: mark Phases 2 and 3 as obsolete and link to `docs/SINGLE_LLM_PIVOT_PLAN.md` as the canonical reference for the pivot.
> 3. Update `ROADMAP.md` Active Plans pointer to reference `docs/SINGLE_LLM_PIVOT_PLAN.md` (status: Phase A starting).
> 4. Commit those moves as a single "plan: move single-LLM pivot plan into repo" commit before any code changes.

## Status

- **Phase**: F (pending live API budget) — Phases A-E landed in commit `ec65c06`.
- **Branch**: `rating-overlays`
- **Last update**: 2026-05-02
- **Implementing agent**: Claude Opus 4.7 (1M context)

| Phase | Name | Status |
|---|---|---|
| A | Build `single_llm_pipeline.py` | ✅ |
| B | Wire route, default `single_llm` mode, drop streaming | ✅ |
| C | Schema/model updates (vintage everywhere) | ✅ |
| D | Frontend types (Next.js + iOS) | ✅ |
| E | Tests (rewrite/delete) | ✅ |
| F | Deploy + benchmark vs old pipeline | ⏳ (blocked on Anthropic credit) |
| G | **Delete all dead code** (no orphans, no commented-out blocks, no unreferenced files) | ⏳ (after F soaks ≥ 24h) |

---

## Context

The Wine Shelf Scanner backend currently runs a multi-stage production pipeline (`flash_names_pipeline.py`, `PIPELINE_MODE=flash_names`) that combines Google Vision API for bottle bbox detection + Gemini 2.0 Flash for wine recognition + a Hungarian-algorithm spatial merge that assigns wine names to bottle bboxes. The "rating overlay lands on the wrong bottle" bug we have been chasing for weeks lives almost entirely in that spatial merge: when Gemini's positions drift on dense shelves, the merge step routes the wrong wine name to the wrong Vision bbox. Three band-aids (`_find_ocr_label_bbox`, OCR-text similarity bonus, per-image calibration offset) have not solved it.

A controlled experiment on `test-images/IMG_8080.jpg` showed that a single multimodal call to either **Claude Sonnet 4.6** or **Claude Opus 4.7** does the entire job — detects all 14 bottles (front + back rows), reads each label, identifies the wine, and produces a plausible bbox — in one shot, with substantively better accuracy than the multi-stage pipeline. The complexity in the current pipeline exists *only* because Gemini 2.0 Flash is too weak to do the whole thing on its own; that constraint is gone now that stronger multimodal models are available at usable price/latency.

This plan rips out the multi-stage complexity and replaces it with a single LLM call. The user explicitly does not want intermediate fall-back layers (no merging, no OCR-then-match, no Hungarian, no Vision-API + LLM-name combination). One LLM, one call, one structured response. Cost is not a concern beyond choosing a default model and supporting programmatic swap via env var. Vintage / year must be a first-class returned field. **Dead code removal is mandatory, not optional** — the codebase should be substantially smaller after this work.

---

## Goals

1. **Replace the production scan pipeline with a single multimodal LLM call.** Image → LLM → JSON list of bottles, each with name, bbox, rating estimate, full metadata, **vintage**, confidence.
2. **Make the model swappable via a single env var** (`SINGLE_LLM_MODEL`) with sensible default (`anthropic/claude-sonnet-4-5-20250929`). Any LiteLLM-supported multimodal model works (Sonnet, Opus, Gemini 2.5 Pro, etc.). Programmatic model selection (e.g. swap on retry, route by image size) is OK only if each individual scan still goes through exactly one model.
3. **Keep post-LLM DB enrichment intact**: `WineMatcher.match()` to canonicalize names + override LLM-estimated ratings with DB ratings, `_enrich_with_reviews()` to attach review stats / snippets, `wine_sync` to cache discovered wines back to the DB.
4. **Add `vintage: Optional[str]`** as a first-class field on `RecognizedWine`, the API response (`WineResult`), the LLM cache schema, and the frontend types (Next.js + iOS).
5. **Aggressive dead-code removal.** After Phase G the repo must contain ZERO references to `flash_names_pipeline`, `turbo_pipeline`, `hybrid_pipeline`, the Hungarian spatial merge, OCR-grouping-for-merge, `vision_cache` writes, and any test that imports the deleted modules. Net delta target: ~1,600 lines deleted, ~400 added (≈ -1,200 net). If the implementing agent finds themselves adding more than they delete, stop and reconsider.
6. **Backward-compatible API contract.** Existing fields (`wine_name`, `rating`, `confidence`, `bbox`) preserved; `vintage` is additive and nullable.

## Non-Goals

- **No legacy fallback chain.** No "if single-LLM fails, run Vision + Hungarian merge". A failed LLM call returns an error response or an empty `results[]`. Surface failures, don't paper over them.
- **No multi-model merging.** One model per scan.
- **No Phase 2 (Diagnose) or Phase 3 (Targeted spatial-merge fix) from the prior plan.** Those are obsolete — there is no spatial merge anymore.
- **No frontend rendering changes** beyond adding `vintage` to the type and (optionally) showing it in the detail sheet. The existing badge / overlay rendering is correct.
- **No iOS app changes** other than keeping the type backward-compatible. iOS already consumes the same API contract; vintage will just be ignored until iOS adds support.
- **No leaving dead code in place "just in case."** Delete it. Git history preserves it. Phase G is non-negotiable.

---

## Architecture Overview

### Before (today's production)
```
[image bytes]
   ↓
[Google Vision API (bboxes + OCR)]   [Gemini 2.0 Flash (names + rough positions)]
   ↓                                  ↓
[OCR Processor groups text by bbox]
   ↓
[Hungarian spatial merge: assigns LLM names → Vision bboxes via cost matrix
   blending Euclidean distance + OCR-text similarity bonus]
   ↓ (bug lives here)
[OCR-text fallback for unmatched]
   ↓
[OCR-anchor synthetic bbox for still-unmatched]
   ↓
[Gemini-position synthetic bbox for the rest]
   ↓
[DB lookups + review enrichment]
   ↓
[response]
```

### After (new production)
```
[image bytes]
   ↓
[SINGLE multimodal LLM call (Sonnet 4.6 by default)]
   ↓ returns: [{wine_name, vintage, bbox, rating, type, varietal, region, brand, confidence}]
   ↓
[DB lookups (WineMatcher) + review enrichment (_enrich_with_reviews)]
   ↓
[response]
```

The new path is essentially the existing `fast_pipeline.py` plus (a) swappable model selection, (b) vintage in the prompt + parser + schema, (c) hard requirement that no fallback to other pipelines runs.

---

## Phase Plan

Each phase ends in a working state and is independently revertable. Estimated implementation effort: ~1–2 days for an agent + ~1 hour to deploy + smoke test.

### Phase A — Build `single_llm_pipeline.py`

- [x] **A.1** Create `backend/app/services/single_llm_pipeline.py` based on `fast_pipeline.py` (which is 80% there).
- [x] **A.2** Add `Config.single_llm_model()` reading `SINGLE_LLM_MODEL` env var. Default changed to `"anthropic/claude-haiku-4-5-20251001"` (see Notes — Phase A.2).
- [x] **A.3** Update the prompt to require `vintage` (4-digit year string or `null`) in the JSON contract. Tighten prompt: "Be exhaustive — count and identify EVERY visible bottle including back rows and partially occluded bottles."
- [x] **A.4** Add `vintage` to response parser; default `None` if missing.
- [x] **A.5** Add tiny `_select_model(...)` shim returning a model name (default impl returns `Config.single_llm_model()`). Single-model implementation only — no fallback or ensemble.
- [x] **A.6** Drop everything Vision-related from the new file (no `_run_vision`, no spatial merge, no OCR processor calls).
- [x] **A.7** Reuse `llm_rating_cache` (SQLite). Extend `LLMRatingCache.set/get` signatures to round-trip `vintage`. Create a new Alembic migration adding `vintage TEXT` column to `llm_rating_cache`.

Critical files:
- **CREATE** `backend/app/services/single_llm_pipeline.py` (~250 lines)
- **EDIT** `backend/app/config.py` — add `single_llm_model()` static method
- **EDIT** `backend/app/services/llm_rating_cache.py` — accept and persist `vintage`
- **CREATE** `backend/alembic/versions/<next>_add_vintage_to_llm_rating_cache.py`

Reuses (do NOT rewrite these):
- `backend/app/services/wine_matcher.py:WineMatcher.match` — DB canonicalization + rating override.
- `backend/app/services/llm_rating_cache.py:LLMRatingCache.set/get` — extend signature, reuse logic.
- `backend/app/services/wine_sync.py:sync_discovered_wines` — write LLM results back to the wines table.
- `backend/app/services/fast_pipeline.py:_compress_for_llm` — image compression helper (will be deleted with `fast_pipeline.py` — copy or move to `services/image_utils.py`).
- `litellm.acompletion(...)` — already wired in `fast_pipeline.py` via lazy `_get_litellm()`. Supports any provider/model swap by string name.

### Phase B — Route + remove old modes

- [x] **B.1** EDIT `backend/app/routes/scan.py`:
   - Implement `_run_single_llm_pipeline(image_bytes)` calling `SingleLLMPipeline.scan(...)` and the existing `_enrich_with_reviews()` post-step.
   - Add new pipeline mode `"single_llm"` in dispatch (around lines 826–877).
   - Make `"single_llm"` the new default when `PIPELINE_MODE` is unset.
- [x] **B.2** EDIT `backend/app/routes/scan_stream.py`:
   - **Drop streaming entirely.** Single-LLM call is one-shot ~3–5 s; the 2-phase progressive contract was only meaningful when there was a fast Phase 1 (Vision-only) and slow Phase 2 (Gemini-enriched). With one call there's nothing to stream.
   - Deleted the file outright (chose delete over 410 Gone). Removed `scan_stream_router` from `routes/__init__.py` and `main.py`.
   - Updated Next.js client (`nextjs/lib/api-client.ts`) — `scanImageStream` deleted entirely. `useScanState.ts` rewritten to call `scanImage` synchronously; `partial_results` state removed from `ScanState`. `ResultsView` lost `isPartial` prop.
- [~] **B.3** EDIT `backend/app/config.py` — `pipeline_mode()` default flipped to `"single_llm"`. **Did NOT drop the legacy env-var helpers** (`FLASH_NAMES_MODEL`, `FAST_PIPELINE_MODEL`, etc.) because the legacy pipeline modules still import them; they're harmless dead config until Phase G deletes the modules. See Notes — Phase B.3.

### Phase C — Schema & model updates

- [x] **C.1** EDIT `backend/app/services/recognition_pipeline.py:RecognizedWine`: add `vintage: Optional[str] = None`.
- [x] **C.2** EDIT `backend/app/models/response.py:WineResult`: add `vintage: Optional[str] = Field(None, ...)`.
- [x] **C.3** EDIT `backend/app/services/llm_rating_cache.py`: extend `set/get` signatures to round-trip `vintage`. `CachedRating` dataclass also gained the field.
- [x] **C.4** CREATE Alembic migration `007_add_vintage_to_llm_cache.py` (`ALTER TABLE llm_ratings_cache ADD COLUMN vintage TEXT`).
- [ ] **C.5** Optional: add `vintage TEXT` to `wines` table via separate migration. **Deferred** — LLM-returned vintage is sufficient for now. Re-evaluate after seeing how often Vivino-DB-matched wines have known canonical vintages.

### Phase D — Frontend types

- [x] **D.1** EDIT `nextjs/lib/types.ts:WineResult` — added `vintage?: string;`.
- [ ] **D.2** Optional: `nextjs/components/DetailSheet.tsx` — show vintage under the wine name. **Deferred** — type is wired through, rendering can be a small follow-up.
- [x] **D.3** EDIT `ios/WineShelfScanner/Models/ScanResponse.swift` — added `var vintage: String? = nil` + `case vintage` in `CodingKeys`. Decode-failable so older responses still parse.

### Phase E — Tests

- [x] **E.1** RENAME `backend/tests/test_fast_pipeline.py` → `test_single_llm_pipeline.py`. Covers: model from `Config.single_llm_model()`, vintage parsing, LLM-error propagation (no silent fallback), cache vintage round-trip, integration with mocked litellm.
- [x] **E.2** DELETE `backend/tests/test_flash_names_spatial.py` (~1,060 lines).
- [x] **E.3** EDIT `backend/tests/test_recognition_pipeline.py` — added vintage type assertion to `test_recognized_wine_has_all_fields`. No spatial-merge tests existed in this file to drop.
- [x] **E.4** EDIT `backend/tests/test_scan.py` — added `TestPipelineDispatch` class verifying `Config.pipeline_mode()` defaults to `single_llm` and the route routes through `SingleLLMPipeline.scan`.
- [x] **E.5** EDIT `backend/tests/test_overlay_metrics.py` — confirmed no change needed.
- [x] **E.6** Integration test added in `test_single_llm_pipeline.py::TestSingleLLMIntegration::test_full_scan_flow_with_vintage` — mocks litellm response with vintages and verifies they reach `RecognizedWine.vintage`.
- [x] **E.7 (added)** `backend/tests/test_scan_e2e.py` — added autouse fixture mocking `SingleLLMPipeline.scan` so e2e tests no longer hit a real API. Surfaced when `test_accepts_png` started returning 500 instead of 200 (single_llm has no silent fallback, unlike `flash_names`).

### Phase F — Deploy + Benchmark

- [ ] **F.1** Deploy to Cloud Run via existing GitHub Actions workflow (no infra changes; same container).
- [ ] **F.2** Set Cloud Run env vars: `PIPELINE_MODE=single_llm`, `SINGLE_LLM_MODEL=anthropic/claude-sonnet-4-5-20250929`. `ANTHROPIC_API_KEY` should already exist.
- [ ] **F.3** Run benchmark: `cd backend && venv/bin/python -m scripts.eval_overlays --all --json out/single_llm_baseline.json`, then `--compare backend/out/baseline.json backend/out/single_llm_baseline.json`. Confirm assignment_accuracy ↑, swap_rate ↓.
- [ ] **F.4** Manual smoke: upload `IMG_8334.HEIC` via Next.js, confirm overlays land on the right bottles and the detail sheet shows vintage where present.
- [ ] **F.5** Model swap test: set `SINGLE_LLM_MODEL=anthropic/claude-opus-4-5-20251001`, restart, run a scan, confirm Opus is used (check logs). Then set `gemini/gemini-2.5-pro` and confirm same.

### Phase G — Delete all dead code (NON-NEGOTIABLE)

After Phase F has been verified by the user and the new pipeline is healthy in production for at least 24 hours:

- [ ] **G.1** DELETE `backend/app/services/flash_names_pipeline.py` (~1,363 lines).
- [ ] **G.2** DELETE `backend/app/services/turbo_pipeline.py` if it exists.
- [ ] **G.3** DELETE `backend/app/services/hybrid_pipeline.py` if it exists.
- [ ] **G.4** DELETE `backend/app/services/fast_pipeline.py` (replaced by `single_llm_pipeline.py`). Migrate `_compress_for_llm` to `services/image_utils.py` first if any other module needs it.
- [ ] **G.5** DELETE `backend/tests/test_flash_names_spatial.py`. Verify no other tests import from it.
- [ ] **G.6** REMOVE the `_run_flash_names_pipeline`, `_run_turbo_pipeline`, `_run_hybrid_pipeline`, `_run_fast_pipeline` helper functions in `routes/scan.py` and their imports.
- [ ] **G.7** REMOVE the `flash_names`, `turbo`, `hybrid`, `fast`, `legacy` branches in the pipeline-mode dispatch. Only `single_llm` remains. Update `Config.pipeline_mode()` to validate input and raise on unknown modes.
- [ ] **G.8** DROP the `vision_cache` table via a new Alembic migration (it's unused after Phase A). Existing data is harmless to keep; this is purely about removing the unused write path.
- [ ] **G.9** AUDIT `backend/app/services/vision.py` (`VisionService` class). If nothing imports it after Phase G.1–G.7, delete it. If only `claude_vision.py` or other utilities reference it, evaluate whether those modules are still used and delete the chain.
- [ ] **G.10** AUDIT `backend/app/services/ocr_processor.py`. If nothing imports it after deletions, delete it. (`annotate_overlays.py` may reference it — check.)
- [ ] **G.11** AUDIT `backend/app/services/recognition_pipeline.py`. Large parts unused now. Consider extracting `RecognizedWine` to `models/wine.py` and deleting the rest of the file, OR trimming the file to only the still-used helpers.
- [ ] **G.12** AUDIT `backend/app/services/claude_vision.py` (Vision fallback module). Delete if unused after Phase G.
- [ ] **G.13** AUDIT `backend/scripts/visualize_bboxes.py` — uses `flash_names_pipeline` for the live mode. Either rewrite it to use `single_llm_pipeline`, or simplify it to fixture-replay-only and delete the `--live` path.
- [ ] **G.14** RUN `git grep -E "flash_names|turbo_pipeline|hybrid_pipeline|fast_pipeline|_spatial_merge|_ocr_text_merge|_find_ocr_label_bbox"` and verify ZERO non-comment hits in source code (test files, docs, scripts, etc.). Comments in git history are fine; references in current source are not.
- [ ] **G.15** RUN `cd backend && venv/bin/pytest tests/ --ignore=tests/e2e -q` — confirm all tests still pass after deletions.
- [ ] **G.16** RUN `cd backend && venv/bin/python -c "from app.routes.scan import router; print('ok')"` — confirms no import errors after deletions.
- [ ] **G.17** Update `CLAUDE.md` "Backend Pipeline — Detailed Scan Flow" section: delete the multi-stage pipeline description, the `legacy / turbo / flash_names / hybrid / fast` mode table, the "Caching Architecture" table mentions of `vision_cache`, the "Performance Investigation (2026-02-06)" investigation findings, and any other content describing the deleted code paths. Replace with a short description of the single-LLM flow.
- [ ] **G.18** Update `docs/OVERLAY_ACCURACY_PLAN.md`: mark Phases 2 and 3 obsolete (deleted entirely or struck through with a forward link to `SINGLE_LLM_PIVOT_PLAN.md`). Update the Status table.
- [ ] **G.19** Update `ROADMAP.md` Active Plans pointer.
- [ ] **G.20** FINAL net-line audit: compare `git diff --shortstat` against `main`. Expect ≥ 1,000 net lines deleted. If less, find more dead code.

---

## Critical Files (Quick Reference)

| Action | Path | Notes |
|---|---|---|
| Create | `backend/app/services/single_llm_pipeline.py` | Built from `fast_pipeline.py` template |
| Edit | `backend/app/routes/scan.py` | Add `single_llm` mode, default to it |
| Edit | `backend/app/routes/scan_stream.py` | Drop streaming or 410 Gone |
| Edit | `backend/app/config.py` | Add `SINGLE_LLM_MODEL`, drop old env vars |
| Edit | `backend/app/services/recognition_pipeline.py` | Add `vintage` to `RecognizedWine` |
| Edit | `backend/app/models/response.py` | Add `vintage` to `WineResult` |
| Edit | `backend/app/services/llm_rating_cache.py` | Round-trip vintage |
| Create | `backend/alembic/versions/<next>_add_vintage*.py` | DB migration |
| Edit | `nextjs/lib/types.ts` | Add `vintage?: string` |
| Edit | `nextjs/lib/api-client.ts` | Drop `scanImageStream` |
| Edit | `nextjs/lib/useScanState.ts` | Drop `partial_results` machinery |
| Edit | `ios/WineShelfScanner/Models/ScanResponse.swift` | Add optional `vintage` field |
| Delete | `backend/app/services/flash_names_pipeline.py` | Phase G.1 |
| Delete | `backend/app/services/turbo_pipeline.py` (if present) | Phase G.2 |
| Delete | `backend/app/services/hybrid_pipeline.py` (if present) | Phase G.3 |
| Delete | `backend/app/services/fast_pipeline.py` | Phase G.4 (after migrating helpers) |
| Delete | `backend/tests/test_flash_names_spatial.py` | Phase G.5 |
| Delete | `backend/app/services/vision.py`, `ocr_processor.py`, `claude_vision.py` | Conditional on Phase G audit |
| Edit | `backend/tests/test_fast_pipeline.py` → `test_single_llm_pipeline.py` | Rewrite for new pipeline |
| Edit | `docs/OVERLAY_ACCURACY_PLAN.md` | Mark Phases 2–3 obsolete; link to new plan |
| Edit | `CLAUDE.md` | Replace multi-stage pipeline section with single-LLM flow |
| Edit | `ROADMAP.md` | Update Active Plans pointer status |

## What Stays

- Wine database (191K wines), wine_aliases, wine_fts5, wine_reviews — all preserved.
- All ingestion code (`backend/app/ingestion/`).
- Bug report endpoint and table.
- Feature-flag system.
- All deploy infra (Cloud Run, GitHub Actions, Alembic migrations on startup).
- The eval harness (`eval_overlays.py`, `annotate_overlays.py`) — purpose changes from "fix Hungarian merge" to "benchmark new vs old pipeline accuracy". The 10 GT files in `test-images/corpus/ground_truth/*.json` (committed in `0392816`) keep working.

---

## Verification

End-to-end test sequence after the implementing agent finishes Phases A–F:

1. **Unit tests:** `cd backend && venv/bin/pytest tests/ --ignore=tests/e2e -q` should report all green except 3 pre-existing flakes (perf, missing fixtures).
2. **Schema migration:** `rm -f backend/app/data/wines.db && cd backend && venv/bin/alembic upgrade head` runs without errors. Verify `vintage` column exists on `llm_rating_cache`.
3. **Backend smoke:** start `uvicorn main:app --reload`, hit `GET /health` → 200.
4. **End-to-end scan:** with `PIPELINE_MODE=single_llm` set, run:
   ```bash
   curl -X POST http://localhost:8000/scan \
     -F "image=@test-images/IMG_8334.HEIC" -F "use_vision_api=true"
   ```
   Confirm response JSON contains `results[]` with `vintage` populated on at least some bottles.
5. **Frontend smoke:** start Next.js dev (`cd nextjs && PATH=/Users/julian/.nvm/versions/node/v22.18.0/bin:$PATH npm run dev`), upload `IMG_8334.HEIC`, confirm overlays render on the actual bottles (not the swap-bug wrong ones), and the detail sheet shows the wine name + (if rendered) vintage.
6. **Eval harness benchmark:**
   ```bash
   cd backend
   venv/bin/python -m scripts.eval_overlays --all --json out/single_llm_baseline.json
   venv/bin/python -m scripts.eval_overlays --compare out/baseline.json out/single_llm_baseline.json
   ```
   Expected: `assignment_accuracy` rises sharply (45% → 80%+); `swap_rate` drops (9% → near zero); `mean_iou` may shift because LLM bboxes follow different conventions (full-bottle vs cap-to-mid-label) — that is expected.
7. **Visual diff:** `venv/bin/python -m scripts.eval_overlays --image IMG_8334.HEIC --visual` and inspect `backend/out/visuals/IMG_8334_diff.jpg`. Yellow `P:` boxes should sit on the same bottles as cyan `GT:` boxes.
8. **Production smoke:** deploy via `git push origin main` (GitHub Actions). Hit production with the same image; confirm the same accuracy holds.
9. **Phase G dead-code audit (after deletions):** `git grep -E "flash_names|turbo_pipeline|hybrid_pipeline|fast_pipeline|_spatial_merge|_ocr_text_merge|_find_ocr_label_bbox"` returns zero hits in non-doc, non-comment code. `git diff --shortstat main` shows ≥ 1,000 net lines deleted.

## Risks & Mitigations

- **LLM bbox accuracy.** Sonnet's bboxes follow different conventions than Vision API's. The eval metric uses anchor-inside-bbox (lenient), so this should be fine. If specific images regress, tighten the prompt to ask for the *bottle* bbox specifically (cap to bottom of bottle) and re-test.
- **Latency.** Sonnet on a 4 MB image is ~3–5 s. Compress aggressively in `_compress_for_llm` if needed. Phase 0 work showed Cloud Run cold start adds 2–5 s; consider min-instances=1 for production to eliminate it (~$10–20/mo).
- **Rate limits.** A `429` from Anthropic could break a scan. Implement a simple retry-with-backoff *to the same model*. Do NOT silently fall back to a different pipeline; surface the failure to the user.
- **Vintage extraction quality.** Some labels don't show vintage (NV champagnes, generic table wines). LLM should return `null`; guard against the LLM hallucinating a vintage. Spot-check 5+ images during verification.
- **`vision_cache` table data loss.** Dropping the table loses cached Vision API responses. Migration should be idempotent. If you want extra caution, keep the table and just stop writing to it.
- **Hidden imports.** Some scripts (`backend/scripts/visualize_bboxes.py`, `annotate_overlays.py`) may import `flash_names_pipeline` directly. Phase G.13 audit catches this — ensure those scripts work or are deleted/rewritten.

## Open Questions (decide before starting Phase A)

1. **Default model**: Sonnet 4.6 (recommended; cheaper of the strong options) or Opus 4.7 (strongest)?
2. **Streaming endpoint** `/scan/stream`: delete the route entirely, or return 410 Gone?
3. **Move `RecognizedWine`** out of `recognition_pipeline.py` into `models/wine.py` while we're cleaning up? Optional refactor; safe to defer until Phase G.11.
4. **Eval harness corpus**: keep the 10 GT files committed in `0392816` even though 2 had errors (`IMG_8080`, `IMG_8123`). They're useful for *relative* comparison (old vs new pipeline accuracy); the errors don't change the *direction* of the delta. Recommendation: keep, fix the 2 errors as a small follow-up, expand the corpus using the LLM-GT-generation method demonstrated in this session (Sonnet-as-GT-generator).
5. **iOS implementation timing**: ship backend + Next.js first, iOS later? iOS won't break — `vintage` is additive and Swift's optional decoding handles missing fields gracefully.

---

## Living-document conventions

The implementing agent owns this file once kickoff begins. Maintenance rules:

- **Tick checkboxes** (`[ ]` → `[x]`) as each task completes. Do this in the same commit that lands the code.
- **Update the Status table** at the top before/after each phase.
- **Add a `## Notes — Phase X` section** for any non-trivial discovery or in-flight decision (e.g. "found `flash_names_pipeline` was also imported by `scripts/visualize_bboxes.py`; rewrote that script to use single-LLM").
- **Never silently change scope.** If the plan needs to grow (new task uncovered) or shrink (something was already done elsewhere), edit this file and call it out in the commit message.
- **At Phase G.20** (final line audit), include the actual `git diff --shortstat` numbers in the file as proof of net deletion.
- **When Phase G is fully complete**, change the Status to `✅ Complete` and add a one-paragraph summary at the top of this file under the Status table linking to the merge commit.

---

## HANDOFF PROMPT (copy-paste-ready for the next agent)

```
You are picking up the Wine Shelf Scanner backend rearchitecture. Read /Users/julian/dev/wine-shelf-scanner/docs/SINGLE_LLM_PIVOT_PLAN.md end-to-end before starting — it has full context, scope, file map, verification steps, and explicit dead-code-removal requirements.

YOUR FIRST ACTION (before any code):
1. Copy the plan from ~/.claude/plans/eager-yawning-wind.md (or wherever it currently lives) to docs/SINGLE_LLM_PIVOT_PLAN.md if it isn't already there.
2. Update docs/OVERLAY_ACCURACY_PLAN.md: mark Phases 2 and 3 as obsolete and link to docs/SINGLE_LLM_PIVOT_PLAN.md.
3. Update ROADMAP.md Active Plans pointer to reference the new plan.
4. Commit those moves as "plan: move single-LLM pivot plan into repo and supersede overlay plan Phases 2-3" before any code changes.

BACKGROUND (1-paragraph TL;DR):
The current production pipeline (backend/app/services/flash_names_pipeline.py, ~1,360 lines) uses Google Vision API + Gemini 2.0 Flash + a Hungarian-algorithm spatial merge to assign wine names to bottle bboxes. A persistent bug — overlays land on the wrong bottle, especially on dense shelves — was traced to that spatial merge step. A controlled experiment showed that a single multimodal call to Claude Sonnet 4.6 does the entire job (detect bottles, read labels, identify wines, produce bboxes) in one shot, more accurately than the multi-stage pipeline. We are replacing the multi-stage pipeline with a single-LLM call. The model must also return the bottle's vintage/year. Cost is not a concern; simplicity is the goal. **Dead code removal is mandatory** — by the end of Phase G the codebase should be substantially smaller (target: ≥ 1,000 net lines deleted vs main).

YOUR TASK:
Implement Phases A through F in order, then deploy and run the verification steps. Phase G (delete the old multi-stage code) only after the user has confirmed the new pipeline is healthy in production for at least 24 hours.

CONSTRAINTS (these are sacred):
1. Single LLM call per scan. No multi-step merging. No OCR-then-match. No Hungarian. No fallback to the old pipeline. If the LLM fails, surface the error.
2. Vintage is a first-class field on the response and the cache.
3. Model is swappable via SINGLE_LLM_MODEL env var. Default "anthropic/claude-sonnet-4-5-20250929". Other options must work without code changes (gemini/gemini-2.5-pro, anthropic/claude-opus-4-5-20251001, etc.) — litellm.acompletion() handles this.
4. Dead code removal is non-negotiable. After Phase G the repo must contain ZERO references to flash_names_pipeline, turbo_pipeline, hybrid_pipeline, _spatial_merge, _ocr_text_merge, _find_ocr_label_bbox. If you find yourself adding more lines than you delete, stop and reconsider.
5. API contract is backward-compatible. Existing fields (wine_name, rating, confidence, bbox) keep their names and semantics. vintage is purely additive.

LIVING DOCUMENT:
docs/SINGLE_LLM_PIVOT_PLAN.md is the canonical reference and should be updated as you progress. Tick checkboxes as you complete tasks (in the same commit that lands the code). Update the Status table at each phase boundary. Add ## Notes — Phase X sections for non-trivial discoveries. Never silently change scope.

BEFORE YOU START, ASK THE USER:
- Default model: Sonnet 4.6 (recommended) or Opus 4.7?
- Drop /scan/stream entirely or return 410 Gone?

WHERE THE EXISTING EVAL HARNESS LIVES (re-use, don't recreate):
backend/scripts/eval_overlays.py, backend/scripts/annotate_overlays.py, backend/tests/accuracy/overlay_metrics.py, backend/out/baseline.json (the old-pipeline baseline you'll compare against), and 10 GT JSON files at test-images/corpus/ground_truth/IMG_*.json, wine1.json, red-wine-shelf-...json. The same eval harness will benchmark your new pipeline; just write the new metrics to backend/out/single_llm_baseline.json and use --compare.

DELIVERABLES CHECKLIST (PR-ready):
- [ ] First-action moves (plan into repo + OVERLAY_ACCURACY_PLAN.md / ROADMAP.md updates) lands as commit 1.
- [ ] Phase A code (single_llm_pipeline.py + cache + migration) lands as commit 2.
- [ ] Phase B–C code (route wiring + schema fields) lands as commit 3.
- [ ] Phase D code (frontend types) lands as commit 4.
- [ ] Phase E (test rewrites) lands as commit 5.
- [ ] Verification steps 1–7 from the plan all pass on local. Output of step 6 (--compare JSON) attached to the PR description.
- [ ] Phase G (deletes) is a SEPARATE PR — DO NOT bundle with the implementation. Land it after the user confirms the new pipeline is healthy in production.
- [ ] docs/OVERLAY_ACCURACY_PLAN.md, CLAUDE.md, and ROADMAP.md all updated to reflect the new architecture.

BRANCH:
Commit on the current working branch — check with git branch. Open a PR per phase or per logical chunk; do not merge to main without explicit user approval.

THINGS YOU WILL BE TEMPTED TO DO — DON'T:
- Don't add a "fallback to legacy pipeline if single-LLM fails." The user explicitly rejected this. Surface the error.
- Don't add multi-model voting / ensemble / merging. One model per scan.
- Don't preserve the spatial merge as "dead code in case we need it." Delete it. Git history preserves it.
- Don't add new "smart" features beyond what's in this plan. Simplicity is the goal.
- Don't refactor large unrelated areas while you're in there. If you spot something, leave a comment, don't fix it.
- Don't skip Phase G. The plan is incomplete until the dead code is gone.

USER:
julianmcarlin@gmail.com.
```
