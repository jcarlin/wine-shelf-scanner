"""
Visual debug tool for wine bottle spatial matching.

Draws annotated bounding boxes on shelf images showing:
- Green rectangles: Vision API bottle detections
- Red rectangles: Gemini-estimated positions
- Yellow lines: spatial match connections between Gemini and Vision bottles
- Wine name + rating labels

Usage:
    # Live pipeline mode (requires API credentials):
    python -m scripts.visualize_bboxes test-images/IMG_8334.HEIC

    # From a JSON fixture file:
    python -m scripts.visualize_bboxes test-images/IMG_8334.HEIC --fixture path/to/fixture.json

    # Custom output path:
    python -m scripts.visualize_bboxes test-images/IMG_8334.HEIC --output debug_output.jpg
"""

import argparse
import asyncio
import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Image loading helpers
# ---------------------------------------------------------------------------

def _load_image(path: str) -> Image.Image:
    """Load an image, converting HEIC to JPEG if necessary."""
    p = Path(path)
    ext = p.suffix.lower()

    if ext in (".heic", ".heif"):
        return _load_heic(p)

    return Image.open(p).convert("RGB")


def _load_heic(path: Path) -> Image.Image:
    """Load HEIC image via pillow-heif or macOS sips fallback."""
    # Try pillow-heif first
    try:
        import pillow_heif
        heif_file = pillow_heif.read_heif(str(path))
        return Image.frombytes(
            heif_file.mode, heif_file.size, heif_file.data, "raw"
        ).convert("RGB")
    except ImportError:
        pass

    # Fallback: macOS sips conversion
    tmp_path = path.with_suffix(".tmp.jpg")
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(path), "--out", str(tmp_path)],
            check=True,
            capture_output=True,
        )
        img = Image.open(tmp_path).convert("RGB")
        return img
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            f"Cannot load HEIC image. Install pillow-heif or use macOS sips. Error: {exc}"
        ) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------

def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Get a readable font, falling back to default if no TTF is available."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

# Colors
VISION_COLOR = (0, 200, 0)          # Green for Vision API bottles
GEMINI_COLOR = (220, 40, 40)        # Red for Gemini-estimated positions
MATCH_LINE_COLOR = (255, 220, 0)    # Yellow for match connections
LEGEND_BG = (30, 30, 30, 200)       # Semi-transparent dark background
TEXT_COLOR = (255, 255, 255)         # White text
LABEL_BG = (0, 0, 0, 160)          # Semi-transparent label background


def _bbox_to_pixels(
    x: float, y: float, w: float, h: float,
    img_w: int, img_h: int,
) -> tuple[int, int, int, int]:
    """Convert normalized (0-1) bbox to pixel coordinates (x1, y1, x2, y2)."""
    x1 = int(x * img_w)
    y1 = int(y * img_h)
    x2 = int((x + w) * img_w)
    y2 = int((y + h) * img_h)
    return x1, y1, x2, y2


def _center_pixels(
    x: float, y: float, w: float, h: float,
    img_w: int, img_h: int,
) -> tuple[int, int]:
    """Get pixel center of a normalized bbox."""
    cx = int((x + w / 2) * img_w)
    cy = int((y + h / 2) * img_h)
    return cx, cy


def _draw_label(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int, y: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: tuple,
    bg_color: tuple = LABEL_BG,
):
    """Draw text with a semi-transparent background."""
    bbox = draw.textbbox((x, y), text, font=font)
    pad = 3
    draw.rectangle(
        [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
        fill=bg_color,
    )
    draw.text((x, y), text, fill=color, font=font)


def draw_annotations(
    img: Image.Image,
    vision_bottles: list[dict],
    gemini_wines: list[dict],
    matches: list[dict],
) -> Image.Image:
    """
    Draw all annotations on a copy of the image.

    Args:
        img: Source PIL image.
        vision_bottles: List of dicts with keys: label, x, y, w, h (normalized 0-1),
                        and optional ocr_text.
        gemini_wines: List of dicts with keys: name, x, y, w, h (normalized 0-1),
                      and optional rating.
        matches: List of dicts with keys: gemini_idx, vision_idx, distance.

    Returns:
        Annotated copy of the image.
    """
    annotated = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    img_w, img_h = annotated.size

    # Scale font size relative to image
    base_font_size = max(12, int(min(img_w, img_h) * 0.015))
    font = _get_font(base_font_size)
    small_font = _get_font(max(10, base_font_size - 4))

    # 1. Draw Vision API bottles (green)
    for i, vb in enumerate(vision_bottles):
        x1, y1, x2, y2 = _bbox_to_pixels(
            vb["x"], vb["y"], vb["w"], vb["h"], img_w, img_h
        )
        line_width = max(2, int(min(img_w, img_h) * 0.003))
        draw.rectangle([x1, y1, x2, y2], outline=VISION_COLOR + (220,), width=line_width)

        label = f"V{i}"
        _draw_label(draw, label, x1, y1 - base_font_size - 6, font, VISION_COLOR + (255,))

        # Show OCR text if available
        ocr = vb.get("ocr_text", "")
        if ocr:
            short_ocr = ocr[:30] + ("..." if len(ocr) > 30 else "")
            _draw_label(draw, short_ocr, x1, y2 + 4, small_font, (200, 200, 200, 255))

    # 2. Draw Gemini-estimated positions (red)
    for i, gw in enumerate(gemini_wines):
        gx, gy = gw.get("x"), gw.get("y")
        if gx is None or gy is None:
            continue

        gw_w = gw.get("w", 0.08)
        gw_h = gw.get("h", 0.25)

        x1, y1, x2, y2 = _bbox_to_pixels(gx, gy, gw_w, gw_h, img_w, img_h)
        line_width = max(2, int(min(img_w, img_h) * 0.003))
        # Dashed effect: draw with thinner lines
        draw.rectangle([x1, y1, x2, y2], outline=GEMINI_COLOR + (200,), width=line_width)

        name = gw.get("name", f"G{i}")
        rating = gw.get("rating")
        label_parts = [name[:25] + ("..." if len(name) > 25 else "")]
        if rating is not None:
            label_parts.append(f"  [{rating:.1f}]")
        label_text = "".join(label_parts)
        _draw_label(draw, label_text, x1, y1 - base_font_size - 6, font, GEMINI_COLOR + (255,))

    # 3. Draw match connections (yellow lines)
    for m in matches:
        gi = m["gemini_idx"]
        vi = m["vision_idx"]
        dist = m.get("distance", 0)

        if gi >= len(gemini_wines) or vi >= len(vision_bottles):
            continue

        gw = gemini_wines[gi]
        vb = vision_bottles[vi]

        gx, gy = gw.get("x"), gw.get("y")
        if gx is None or gy is None:
            continue
        gw_w = gw.get("w", 0.08)
        gw_h = gw.get("h", 0.25)
        g_cx, g_cy = _center_pixels(gx, gy, gw_w, gw_h, img_w, img_h)
        v_cx, v_cy = _center_pixels(vb["x"], vb["y"], vb["w"], vb["h"], img_w, img_h)

        line_width = max(1, int(min(img_w, img_h) * 0.002))
        draw.line([(g_cx, g_cy), (v_cx, v_cy)], fill=MATCH_LINE_COLOR + (200,), width=line_width)

        # Distance annotation at midpoint
        mid_x = (g_cx + v_cx) // 2
        mid_y = (g_cy + v_cy) // 2
        dist_text = f"d={dist:.3f}"
        _draw_label(draw, dist_text, mid_x, mid_y, small_font, MATCH_LINE_COLOR + (255,))

    # 4. Draw legend
    _draw_legend(draw, img_w, img_h, font, small_font)

    # Composite overlay onto image
    annotated = Image.alpha_composite(annotated, overlay)
    return annotated.convert("RGB")


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    img_w: int, img_h: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
):
    """Draw a legend box in the top-right corner."""
    legend_items = [
        (VISION_COLOR + (255,), "Green = Vision API bottles"),
        (GEMINI_COLOR + (255,), "Red = Gemini estimates"),
        (MATCH_LINE_COLOR + (255,), "Yellow = spatial match"),
    ]

    pad = 10
    line_height = 20
    legend_w = 260
    legend_h = pad * 2 + line_height * len(legend_items)
    lx = img_w - legend_w - pad
    ly = pad

    draw.rectangle(
        [lx, ly, lx + legend_w, ly + legend_h],
        fill=LEGEND_BG,
    )

    for i, (color, text) in enumerate(legend_items):
        item_y = ly + pad + i * line_height
        # Color swatch
        draw.rectangle(
            [lx + pad, item_y + 2, lx + pad + 14, item_y + 14],
            fill=color,
        )
        draw.text(
            (lx + pad + 20, item_y),
            text,
            fill=TEXT_COLOR + (255,),
            font=small_font,
        )


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def load_fixture(fixture_path: str) -> dict:
    """
    Load a JSON fixture file with pipeline data.

    Expected format:
    {
        "vision_bottles": [
            {"label": "V0", "x": 0.1, "y": 0.2, "w": 0.08, "h": 0.3, "ocr_text": "CAYMUS..."}
        ],
        "gemini_wines": [
            {"name": "Caymus Cabernet Sauvignon", "x": 0.12, "y": 0.22, "w": 0.08, "h": 0.28, "rating": 4.4}
        ],
        "matches": [
            {"gemini_idx": 0, "vision_idx": 0, "distance": 0.032}
        ]
    }
    """
    with open(fixture_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Live pipeline mode
# ---------------------------------------------------------------------------

def run_live_pipeline(image_bytes: bytes) -> dict:
    """
    Run the flash_names pipeline and capture intermediate results.

    Returns dict with vision_bottles, gemini_wines, and matches.
    """
    # Add backend root to path so imports work
    backend_root = str(Path(__file__).resolve().parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    from app.services.flash_names_pipeline import FlashNamesPipeline
    from app.services.vision import VisionService
    from app.services.ocr_processor import OCRProcessor

    # --- Step 1: Run Vision API ---
    print("  Running Vision API...")
    vision_service = VisionService()
    vision_result = vision_service.analyze(image_bytes)
    print(f"  Vision API: {len(vision_result.objects)} bottles detected")

    # --- Step 2: Run Gemini ---
    print("  Running Gemini Flash...")
    pipeline = FlashNamesPipeline()
    llm_wines = asyncio.run(pipeline._run_gemini_names(image_bytes))
    print(f"  Gemini: {len(llm_wines)} wines identified")

    # --- Step 3: OCR grouping ---
    ocr_processor = OCRProcessor()
    ocr_result = ocr_processor.process_with_orphans(
        vision_result.objects, vision_result.text_blocks
    )
    bottle_texts = ocr_result.bottle_texts

    # --- Step 4: Build visualization data ---

    # Vision bottles
    vision_bottles = []
    for i, bt in enumerate(bottle_texts):
        bbox = bt.bottle.bbox
        vision_bottles.append({
            "label": f"V{i}",
            "x": bbox.x,
            "y": bbox.y,
            "w": bbox.width,
            "h": bbox.height,
            "ocr_text": bt.combined_text or "",
        })

    # Gemini wines
    gemini_wines = []
    for wine in llm_wines:
        gemini_wines.append({
            "name": wine.get("name", "Unknown"),
            "x": wine.get("x"),
            "y": wine.get("y"),
            "w": wine.get("w"),
            "h": wine.get("h"),
            "rating": wine.get("rating"),
        })

    # --- Step 5: Compute spatial matches (replicating pipeline logic) ---
    DEFAULT_BOTTLE_WIDTH = 0.08
    DEFAULT_BOTTLE_HEIGHT = 0.25
    MAX_SPATIAL_DISTANCE = 0.25

    bottle_centers = [bt.bottle.bbox.center for bt in bottle_texts]

    pairs = []
    for li, wine in enumerate(llm_wines):
        lx, ly = wine.get("x"), wine.get("y")
        if lx is None or ly is None:
            continue
        lw, lh = wine.get("w"), wine.get("h")
        if lw is not None and lh is not None:
            cx = lx + lw / 2
            cy = ly + lh / 2
        else:
            cx = lx + DEFAULT_BOTTLE_WIDTH / 2
            cy = ly + DEFAULT_BOTTLE_HEIGHT / 2
        for bi, (bx, by) in enumerate(bottle_centers):
            dist = math.sqrt((cx - bx) ** 2 + (cy - by) ** 2)
            pairs.append((dist, li, bi))

    pairs.sort()
    used_bottles: set[int] = set()
    used_llm: set[int] = set()
    matches = []

    for dist, li, bi in pairs:
        if li in used_llm or bi in used_bottles:
            continue
        if dist > MAX_SPATIAL_DISTANCE:
            break
        used_llm.add(li)
        used_bottles.add(bi)
        matches.append({
            "gemini_idx": li,
            "vision_idx": bi,
            "distance": round(dist, 4),
        })

    print(f"  Spatial matches: {len(matches)}")
    print(f"  Unmatched Gemini wines: {len(llm_wines) - len(used_llm)}")
    print(f"  Unmatched Vision bottles: {len(bottle_texts) - len(used_bottles)}")

    return {
        "vision_bottles": vision_bottles,
        "gemini_wines": gemini_wines,
        "matches": matches,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Visualize wine bottle bounding boxes and spatial matching.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Live pipeline (requires API credentials):
  python -m scripts.visualize_bboxes test-images/IMG_8334.HEIC

  # From fixture:
  python -m scripts.visualize_bboxes test-images/IMG_8334.HEIC --fixture data.json

  # Custom output:
  python -m scripts.visualize_bboxes test-images/wine1.jpg --output annotated.jpg
        """,
    )
    parser.add_argument("image", help="Path to the shelf image (HEIC, JPEG, PNG)")
    parser.add_argument(
        "--fixture",
        help="Path to JSON fixture with pre-captured pipeline data",
    )
    parser.add_argument(
        "--output",
        help="Output path for annotated image (default: <image>_annotated.jpg)",
    )

    args = parser.parse_args()

    # Resolve paths
    image_path = Path(args.image).resolve()
    if not image_path.exists():
        print(f"Error: Image not found: {image_path}")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = image_path.with_name(image_path.stem + "_annotated.jpg")

    # Load image
    print(f"Loading image: {image_path}")
    img = _load_image(str(image_path))
    print(f"  Image size: {img.size[0]}x{img.size[1]}")

    # Get pipeline data
    if args.fixture:
        fixture_path = Path(args.fixture).resolve()
        if not fixture_path.exists():
            print(f"Error: Fixture not found: {fixture_path}")
            sys.exit(1)
        print(f"Loading fixture: {fixture_path}")
        data = load_fixture(str(fixture_path))
    else:
        print("Running live pipeline...")
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # Convert HEIC to JPEG bytes for the pipeline
        ext = image_path.suffix.lower()
        if ext in (".heic", ".heif"):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            image_bytes = buf.getvalue()

        data = run_live_pipeline(image_bytes)

    vision_bottles = data.get("vision_bottles", [])
    gemini_wines = data.get("gemini_wines", [])
    matches = data.get("matches", [])

    print(f"\nDrawing annotations:")
    print(f"  Vision bottles: {len(vision_bottles)}")
    print(f"  Gemini wines: {len(gemini_wines)}")
    print(f"  Matches: {len(matches)}")

    # Draw
    annotated = draw_annotations(img, vision_bottles, gemini_wines, matches)

    # Save
    annotated.save(str(output_path), "JPEG", quality=95)
    print(f"\nSaved: {output_path}")

    # Also save the fixture data alongside (for re-use)
    if not args.fixture:
        fixture_output = output_path.with_suffix(".json")
        with open(fixture_output, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved fixture: {fixture_output}")


if __name__ == "__main__":
    main()
