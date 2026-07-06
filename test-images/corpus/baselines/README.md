# Pipeline output baselines

Reference scans from specific models on specific images. Used as upper-bound expectations when evaluating new pipeline outputs.

These are NOT ground truth — they're what a strong model returned, useful for "did we regress?" comparisons.

## Files

| File | Source | Bottles | Notes |
|---|---|---|---|
| `IMG_8080_opus_4_7.json` | Claude Opus 4.7, 2026-05-02 | 15 | Front + back rows. 7/15 bottles partially occluded. |

## Format note

These baselines use `{"x", "y", "w", "h"}` for bboxes (the model returned that format).
The pipeline's API contract uses `{"x", "y", "width", "height"}`.

Convert before direct comparison:
```python
def normalize_bbox(b):
    return {"x": b["x"], "y": b["y"],
            "width": b.get("w") or b["width"],
            "height": b.get("h") or b["height"]}
```

## Adding new baselines

Convention: `<image_basename>_<model_short>_<version>.json`. Examples:
- `IMG_8080_opus_4_7.json`
- `IMG_8334_sonnet_4_6.json`
- `wine1_haiku_4_5.json`

Include a `_meta` block at the top with `model`, `captured` (date), `purpose`, and `bbox_format`.
