# Feasibility Run Log — Overlay Accuracy + Unit Economics

> Running state file for the feasibility loop (see the run prompt). One entry per round.
> A "round" = one full re-measurement of the corpus after a change.
> Resume protocol: read this file + `git log` on `rating-overlays` before starting new work.

## Run status

- **Phase:** Round 0 — baseline measurement (pre-Gate 1)
- **Branch:** `rating-overlays`
- **Started:** 2026-07-04

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
