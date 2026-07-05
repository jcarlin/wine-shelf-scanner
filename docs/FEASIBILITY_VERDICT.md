# Feasibility Verdict — Rating Overlays on the Correct Bottles

> **Status: LIVING DOCUMENT — verdict not yet reached.** This file accumulates evidence during the
> feasibility loop and becomes final at Gate 3. See `FEASIBILITY_RUN_LOG.md` for round-by-round state.

## The question

Is it technically and economically feasible to reliably highlight the best-rated wines on a shelf
photo — with the star landing on the right bottle — and can we prove it in the Next.js webapp?
"Correct" is defined by rendered pixels: the badge the user sees must sit on, or right next to,
the correct bottle. Showing only the top ~10 rated wines is an allowed simplification.

## Verdict

**TBD** (Gate 3). Requires: accuracy bar met on held-out images with rendered visual proof,
measured cost/scan under ceiling, measured e2e latency under ceiling.

## Evidence so far

### Round 0 baseline — current production architecture (single LLM call, Sonnet 4.6)

Measured 2026-07-04 on the 10-image / 64-target overlay corpus (`backend/out/round0b_sonnet46_8k.json`):

| Axis | Measured | Notes |
|---|---|---|
| Overlay accuracy | **31.2%** (swap 17.2%, miss 51.6%) | Old multi-stage pipeline scored 45.3% on the same corpus — the single-LLM pivot regressed placement. |
| Cost / scan | **$0.0906 mean** ($0.019–$0.127) | From per-call token logs × Anthropic pricing. Docs claimed $0.02–0.04; true only for sparse shelves. |
| Latency (LLM call) | **52.7s mean, 76.6s max** | Output tokens scale with bottle count. E2E webapp ~30–45s on the sparsest image. Product promise is <10s. |
| Reliability | 2/10 images return **zero** overlays at max_tokens=8000; **8/10** at the shipped 2500 | Truncated JSON → parse failure → empty scan. |

**Conclusion so far:** the current architecture fails all three feasibility axes as-is.
This does NOT settle the feasibility question — it settles that *this* architecture (one verbose
LLM call doing detection + OCR + rating in one JSON) is not the shape that clears the bar.
Candidate architectures are evaluated at Gate 2.

### Render-fidelity check (metric validity)

Verified 2026-07-04 via Playwright against the local Next.js + FastAPI stack (IMG_8080):
rendered badge centers match the `(bbox.x + w/2, bbox.y + h*0.25)` anchor formula exactly,
including object-fit letterboxing. The eval harness's anchor-in-bbox metric is therefore a
faithful proxy for rendered placement — **provided ground truth is correct**, which an audit
must ensure (one corrupted annotation already found and documented in the run log).
Proof artifacts: `backend/out/render_checks/render_check_IMG_8080.png` (screenshot),
`backend/out/render_checks/scan_response_IMG_8080.json` (the exact API response that rendered),
`backend/out/visuals/IMG_8080_diff.jpg` (GT boxes on pixels).

### Known contradictions reconciled

- `single_llm_pipeline.py` docstring says default model is Haiku; `config.py` and `.env` say
  Sonnet 4.6. **Verified: Sonnet 4.6 is the effective default.**
- Docs claim single-LLM is "more accurate" than the multi-stage pipeline; the harness says the
  opposite on the full corpus (31.2% vs 45.3%). The doc claim was extrapolated from one image.

## Success bar

**PROPOSED at Gate 1, not yet approved** — see run log / Gate 1 report.

## Unit economics model

TBD (Gate 3). Skeleton: subscription price point × expected scans/user/month vs measured
blended cost/scan; iOS-vs-web cost caveat (on-device detection is free on iOS but unavailable
to the webapp).
