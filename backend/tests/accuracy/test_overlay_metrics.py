"""Smoke tests for overlay placement metrics."""

from tests.accuracy.overlay_metrics import (
    OverlayPrediction,
    OverlayTarget,
    score_image,
)


def _bbox(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def test_correct_assignment_when_anchor_inside_and_name_matches():
    target = OverlayTarget(wine_name="Caymus Cabernet", bbox=_bbox(0.10, 0.10, 0.10, 0.30))
    pred = OverlayPrediction(
        wine_name="Caymus Cabernet Sauvignon",
        bbox=_bbox(0.10, 0.10, 0.10, 0.30),
        confidence=0.85,
    )
    m = score_image("img", [target], [pred])
    assert m.correct == 1
    assert m.swaps == 0
    assert m.misses == 0
    assert m.outcomes[0].iou is not None and m.outcomes[0].iou > 0.99


def test_swap_when_anchor_lands_in_other_targets_bbox():
    # Two bottles side by side. Predictions are crossed.
    t_left = OverlayTarget(wine_name="Caymus Cabernet", bbox=_bbox(0.10, 0.10, 0.10, 0.30))
    t_right = OverlayTarget(wine_name="Opus One", bbox=_bbox(0.40, 0.10, 0.10, 0.30))
    # Caymus prediction lands on the Opus bbox (swap)
    p_caymus = OverlayPrediction(
        wine_name="Caymus Cabernet Sauvignon",
        bbox=_bbox(0.40, 0.10, 0.10, 0.30),
    )
    p_opus = OverlayPrediction(
        wine_name="Opus One 2019", bbox=_bbox(0.10, 0.10, 0.10, 0.30)
    )
    m = score_image("img", [t_left, t_right], [p_caymus, p_opus])
    assert m.correct == 0
    assert m.swaps == 2
    assert m.misses == 0


def test_miss_when_no_prediction_for_target():
    target = OverlayTarget(wine_name="Caymus", bbox=_bbox(0.10, 0.10, 0.10, 0.30))
    p_other = OverlayPrediction(
        wine_name="Random Other Wine", bbox=_bbox(0.50, 0.50, 0.10, 0.30)
    )
    m = score_image("img", [target], [p_other])
    assert m.correct == 0
    assert m.swaps == 0
    assert m.misses == 1


def test_anchor_just_outside_bbox_does_not_match():
    # Anchor falls just outside the GT bbox horizontally
    target = OverlayTarget(wine_name="Caymus", bbox=_bbox(0.10, 0.10, 0.10, 0.30))
    # Bbox center is at 0.55 — outside the GT [0.10, 0.20]
    pred = OverlayPrediction(
        wine_name="Caymus Cabernet", bbox=_bbox(0.50, 0.10, 0.10, 0.30)
    )
    m = score_image("img", [target], [pred])
    assert m.correct == 0


def test_high_confidence_prediction_consumed_first():
    # Two predictions, one correct + high-confidence, one incorrect + low confidence
    target = OverlayTarget(wine_name="Caymus", bbox=_bbox(0.10, 0.10, 0.10, 0.30))
    # Both anchors fall in target bbox; only one name matches
    p_correct = OverlayPrediction(
        wine_name="Caymus Cabernet", bbox=_bbox(0.10, 0.10, 0.10, 0.30), confidence=0.85
    )
    p_wrong = OverlayPrediction(
        wine_name="Other Wine", bbox=_bbox(0.10, 0.10, 0.10, 0.30), confidence=0.50
    )
    m = score_image("img", [target], [p_correct, p_wrong])
    assert m.correct == 1
    assert m.outcomes[0].matched_prediction is p_correct
