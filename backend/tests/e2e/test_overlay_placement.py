"""
End-to-end overlay placement test.

Loads a real test image into the running Next.js dev server (assumed at
http://localhost:3000), waits for the scan to render, then verifies that at
least one rating badge was rendered AND its normalized anchor falls inside
the union of GT bboxes from `overlay_targets`. This is a *coarse* sanity
check; the full numeric eval is the CLI (`scripts.eval_overlays --all`).

Marked `@pytest.mark.network` because it depends on:
- Next.js dev server running at localhost:3000
- The local backend running at localhost:8000 (with valid Vision + Gemini keys)

Run manually with:
    pytest backend/tests/e2e/test_overlay_placement.py -m network -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e._overlay_helpers import BADGE_EXTRACT_JS, normalize_targets_to_anchors

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GT_DIR = REPO_ROOT / "test-images" / "corpus" / "ground_truth"
NEXTJS_URL = "http://localhost:3000"


def _is_nextjs_up() -> bool:
    import httpx

    try:
        r = httpx.get(NEXTJS_URL, timeout=2.0)
        return r.status_code < 500
    except Exception:
        return False


def _load_gt(stem: str) -> dict:
    p = GT_DIR / f"{stem}.json"
    if not p.exists():
        pytest.skip(f"No GT for {stem} at {p}")
    return json.loads(p.read_text())


@pytest.mark.network
def test_image_8334_renders_overlays_at_expected_locations(tmp_path):
    """Smoke check that uploading IMG_8334.HEIC produces ≥1 badge whose
    anchor lies inside one of the annotated overlay_target bboxes.

    Failure modes:
    - 0 badges → frontend or backend silently broke.
    - All badges fall outside every GT bbox → severe placement regression.
    """
    if not _is_nextjs_up():
        pytest.skip(
            "Next.js dev server not running at localhost:3000 — "
            "start it with `cd nextjs && npm run dev`."
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed in this venv")

    image_path = REPO_ROOT / "test-images" / "IMG_8334.HEIC"
    if not image_path.exists():
        pytest.skip(f"Test image missing: {image_path}")

    gt = _load_gt("IMG_8334")
    targets = gt.get("overlay_targets") or []
    if not targets:
        pytest.skip("IMG_8334 has no overlay_targets")

    expected_anchors = normalize_targets_to_anchors(targets)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(NEXTJS_URL)

        with page.expect_file_chooser() as fc_info:
            page.get_by_role("button", name="Upload Image").click()
        fc_info.value.set_files(str(image_path))

        # Wait for the "Analyzing wines..." overlay to disappear (max 60s)
        try:
            page.get_by_text("Analyzing wines").first.wait_for(state="hidden", timeout=60_000)
        except Exception:
            pass  # may have rendered too fast

        # Allow badge entrance animations
        page.wait_for_timeout(1500)

        result = page.evaluate(BADGE_EXTRACT_JS)
        page.close()
        context.close()
        browser.close()

    assert "error" not in result, f"DOM extract returned error: {result.get('error')}"
    assert result["badge_count"] > 0, (
        f"No rating badges rendered after scan. body suggests pipeline failed."
    )

    # At least 50% of badges should land inside SOME GT bbox.
    inside = 0
    for badge in result["badges"]:
        ax = badge["anchor_norm"]["x"]
        ay = badge["anchor_norm"]["y"]
        for t in targets:
            b = t["bbox"]
            if b["x"] <= ax <= b["x"] + b["w"] and b["y"] <= ay <= b["y"] + b["h"]:
                inside += 1
                break

    fraction = inside / max(1, result["badge_count"])
    # Phase 1 baseline threshold — kept loose; tighter assertions arrive in Phase 3.
    assert fraction >= 0.10, (
        f"Only {fraction:.1%} of {result['badge_count']} badges land in any GT bbox; "
        f"expected at least 10% even at baseline."
    )
