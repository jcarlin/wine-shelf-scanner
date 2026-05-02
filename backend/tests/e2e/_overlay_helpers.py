"""
Shared DOM-extraction + comparison helpers for overlay placement e2e checks.

Used by both:
- backend/tests/e2e/test_overlay_placement.py (pytest + Playwright)
- The Playwright MCP interactive flow (an agent calls `BADGE_EXTRACT_JS` via
  `mcp__playwright__browser_evaluate`).

Badge identification: each rating overlay carries
`data-testid="rating-badge"` and `data-wine-name="<wine name>"`. Reading
`data-wine-name` gives the wine identity without needing to click into the
detail sheet. Verified empirically that clicking the badge opens a modal
with the same wine name.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# JavaScript snippets for extracting overlay positions from the rendered page
# ---------------------------------------------------------------------------

#: Returns:
#: {
#:   "image_natural": {"w": int, "h": int},
#:   "image_box": {"w": float, "h": float, "left": float, "top": float},
#:   "draw":      {"w": float, "h": float, "offX": float, "offY": float},
#:   "badge_count": int,
#:   "badges": [
#:     {
#:        "text": "...",
#:        "anchor_norm": {"x": float, "y": float},  # 0..1, in image-space (excludes letterbox)
#:        "screen_center": {"x": float, "y": float}
#:     }, ...
#:   ]
#: }
BADGE_EXTRACT_JS = r"""
() => {
  const img = document.querySelector('img[src^="blob:"], img[src*="data:image"], main img');
  if (!img) return { error: 'no rendered image found' };
  const ir = img.getBoundingClientRect();
  const naturalW = img.naturalWidth || ir.width;
  const naturalH = img.naturalHeight || ir.height;
  const ratioImg = naturalW / naturalH;
  const ratioBox = ir.width / ir.height;
  let drawW, drawH, offX, offY;
  if (ratioImg > ratioBox) {
    drawW = ir.width; drawH = ir.width / ratioImg; offX = 0; offY = (ir.height - drawH) / 2;
  } else {
    drawH = ir.height; drawW = ir.height * ratioImg; offX = (ir.width - drawW) / 2; offY = 0;
  }
  const badges = [];
  document.querySelectorAll('[data-testid="rating-badge"]').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const ix = (cx - ir.left - offX) / drawW;
    const iy = (cy - ir.top - offY) / drawH;
    badges.push({
      wine_name: el.getAttribute('data-wine-name') || '',
      text: (el.textContent || '').trim().slice(0, 80),
      anchor_norm: { x: +ix.toFixed(4), y: +iy.toFixed(4) },
      screen_center: { x: Math.round(cx), y: Math.round(cy) }
    });
  });
  return {
    image_natural: { w: naturalW, h: naturalH },
    image_box: { w: ir.width, h: ir.height, left: ir.left, top: ir.top },
    draw: { w: drawW, h: drawH, offX, offY },
    badge_count: badges.length,
    badges
  };
}
""".strip()


def parse_badge(badge: dict) -> tuple[str, str, float, float]:
    """Split badge text like 'BEST PICK4.5#1' or '4.0#5' or '3.8' into
    (rank_label, rating, anchor_x, anchor_y).
    """
    text = badge.get("text", "")
    anchor = badge.get("anchor_norm") or {}
    ax = float(anchor.get("x", -1))
    ay = float(anchor.get("y", -1))
    rank = ""
    rating = text
    if "#" in text:
        rating, _, rank = text.partition("#")
        rank = "#" + rank.strip()
    rating = rating.replace("BEST PICK", "").strip()
    return (rank, rating, ax, ay)


def normalize_targets_to_anchors(overlay_targets: list[dict]) -> list[dict]:
    """Convert GT overlay_targets (with full bbox) to a list of expected anchor
    points using the same OverlayMath rule the frontend uses.
    """
    out = []
    for t in overlay_targets:
        b = t["bbox"]
        out.append({
            "wine_name": t["wine_name"],
            "anchor": {
                "x": b["x"] + b["w"] / 2.0,
                "y": b["y"] + b["h"] * 0.25,
            },
        })
    return out
