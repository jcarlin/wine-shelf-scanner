"""
CLI for overlay placement evaluation.

Usage:
    # Single image
    python -m scripts.eval_overlays --image test-images/IMG_8334.HEIC

    # Whole annotated corpus
    python -m scripts.eval_overlays --all

    # Save baseline JSON
    python -m scripts.eval_overlays --all --json backend/out/baseline.json

    # Compare two runs
    python -m scripts.eval_overlays \
        --compare backend/out/baseline.json backend/out/after_3_1.json

    # Render visual overlay diff (cyan = GT, yellow = predicted, magenta = swap arrow)
    python -m scripts.eval_overlays --image test-images/IMG_8334.HEIC --visual

The script loads the image + ground-truth JSON, runs the production pipeline
(`SingleLLMPipeline.scan`), and scores predictions against `overlay_targets`
using `tests.accuracy.overlay_metrics.score_image`.
"""

import argparse
import asyncio
import io
import json
import sys
import time
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.services.single_llm_pipeline import SingleLLMPipeline  # noqa: E402
from scripts.visualize_bboxes import _load_image  # noqa: E402  # type: ignore
from tests.accuracy.overlay_metrics import (  # noqa: E402
    AggregateMetrics,
    ImageMetrics,
    OverlayPrediction,
    OverlayTarget,
    PrecisionView,
    aggregate,
    format_aggregate,
    format_per_image_table,
    format_swap_details,
    merge_precision_views,
    precision_view,
    score_image,
)

REPO_ROOT = BACKEND_ROOT.parent
GT_DIR = REPO_ROOT / "test-images" / "corpus" / "ground_truth"
SHELVES_DIR = REPO_ROOT / "test-images" / "corpus" / "shelves"
ROOT_IMAGES_DIR = REPO_ROOT / "test-images"
OUT_DIR = BACKEND_ROOT / "out"


# ---------------------------------------------------------------------------
# GT loading
# ---------------------------------------------------------------------------

def _resolve_image_path(image_file: str) -> Path:
    """Find an image by name across the supported test-image locations."""
    candidates = [
        Path(image_file),
        ROOT_IMAGES_DIR / image_file,
        SHELVES_DIR / image_file,
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(f"Image not found in any expected location: {image_file}")


def _load_gt_targets(gt_path: Path) -> tuple[Path, list[OverlayTarget]]:
    with open(gt_path) as f:
        data = json.load(f)
    image_file = data.get("image_file")
    if not image_file:
        raise ValueError(f"GT {gt_path} missing 'image_file' key")
    raw_targets = data.get("overlay_targets") or []
    targets = [
        OverlayTarget(
            wine_name=t["wine_name"],
            bbox=t["bbox"],
            bbox_kind=t.get("bbox_kind", "bottle"),
            distinctive_tokens=t.get("distinctive_tokens", []) or [],
        )
        for t in raw_targets
    ]
    image_path = _resolve_image_path(image_file)
    return image_path, targets


def _gt_files_with_targets() -> list[Path]:
    """Return GT JSONs that have at least one overlay_target."""
    out: list[Path] = []
    for f in sorted(GT_DIR.glob("*.json")):
        try:
            d = json.load(open(f))
        except json.JSONDecodeError:
            continue
        if d.get("overlay_targets"):
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

# When set (via --candidate), _run_pipeline routes to a bake-off candidate from
# scripts.candidates instead of the production SingleLLMPipeline. Candidate
# ratings are LLM-estimated (no DB override) — fine for placement scoring.
_ACTIVE_CANDIDATE: Optional[str] = None


async def _run_pipeline(image_path: Path) -> tuple[list[OverlayPrediction], dict]:
    img = _load_image(str(image_path))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    image_bytes = buf.getvalue()

    if _ACTIVE_CANDIDATE:
        from scripts.candidates import CANDIDATES
        fn = CANDIDATES[_ACTIVE_CANDIDATE]
        t0 = time.perf_counter()
        result = await fn(image_bytes, image_path.name)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        predictions = [
            OverlayPrediction(
                wine_name=p.wine_name,
                bbox=p.bbox,
                confidence=p.confidence,
                source=_ACTIVE_CANDIDATE,
                rating=p.rating,
            )
            for p in result.predictions
        ]
        info = {
            "elapsed_ms": elapsed_ms,
            "candidate": _ACTIVE_CANDIDATE,
            "usage": result.usage,
            "cost_usd": result.total_cost_usd,
            "paid_latency_ms": result.wall_ms or result.total_latency_ms,
            "recognized_count": len(predictions),
            "notes": result.notes,
        }
        return predictions, info

    pipeline = SingleLLMPipeline()
    t0 = time.perf_counter()
    result = await pipeline.scan(image_bytes, image_id=image_path.name)
    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    predictions: list[OverlayPrediction] = []
    for rw in result.recognized_wines:
        bt = rw.bottle_text
        if bt is None or bt.bottle is None or bt.bottle.bbox is None:
            continue
        bbox = bt.bottle.bbox
        predictions.append(
            OverlayPrediction(
                wine_name=rw.wine_name,
                bbox={
                    "x": bbox.x,
                    "y": bbox.y,
                    "w": bbox.width,
                    "h": bbox.height,
                },
                confidence=rw.confidence,
                source="single_llm",
                rating=rw.rating,
            )
        )

    info = {
        "elapsed_ms": elapsed_ms,
        "model": result.timings.get("model"),
        "llm_call_ms": result.timings.get("llm_call_ms"),
        "recognized_count": len(result.recognized_wines),
    }
    return predictions, info


# ---------------------------------------------------------------------------
# Visual diff rendering
# ---------------------------------------------------------------------------

def _render_visual_diff(
    image_path: Path,
    targets: list[OverlayTarget],
    predictions: list[OverlayPrediction],
    metrics: ImageMetrics,
    output_path: Path,
    vision_bottles: Optional[list[dict]] = None,
) -> None:
    """Save a diff PNG: cyan = GT bboxes, yellow = predictions, magenta = swap
    arrows, and (when ``vision_bottles`` is provided) green = Vision-detected
    bottle bboxes labeled with their OCR fingerprint. Reading OCR fingerprint
    next to the predicted overlay name makes swap mismatches obvious to the eye.
    """
    from PIL import Image, ImageDraw, ImageFont  # noqa: WPS433

    img = _load_image(str(image_path)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    img_w, img_h = img.size

    line_width = max(2, int(min(img_w, img_h) * 0.0035))

    # Pick a font that scales with the image
    base_size = max(14, int(min(img_w, img_h) * 0.014))
    font: object = ImageFont.load_default()
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            font = ImageFont.truetype(path, base_size)
            break
        except (OSError, ValueError):
            continue
    small_font: object = ImageFont.load_default()
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            small_font = ImageFont.truetype(path, max(10, base_size - 4))
            break
        except (OSError, ValueError):
            continue

    def to_px(bbox: dict) -> tuple[int, int, int, int]:
        x1 = int(bbox["x"] * img_w)
        y1 = int(bbox["y"] * img_h)
        x2 = int((bbox["x"] + bbox["w"]) * img_w)
        y2 = int((bbox["y"] + bbox["h"]) * img_h)
        return x1, y1, x2, y2

    def labeled_text(x: int, y: int, text: str, color: tuple, fnt) -> None:
        bbox = draw.textbbox((x, y), text, font=fnt)
        pad = 2
        draw.rectangle(
            [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
            fill=(0, 0, 0, 180),
        )
        draw.text((x, y), text, fill=color, font=fnt)

    # 0. Vision bottles + OCR fingerprint — green. Lets a human eyeball whether
    #    the pipeline put the right name on the right bottle.
    BOTTLE_COLOR = (0, 220, 90, 220)
    if vision_bottles:
        for vi, vb in enumerate(vision_bottles):
            x1, y1, x2, y2 = to_px({"x": vb["x"], "y": vb["y"], "w": vb["w"], "h": vb["h"]})
            draw.rectangle([x1, y1, x2, y2], outline=BOTTLE_COLOR, width=max(1, line_width - 1))
            labeled_text(x1, y2 + 4, f"V{vi}", BOTTLE_COLOR, small_font)
            ocr = (vb.get("ocr_text") or "").replace("\n", " ").strip()
            if ocr:
                labeled_text(x1, y2 + 4 + base_size + 2, ocr[:36], BOTTLE_COLOR, small_font)

    # 1. GT bboxes — cyan
    GT_COLOR = (0, 200, 220, 240)
    for t in targets:
        x1, y1, x2, y2 = to_px(t.bbox)
        draw.rectangle([x1, y1, x2, y2], outline=GT_COLOR, width=line_width)
        labeled_text(x1, max(0, y1 - base_size - 4), f"GT:{t.wine_name[:34]}", GT_COLOR, font)

    # 2. Predictions — yellow
    PRED_COLOR = (255, 220, 0, 240)
    for p in predictions:
        x1, y1, x2, y2 = to_px(p.bbox)
        draw.rectangle([x1, y1, x2, y2], outline=PRED_COLOR, width=line_width)
        ax = int(p.anchor[0] * img_w)
        ay = int(p.anchor[1] * img_h)
        draw.ellipse(
            [ax - 6, ay - 6, ax + 6, ay + 6], outline=PRED_COLOR, width=line_width
        )
        labeled_text(ax + 8, ay - base_size, f"P:{p.wine_name[:34]}", PRED_COLOR, small_font)

    # 3. Swap arrows — magenta from predicted anchor to expected GT center
    SWAP_COLOR = (255, 60, 200, 240)
    for o in metrics.outcomes:
        if o.classification != "swap" or o.matched_prediction is None:
            continue
        ax = int(o.matched_prediction.anchor[0] * img_w)
        ay = int(o.matched_prediction.anchor[1] * img_h)
        gt_cx = int((o.target.bbox["x"] + o.target.bbox["w"] / 2) * img_w)
        gt_cy = int((o.target.bbox["y"] + o.target.bbox["h"] / 2) * img_h)
        draw.line([(ax, ay), (gt_cx, gt_cy)], fill=SWAP_COLOR, width=line_width)

    out = Image.alpha_composite(img, overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(output_path), "JPEG", quality=92)


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def _load_metrics_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _format_compare(before: dict, after: dict) -> str:
    """Print a side-by-side diff of two metrics JSON files."""
    lines = ["Compare:"]
    lines.append(f"  before: {before.get('source_file', '?')}")
    lines.append(f"  after : {after.get('source_file', '?')}")
    lines.append("")
    lines.append(f"{'metric':<28}{'before':>12}{'after':>12}{'delta':>12}")
    lines.append("-" * 64)

    def row(name: str, b: float, a: float, fmt: str = "{:.3f}") -> str:
        delta = a - b
        return f"{name:<28}{fmt.format(b):>12}{fmt.format(a):>12}{fmt.format(delta):>+12}"

    bagg = before.get("aggregate", {})
    aagg = after.get("aggregate", {})
    lines.append(row("assignment_accuracy", bagg.get("assignment_accuracy", 0.0), aagg.get("assignment_accuracy", 0.0)))
    lines.append(row("swap_rate", bagg.get("swap_rate", 0.0), aagg.get("swap_rate", 0.0)))
    lines.append(row("miss_rate", bagg.get("miss_rate", 0.0), aagg.get("miss_rate", 0.0)))
    lines.append(row("mean_iou", bagg.get("mean_iou", 0.0) or 0.0, aagg.get("mean_iou", 0.0) or 0.0))

    # Per-image swap_rate diff
    by_id_b = {r["image_id"]: r for r in before.get("per_image", [])}
    by_id_a = {r["image_id"]: r for r in after.get("per_image", [])}
    all_ids = sorted(set(by_id_b) | set(by_id_a))
    lines.append("")
    lines.append("Per-image swap_rate change:")
    for image_id in all_ids:
        b = by_id_b.get(image_id, {}).get("swap_rate", 0.0)
        a = by_id_a.get(image_id, {}).get("swap_rate", 0.0)
        delta = a - b
        marker = "  "
        if delta > 0.001:
            marker = "↑↑"
        elif delta < -0.001:
            marker = "↓↓"
        lines.append(f"  {marker} {image_id[:60]:<60}{b:>7.2f}{a:>7.2f}{delta:>+8.2f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Result serialisation
# ---------------------------------------------------------------------------

def _outcome_to_dict(o) -> dict:
    pred = None
    if o.matched_prediction is not None:
        pred = {
            "wine_name": o.matched_prediction.wine_name,
            "bbox": o.matched_prediction.bbox,
            "anchor": o.matched_prediction.anchor,
            "confidence": o.matched_prediction.confidence,
            "source": o.matched_prediction.source,
        }
    swap_target = None
    if o.swap_target is not None:
        swap_target = {
            "wine_name": o.swap_target.wine_name,
            "bbox": o.swap_target.bbox,
        }
    return {
        "target_wine_name": o.target.wine_name,
        "target_bbox": o.target.bbox,
        "classification": o.classification,
        "iou": o.iou,
        "matched_prediction": pred,
        "swap_target": swap_target,
    }


def _image_metrics_to_dict(m: ImageMetrics, info: dict) -> dict:
    return {
        "image_id": m.image_id,
        "total_targets": m.total_targets,
        "correct": m.correct,
        "swap": m.swaps,
        "miss": m.misses,
        "assignment_accuracy": m.assignment_accuracy,
        "swap_rate": m.swap_rate,
        "miss_rate": m.miss_rate,
        "mean_iou": m.mean_iou,
        "source_counts": m.source_counts,
        "pipeline_info": info,
        "outcomes": [_outcome_to_dict(o) for o in m.outcomes],
        "unmatched_predictions": [
            {
                "wine_name": p.wine_name,
                "bbox": p.bbox,
                "confidence": p.confidence,
                "source": p.source,
            }
            for p in m.unmatched_predictions
        ],
    }


def _aggregate_to_dict(agg: AggregateMetrics) -> dict:
    return {
        "total_targets": agg.total_targets,
        "correct": agg.correct,
        "swap": agg.swaps,
        "miss": agg.misses,
        "assignment_accuracy": agg.assignment_accuracy,
        "swap_rate": agg.swap_rate,
        "miss_rate": agg.miss_rate,
        "mean_iou": agg.mean_iou,
        "source_counts": agg.source_counts,
    }


# ---------------------------------------------------------------------------
# GT-free swap audit
# ---------------------------------------------------------------------------

def _run_ocr_audit(image_arg: str, render_visual: bool = False) -> None:
    """For every rendered overlay, compare the predicted wine name against the
    OCR text of the Vision bottle whose bbox contains the badge's anchor. No
    ground truth required.

    A LOW similarity is the signal: badge claims wine X, but the label text
    on the bottle the badge is sitting on doesn't mention X — i.e., the user's
    "click star, see wrong wine" experience.
    """
    from rapidfuzz import fuzz

    image_path = _resolve_image_path(image_arg)
    print(f"OCR-AUDIT: {image_path}")
    predictions, info = asyncio.run(_run_pipeline(image_path))

    # Pull cached Vision bottle data (from a prior fixture run)
    fixture_path = BACKEND_ROOT / "out" / "fixtures" / f"{image_path.stem}.fixture.json"
    if not fixture_path.exists():
        print(
            f"  no cached fixture at {fixture_path}.\n"
            "  Run `python -m scripts.annotate_overlays <image> --print-bottles` first "
            "to capture Vision bottle bboxes + OCR text."
        )
        sys.exit(1)
    vision_bottles = json.loads(fixture_path.read_text()).get("vision_bottles", [])

    def bottle_at_anchor(ax: float, ay: float) -> Optional[dict]:
        for vb in vision_bottles:
            if vb["x"] <= ax <= vb["x"] + vb["w"] and vb["y"] <= ay <= vb["y"] + vb["h"]:
                return vb
        return None

    rows: list[dict] = []
    for p in predictions:
        ax, ay = p.anchor
        vb = bottle_at_anchor(ax, ay)
        ocr = (vb.get("ocr_text") if vb else "") or ""
        if ocr:
            sim = max(
                fuzz.token_set_ratio(p.wine_name.lower(), ocr.lower()) / 100.0,
                fuzz.partial_ratio(p.wine_name.lower(), ocr.lower()) / 100.0,
            )
        else:
            sim = 0.0
        rows.append({
            "wine_name": p.wine_name,
            "anchor": (round(ax, 3), round(ay, 3)),
            "vision_bottle": (vision_bottles.index(vb) if vb else None),
            "ocr": ocr[:80],
            "similarity": round(sim, 2),
        })

    rows.sort(key=lambda r: r["similarity"])

    print(
        f"\n{'sim':>5}  {'V':>3}  {'predicted wine':<40}  ocr fingerprint"
    )
    print("-" * 110)
    flagged_low = 0
    flagged_no_bottle = 0
    SWAP_THRESHOLD = 0.55  # below this, predicted wine name shares almost no tokens with bottle OCR
    for r in rows:
        marker = " "
        if r["vision_bottle"] is None:
            flagged_no_bottle += 1
            marker = "?"
        elif r["similarity"] < SWAP_THRESHOLD:
            flagged_low += 1
            marker = "!"
        v_label = "—" if r["vision_bottle"] is None else f"V{r['vision_bottle']}"
        print(
            f"{marker} {r['similarity']:>4.2f}  {v_label:>3}  "
            f"{r['wine_name'][:39]:<40}  {r['ocr'][:60]}"
        )
    total = len(rows)
    print()
    print(
        f"Summary: {total} predictions, "
        f"!= {flagged_low} low-similarity (likely swap), "
        f"?= {flagged_no_bottle} not over any Vision bottle (synthetic bbox)"
    )
    print(
        "Read each '!' row as: 'badge says <predicted wine> but bottle V's OCR "
        "text shares almost no tokens with that name → likely swap'."
    )

    if render_visual:
        # Reuse the visual diff renderer with EMPTY GT — useful when we have no GT
        # but still want a labeled image with predictions + OCR fingerprints.
        out_path = OUT_DIR / "visuals" / f"{image_path.stem}_ocr_audit.jpg"
        _render_visual_diff(
            image_path,
            targets=[],
            predictions=predictions,
            metrics=ImageMetrics(image_id=image_path.name),
            output_path=out_path,
            vision_bottles=vision_bottles,
        )
        print(f"Visual: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _evaluate_one(
    gt_path: Path, render_visual: bool
) -> tuple[ImageMetrics, dict]:
    image_path, targets = _load_gt_targets(gt_path)
    if not targets:
        return ImageMetrics(image_id=gt_path.stem), {"skipped": "no overlay_targets"}
    print(f"  → {image_path.name} (targets={len(targets)})")
    predictions, info = await _run_pipeline(image_path)
    metrics = score_image(image_path.name, targets, predictions)

    view = precision_view(targets, predictions)
    info["precision"] = {
        "on_correct": view.on_correct,
        "wrong_bottle": view.wrong_bottle,
        "off_bottle": view.off_bottle,
        "unjudgeable": view.unjudgeable,
        "badge_precision": view.badge_precision,
        "top3_judged": view.top3_judged,
        "top3_correct": view.top3_correct,
        "top3_precision": view.top3_precision,
    }
    # Per-badge detail (rating rank order) so top-3 failures are diagnosable
    # from the JSON without re-running the scan.
    from tests.accuracy.overlay_metrics import _classify_badge  # noqa: WPS433
    ranked = sorted(predictions, key=lambda p: (p.rating or 0.0, p.confidence), reverse=True)
    info["badges_ranked"] = [
        {
            "wine_name": p.wine_name,
            "rating": p.rating,
            "confidence": p.confidence,
            "anchor": [round(p.anchor[0], 4), round(p.anchor[1], 4)],
            "class": _classify_badge(p, targets, 0.85),
        }
        for p in ranked
    ]

    if render_visual:
        # Pull cached Vision bbox + OCR data so the diff PNG can label each
        # detected bottle with its OCR fingerprint (helps spot swaps by eye).
        fixture_path = BACKEND_ROOT / "out" / "fixtures" / f"{image_path.stem}.fixture.json"
        vision_bottles = None
        if fixture_path.exists():
            try:
                vision_bottles = json.loads(fixture_path.read_text()).get("vision_bottles", [])
            except json.JSONDecodeError:
                vision_bottles = None
        out_path = OUT_DIR / "visuals" / f"{image_path.stem}_diff.jpg"
        _render_visual_diff(
            image_path, targets, predictions, metrics, out_path,
            vision_bottles=vision_bottles,
        )
        info["visual_diff"] = str(out_path)
    return metrics, info


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate overlay placement accuracy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--image",
        help="Single image filename (looked up under test-images/, ground_truth/, shelves/).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run over every GT JSON with overlay_targets.",
    )
    parser.add_argument("--json", help="Write per-image + aggregate metrics JSON.")
    parser.add_argument(
        "--candidate",
        help="Run a bake-off candidate from scripts.candidates instead of the "
             "production pipeline (e.g. c1_lean_sonnet).",
    )
    parser.add_argument(
        "--only",
        help="Comma-separated GT stems to include with --all "
             "(e.g. IMG_8080,IMG_8123). Used to restrict runs to the "
             "iteration set and keep held-out images untouched.",
    )
    parser.add_argument(
        "--visual",
        action="store_true",
        help="Render diff PNGs into backend/out/visuals/.",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="Compare two metrics JSON files.",
    )
    parser.add_argument(
        "--ocr-audit",
        action="store_true",
        help=(
            "Run a GT-free swap audit. For each rendered overlay, fuzzy-match "
            "the predicted wine name against the OCR text of the Vision bottle "
            "the badge sits on. Low similarity flags a likely swap (badge "
            "claims wine X, but the bottle's label OCR doesn't mention X). "
            "Works on any image — no overlay_targets needed."
        ),
    )
    args = parser.parse_args()

    if args.candidate:
        from scripts.candidates import CANDIDATES
        if args.candidate not in CANDIDATES:
            print(f"Unknown candidate '{args.candidate}'. "
                  f"Available: {', '.join(sorted(CANDIDATES))}")
            sys.exit(1)
        global _ACTIVE_CANDIDATE
        _ACTIVE_CANDIDATE = args.candidate

    if args.compare:
        before = _load_metrics_json(Path(args.compare[0]))
        after = _load_metrics_json(Path(args.compare[1]))
        before["source_file"] = args.compare[0]
        after["source_file"] = args.compare[1]
        print(_format_compare(before, after))
        return

    if args.ocr_audit:
        if not args.image:
            print("--ocr-audit requires --image")
            sys.exit(1)
        _run_ocr_audit(args.image, render_visual=args.visual)
        return

    targets_paths: list[Path] = []
    if args.all:
        targets_paths = _gt_files_with_targets()
        if args.only:
            wanted = {s.strip() for s in args.only.split(",") if s.strip()}
            targets_paths = [p for p in targets_paths if p.stem in wanted]
        if not targets_paths:
            print("No GT files with overlay_targets found under "
                  f"{GT_DIR}. Run annotate_overlays.py first.")
            sys.exit(1)
    elif args.image:
        candidate = Path(args.image)
        if candidate.suffix:
            stem = candidate.stem
        else:
            stem = candidate.name
        gt_path = GT_DIR / f"{stem}.json"
        if not gt_path.exists():
            print(f"No GT JSON for {args.image} at {gt_path}. "
                  "Run annotate_overlays.py first.")
            sys.exit(1)
        targets_paths = [gt_path]
    else:
        parser.print_help()
        sys.exit(1)

    print(f"Evaluating {len(targets_paths)} image(s)...")
    per_image: list[ImageMetrics] = []
    info_by_image: dict[str, dict] = {}
    for gt_path in targets_paths:
        try:
            metrics, info = asyncio.run(_evaluate_one(gt_path, render_visual=args.visual))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {gt_path.name}: {exc}")
            continue
        if metrics.total_targets == 0:
            print(f"  (skipped — no overlay_targets in {gt_path.name})")
            continue
        per_image.append(metrics)
        info_by_image[metrics.image_id] = info

    if not per_image:
        print("No images scored.")
        sys.exit(1)

    print()
    print(format_per_image_table(per_image))
    print()
    agg = aggregate(per_image)
    print(format_aggregate(agg))
    print()

    # Badge-precision view (the Gate 1 bar metrics)
    views = []
    print("Badge precision (per rendered badge, bar metrics):")
    print(f"{'image_id':<45}{'judged':>7}{'corr':>6}{'wrong':>6}{'off':>5}{'unjdg':>6}{'prec':>7}{'top3':>7}")
    for m in per_image:
        p = info_by_image.get(m.image_id, {}).get("precision")
        if not p:
            continue
        v = PrecisionView(
            on_correct=p["on_correct"], wrong_bottle=p["wrong_bottle"],
            off_bottle=p["off_bottle"], unjudgeable=p["unjudgeable"],
            top3_judged=p["top3_judged"], top3_correct=p["top3_correct"],
        )
        views.append(v)
        prec = f"{v.badge_precision:.2f}" if v.badge_precision is not None else "  -"
        top3 = f"{v.top3_correct}/{v.top3_judged}"
        print(f"{m.image_id[:44]:<45}{v.judged:>7}{v.on_correct:>6}{v.wrong_bottle:>6}{v.off_bottle:>5}{v.unjudgeable:>6}{prec:>7}{top3:>7}")
    total = merge_precision_views(views)
    bp = f"{total.badge_precision:.3f}" if total.badge_precision is not None else "N/A"
    t3 = f"{total.top3_precision:.3f}" if total.top3_precision is not None else "N/A"
    print(f"AGGREGATE badge_precision={bp}  top3_precision={t3} "
          f"({total.top3_correct}/{total.top3_judged})  unjudgeable={total.unjudgeable}")
    print()

    # Cost / latency summary (measured, candidate runs only)
    costs = [i.get("cost_usd") for i in info_by_image.values() if i.get("cost_usd") is not None]
    lats = [i.get("paid_latency_ms") for i in info_by_image.values() if i.get("paid_latency_ms")]
    if costs:
        print(f"COST: total=${sum(costs):.4f}  mean=${sum(costs)/len(costs):.4f}/scan  "
              f"paid-latency mean={sum(lats)/len(lats)/1000:.1f}s max={max(lats)/1000:.1f}s")
        print()
    print(format_swap_details(per_image))

    if args.json:
        out: dict = {
            "aggregate": _aggregate_to_dict(agg),
            "per_image": [
                _image_metrics_to_dict(m, info_by_image.get(m.image_id, {}))
                for m in per_image
            ],
        }
        out_path = Path(args.json).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nSaved metrics: {out_path}")


if __name__ == "__main__":
    main()
