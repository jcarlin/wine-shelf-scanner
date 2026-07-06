"""
Ground-truth annotator for overlay placement evaluation.

Workflow:
1. Run the live pipeline on an image (cached as a fixture for re-use).
2. Save an annotated PNG showing Vision bottles labeled V0..Vn.
3. Either:
   - Interactive mode: prompt for "wine name -> V index" mappings.
   - --apply <mapping.json>: read mappings from a JSON file (agent / scripted use).
4. Write the resulting `overlay_targets` list into the ground-truth JSON at
   `test-images/corpus/ground_truth/<image_stem>.json` (creating it if absent).

Usage:
    # Interactive (human picks V indices for each wine)
    python -m scripts.annotate_overlays test-images/IMG_8334.HEIC

    # Bulk-apply pre-built mappings
    python -m scripts.annotate_overlays test-images/IMG_8334.HEIC --apply mapping.json

    # Print the Vision bbox table (useful for visual inspection of V indices)
    python -m scripts.annotate_overlays test-images/IMG_8334.HEIC --print-bottles

    # Force re-running the pipeline (default: re-use cached fixture if present)
    python -m scripts.annotate_overlays test-images/IMG_8334.HEIC --refresh

The mapping JSON format (`--apply`):
    {
      "image_file": "IMG_8334.HEIC",
      "targets": [
        {"wine_name": "Caymus Cabernet Sauvignon", "v_idx": 3,
         "distinctive_tokens": ["caymus"]},
        {"wine_name": "Opus One 2019",
         "bbox": {"x": 0.5, "y": 0.2, "w": 0.07, "h": 0.22},
         "distinctive_tokens": ["opus"]}
      ]
    }

A target uses `v_idx` (resolved to the Vision bottle's bbox) OR an explicit
`bbox` (for bottles Vision missed). `distinctive_tokens` is optional metadata
used by Phase 2 diagnostics.
"""

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Optional

# Make sibling imports work when run as `python -m scripts.annotate_overlays`
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.visualize_bboxes import (  # type: ignore  # noqa: E402
    _load_image,
    draw_annotations,
    run_live_pipeline,
)

REPO_ROOT = BACKEND_ROOT.parent
GT_DIR = REPO_ROOT / "test-images" / "corpus" / "ground_truth"
FIXTURE_DIR = BACKEND_ROOT / "out" / "fixtures"
ANNOTATED_DIR = BACKEND_ROOT / "out" / "annotated"


def _gt_path(image_path: Path) -> Path:
    return GT_DIR / f"{image_path.stem}.json"


def _fixture_path(image_path: Path) -> Path:
    return FIXTURE_DIR / f"{image_path.stem}.fixture.json"


def _annotated_path(image_path: Path) -> Path:
    return ANNOTATED_DIR / f"{image_path.stem}_annotated.jpg"


def _load_or_run_fixture(image_path: Path, refresh: bool) -> dict:
    """Return cached fixture if present, otherwise run the pipeline and cache."""
    fixture_path = _fixture_path(image_path)
    if fixture_path.exists() and not refresh:
        with open(fixture_path) as f:
            return json.load(f)

    print(f"Loading image: {image_path}")
    img = _load_image(str(image_path))
    print(f"  Image size: {img.size[0]}x{img.size[1]}")

    # Convert any non-JPEG-readable format to JPEG bytes for the pipeline
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    image_bytes = buf.getvalue()

    print("Running live pipeline (this may cost a Vision API + Gemini call)...")
    data = run_live_pipeline(image_bytes)

    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fixture_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Cached fixture: {fixture_path}")
    return data


def _save_annotated(image_path: Path, fixture: dict) -> Path:
    """Save the labeled annotated PNG and return the path."""
    img = _load_image(str(image_path))
    annotated = draw_annotations(
        img,
        fixture.get("vision_bottles", []),
        fixture.get("gemini_wines", []),
        fixture.get("matches", []),
    )
    out_path = _annotated_path(image_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    annotated.save(str(out_path), "JPEG", quality=92)
    return out_path


def _format_bottle_table(vision_bottles: list[dict]) -> str:
    """Render the V-index table for human review."""
    if not vision_bottles:
        return "(no Vision bottles detected)"
    lines = [f"  {'V#':<5}{'x':>7}{'y':>7}{'w':>7}{'h':>7}  ocr_text"]
    for i, b in enumerate(vision_bottles):
        ocr = (b.get("ocr_text") or "").replace("\n", " ")[:60]
        lines.append(
            f"  V{i:<4}"
            f"{b['x']:>7.3f}{b['y']:>7.3f}{b['w']:>7.3f}{b['h']:>7.3f}  {ocr}"
        )
    return "\n".join(lines)


def _resolve_target(
    target: dict[str, Any],
    vision_bottles: list[dict],
) -> dict[str, Any]:
    """Resolve a mapping entry to the canonical overlay_target schema."""
    wine_name = target.get("wine_name")
    if not wine_name or not isinstance(wine_name, str):
        raise ValueError(f"Target missing wine_name: {target!r}")

    out: dict[str, Any] = {
        "wine_name": wine_name.strip(),
        "bbox_kind": target.get("bbox_kind", "bottle"),
    }
    distinctive = target.get("distinctive_tokens")
    if distinctive:
        out["distinctive_tokens"] = list(distinctive)

    if "v_idx" in target and target["v_idx"] is not None:
        v_idx = int(target["v_idx"])
        if v_idx < 0 or v_idx >= len(vision_bottles):
            raise ValueError(
                f"v_idx {v_idx} out of range "
                f"(have V0..V{len(vision_bottles) - 1}) for wine {wine_name!r}"
            )
        b = vision_bottles[v_idx]
        out["bbox"] = {"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]}
        out["v_idx"] = v_idx
        out.setdefault("bbox_kind", "bottle")
        return out

    if "bbox" in target:
        bbox = target["bbox"]
        for k in ("x", "y", "w", "h"):
            if k not in bbox:
                raise ValueError(f"bbox missing key {k!r} for wine {wine_name!r}")
        out["bbox"] = {
            "x": float(bbox["x"]),
            "y": float(bbox["y"]),
            "w": float(bbox["w"]),
            "h": float(bbox["h"]),
        }
        return out

    raise ValueError(
        f"Target needs either v_idx or explicit bbox for wine {wine_name!r}"
    )


def _write_ground_truth(
    image_path: Path,
    overlay_targets: list[dict[str, Any]],
) -> Path:
    """Write or merge overlay_targets into the GT JSON, preserving `wines`."""
    gt_path = _gt_path(image_path)
    gt_path.parent.mkdir(parents=True, exist_ok=True)

    if gt_path.exists():
        with open(gt_path) as f:
            existing = json.load(f)
    else:
        existing = {"image_file": image_path.name, "wines": []}

    existing["image_file"] = image_path.name
    existing["overlay_targets"] = overlay_targets
    existing["overlay_target_count"] = len(overlay_targets)

    with open(gt_path, "w") as f:
        json.dump(existing, f, indent=2)
    return gt_path


def _interactive_loop(vision_bottles: list[dict]) -> list[dict]:
    """Prompt the human for wine name → V index mappings."""
    print("\nInteractive annotation. Type 'done' when finished.")
    print("Format: '<wine name>' (then prompted for V index).")
    print("        '<wine name> | V3' to set in one line.")
    print("        '<wine name> | x y w h' for explicit bbox (Vision missed it).\n")
    targets: list[dict[str, Any]] = []
    while True:
        try:
            line = input("wine> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line or line.lower() in {"done", "exit", "quit"}:
            break

        if "|" in line:
            wine_name, _, suffix = line.partition("|")
            wine_name = wine_name.strip()
            suffix = suffix.strip()
            if suffix.lower().startswith("v") and suffix[1:].isdigit():
                v_idx = int(suffix[1:])
                target = {"wine_name": wine_name, "v_idx": v_idx}
            else:
                parts = suffix.split()
                if len(parts) != 4:
                    print("  ! Could not parse suffix. Use 'V<idx>' or 'x y w h'.")
                    continue
                target = {
                    "wine_name": wine_name,
                    "bbox": {
                        "x": float(parts[0]),
                        "y": float(parts[1]),
                        "w": float(parts[2]),
                        "h": float(parts[3]),
                    },
                }
        else:
            wine_name = line
            v_raw = input(
                f"  V index for {wine_name!r} (or 'skip' / 'bbox x y w h'): "
            ).strip()
            if v_raw.lower() == "skip":
                continue
            if v_raw.lower().startswith("bbox"):
                parts = v_raw.split()[1:]
                if len(parts) != 4:
                    print("  ! Need 'bbox x y w h'.")
                    continue
                target = {
                    "wine_name": wine_name,
                    "bbox": {
                        "x": float(parts[0]),
                        "y": float(parts[1]),
                        "w": float(parts[2]),
                        "h": float(parts[3]),
                    },
                }
            else:
                if not v_raw.lower().startswith("v"):
                    v_raw = "V" + v_raw
                if not v_raw[1:].isdigit():
                    print("  ! V index must be 'V<n>'.")
                    continue
                target = {"wine_name": wine_name, "v_idx": int(v_raw[1:])}
        try:
            resolved = _resolve_target(target, vision_bottles)
        except ValueError as exc:
            print(f"  ! {exc}")
            continue
        targets.append(resolved)
        print(f"  ✓ {resolved['wine_name']} → bbox={resolved['bbox']}")
    return targets


def _apply_mapping_file(
    mapping_path: Path,
    vision_bottles: list[dict],
) -> list[dict]:
    """Resolve a JSON mapping file into overlay_targets."""
    with open(mapping_path) as f:
        data = json.load(f)

    raw_targets = data.get("targets")
    if raw_targets is None:
        raise ValueError(
            f"Mapping file {mapping_path} must have a top-level 'targets' list"
        )

    resolved = []
    for entry in raw_targets:
        resolved.append(_resolve_target(entry, vision_bottles))
    return resolved


def main():
    parser = argparse.ArgumentParser(
        description="Annotate overlay-placement ground truth.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("image", help="Path to the shelf image (HEIC, JPEG, PNG)")
    parser.add_argument(
        "--apply",
        help="JSON mapping file to apply (skips the interactive prompt).",
    )
    parser.add_argument(
        "--print-bottles",
        action="store_true",
        help="Print the Vision bbox table (V0..Vn) and exit.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force a fresh pipeline run (default: re-use cached fixture).",
    )
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    if not image_path.exists():
        print(f"Error: image not found: {image_path}")
        sys.exit(1)

    fixture = _load_or_run_fixture(image_path, refresh=args.refresh)
    annotated_path = _save_annotated(image_path, fixture)
    print(f"Annotated PNG: {annotated_path}")

    vision_bottles = fixture.get("vision_bottles", [])
    print(f"\nVision bottles ({len(vision_bottles)}):")
    print(_format_bottle_table(vision_bottles))

    if args.print_bottles:
        return

    if args.apply:
        mapping_path = Path(args.apply).resolve()
        if not mapping_path.exists():
            print(f"Error: mapping file not found: {mapping_path}")
            sys.exit(1)
        overlay_targets = _apply_mapping_file(mapping_path, vision_bottles)
        print(f"\nApplied {len(overlay_targets)} targets from {mapping_path}")
    else:
        overlay_targets = _interactive_loop(vision_bottles)
        if not overlay_targets:
            print("No targets recorded; not writing GT.")
            return

    gt_path = _write_ground_truth(image_path, overlay_targets)
    print(f"Ground truth written: {gt_path}")
    print(f"  overlay_targets: {len(overlay_targets)}")


if __name__ == "__main__":
    main()
