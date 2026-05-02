"""
Overlay placement accuracy metrics.

Measures whether predicted wine overlays land on the correct bottle, distinct
from `metrics.py` (which measures wine recognition accuracy).

Primary metric: assignment accuracy.
  For each ground-truth target, the prediction is "correct" iff:
    - the predicted overlay's anchor point falls inside the GT bbox, AND
    - the predicted wine name fuzzy-matches the GT wine name.

Secondary metrics:
  swap_rate: predicted anchor lands inside a DIFFERENT GT bbox AND the predicted
             wine name matches THAT other wine. This is the swap bug we are
             specifically chasing.
  miss_rate: GT wine has no overlay at all (predicted anchor inside GT but
             name mismatch, OR no predicted overlay near GT bbox at all).
  mean_iou:  mean IoU over correctly-assigned pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Reuse the wine recognition fuzzy matcher
from tests.accuracy.metrics import names_match


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _bbox_anchor(bbox: dict) -> tuple[float, float]:
    """Anchor point used to place the rating badge (centered, top quarter).

    Mirrors the OverlayMath rule:
        anchor_x = bbox.x + bbox.w / 2
        anchor_y = bbox.y + bbox.h * 0.25
    """
    return (bbox["x"] + bbox["w"] / 2.0, bbox["y"] + bbox["h"] * 0.25)


def _point_in_bbox(point: tuple[float, float], bbox: dict) -> bool:
    px, py = point
    return (
        bbox["x"] <= px <= bbox["x"] + bbox["w"]
        and bbox["y"] <= py <= bbox["y"] + bbox["h"]
    )


def _iou(a: dict, b: dict) -> float:
    ax2 = a["x"] + a["w"]
    ay2 = a["y"] + a["h"]
    bx2 = b["x"] + b["w"]
    by2 = b["y"] + b["h"]

    ix1 = max(a["x"], b["x"])
    iy1 = max(a["y"], b["y"])
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    if union <= 0:
        return 0.0
    return inter / union


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OverlayPrediction:
    """A predicted overlay from the pipeline."""

    wine_name: str
    bbox: dict  # {x, y, w, h} normalized 0-1
    confidence: float = 1.0
    source: str = "unknown"  # "hungarian" | "ocr_fallback" | "ocr_anchor" | "gemini_synthetic"

    @property
    def anchor(self) -> tuple[float, float]:
        return _bbox_anchor(self.bbox)


@dataclass
class OverlayTarget:
    """A ground-truth overlay placement target."""

    wine_name: str
    bbox: dict  # {x, y, w, h} normalized 0-1
    bbox_kind: str = "bottle"
    distinctive_tokens: list[str] = field(default_factory=list)


@dataclass
class TargetOutcome:
    """Per-target classification result."""

    target: OverlayTarget
    classification: str  # "correct" | "swap" | "miss"
    matched_prediction: Optional[OverlayPrediction] = None
    iou: Optional[float] = None
    # For swaps, the GT target whose bbox the prediction landed in
    swap_target: Optional[OverlayTarget] = None


@dataclass
class ImageMetrics:
    """Per-image overlay placement metrics."""

    image_id: str
    outcomes: list[TargetOutcome] = field(default_factory=list)
    unmatched_predictions: list[OverlayPrediction] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)

    @property
    def total_targets(self) -> int:
        return len(self.outcomes)

    @property
    def correct(self) -> int:
        return sum(1 for o in self.outcomes if o.classification == "correct")

    @property
    def swaps(self) -> int:
        return sum(1 for o in self.outcomes if o.classification == "swap")

    @property
    def misses(self) -> int:
        return sum(1 for o in self.outcomes if o.classification == "miss")

    @property
    def assignment_accuracy(self) -> float:
        return self.correct / self.total_targets if self.total_targets else 0.0

    @property
    def swap_rate(self) -> float:
        return self.swaps / self.total_targets if self.total_targets else 0.0

    @property
    def miss_rate(self) -> float:
        return self.misses / self.total_targets if self.total_targets else 0.0

    @property
    def mean_iou(self) -> Optional[float]:
        ious = [o.iou for o in self.outcomes if o.classification == "correct" and o.iou is not None]
        if not ious:
            return None
        return sum(ious) / len(ious)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_image(
    image_id: str,
    targets: list[OverlayTarget],
    predictions: list[OverlayPrediction],
    name_threshold: float = 0.85,
) -> ImageMetrics:
    """Score a single image's overlay predictions against its ground truth.

    Algorithm:
      For each GT target:
        1. Find predictions whose anchor falls inside the target's bbox.
        2. If exactly one matches AND its wine_name matches → correct.
        3. If a prediction's anchor falls inside a DIFFERENT target's bbox and
           that prediction's name matches THAT other target → swap.
        4. Otherwise → miss.

      A prediction can be "consumed" by at most one target (we use the highest-
      confidence matching prediction first).
    """
    outcomes: list[TargetOutcome] = []
    consumed_predictions: set[int] = set()

    # Pre-sort predictions by confidence (highest first) for deterministic consumption
    sorted_preds = sorted(
        enumerate(predictions),
        key=lambda kv: kv[1].confidence,
        reverse=True,
    )

    # Pass 1 — try correct assignment for each target
    for target in targets:
        outcome = TargetOutcome(target=target, classification="miss")

        candidates = []
        for pred_idx, pred in sorted_preds:
            if pred_idx in consumed_predictions:
                continue
            if _point_in_bbox(pred.anchor, target.bbox) and names_match(
                pred.wine_name, target.wine_name, threshold=name_threshold
            ):
                candidates.append((pred_idx, pred))

        if candidates:
            pred_idx, pred = candidates[0]  # highest-confidence first
            consumed_predictions.add(pred_idx)
            outcome.classification = "correct"
            outcome.matched_prediction = pred
            outcome.iou = _iou(pred.bbox, target.bbox)
        outcomes.append(outcome)

    # Pass 2 — for misses, look for swaps (predicted anchor inside ANOTHER target,
    # name matches THAT target)
    for outcome in outcomes:
        if outcome.classification != "miss":
            continue
        for pred_idx, pred in sorted_preds:
            if pred_idx in consumed_predictions:
                continue
            # Is this prediction supposedly "for" this target by name?
            if not names_match(pred.wine_name, outcome.target.wine_name, threshold=name_threshold):
                continue
            # Did the prediction anchor land in a different target's bbox?
            for other_target in targets:
                if other_target is outcome.target:
                    continue
                if _point_in_bbox(pred.anchor, other_target.bbox):
                    outcome.classification = "swap"
                    outcome.matched_prediction = pred
                    outcome.swap_target = other_target
                    consumed_predictions.add(pred_idx)
                    break
            if outcome.classification == "swap":
                break

    # Source breakdown
    source_counts: dict[str, int] = {}
    for pred in predictions:
        source_counts[pred.source] = source_counts.get(pred.source, 0) + 1

    # Unmatched predictions (didn't land on any GT target)
    unmatched = [
        predictions[i]
        for i in range(len(predictions))
        if i not in consumed_predictions
    ]

    return ImageMetrics(
        image_id=image_id,
        outcomes=outcomes,
        unmatched_predictions=unmatched,
        source_counts=source_counts,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

@dataclass
class AggregateMetrics:
    """Aggregate metrics across multiple images."""

    per_image: list[ImageMetrics] = field(default_factory=list)

    @property
    def total_targets(self) -> int:
        return sum(m.total_targets for m in self.per_image)

    @property
    def correct(self) -> int:
        return sum(m.correct for m in self.per_image)

    @property
    def swaps(self) -> int:
        return sum(m.swaps for m in self.per_image)

    @property
    def misses(self) -> int:
        return sum(m.misses for m in self.per_image)

    @property
    def assignment_accuracy(self) -> float:
        return self.correct / self.total_targets if self.total_targets else 0.0

    @property
    def swap_rate(self) -> float:
        return self.swaps / self.total_targets if self.total_targets else 0.0

    @property
    def miss_rate(self) -> float:
        return self.misses / self.total_targets if self.total_targets else 0.0

    @property
    def mean_iou(self) -> Optional[float]:
        ious: list[float] = []
        for m in self.per_image:
            for o in m.outcomes:
                if o.classification == "correct" and o.iou is not None:
                    ious.append(o.iou)
        if not ious:
            return None
        return sum(ious) / len(ious)

    @property
    def source_counts(self) -> dict[str, int]:
        agg: dict[str, int] = {}
        for m in self.per_image:
            for k, v in m.source_counts.items():
                agg[k] = agg.get(k, 0) + v
        return agg


def aggregate(metrics_list: list[ImageMetrics]) -> AggregateMetrics:
    return AggregateMetrics(per_image=list(metrics_list))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_per_image_table(metrics_list: list[ImageMetrics]) -> str:
    lines = [
        f"{'image_id':<55}{'targets':>9}{'correct':>9}{'swap':>6}{'miss':>6}{'acc':>7}{'swap%':>7}{'iou':>6}",
        "-" * 105,
    ]
    for m in metrics_list:
        iou = f"{m.mean_iou:.2f}" if m.mean_iou is not None else "  -"
        lines.append(
            f"{m.image_id[:54]:<55}"
            f"{m.total_targets:>9}"
            f"{m.correct:>9}"
            f"{m.swaps:>6}"
            f"{m.misses:>6}"
            f"{m.assignment_accuracy:>7.2f}"
            f"{m.swap_rate:>7.2f}"
            f"{iou:>6}"
        )
    return "\n".join(lines)


def format_aggregate(agg: AggregateMetrics) -> str:
    iou = f"{agg.mean_iou:.3f}" if agg.mean_iou is not None else "N/A"
    return (
        f"AGGREGATE: targets={agg.total_targets}  correct={agg.correct}  "
        f"swap={agg.swaps}  miss={agg.misses}\n"
        f"  assignment_accuracy = {agg.assignment_accuracy:.3f}\n"
        f"  swap_rate           = {agg.swap_rate:.3f}\n"
        f"  miss_rate           = {agg.miss_rate:.3f}\n"
        f"  mean_iou            = {iou}\n"
        f"  source_counts       = {agg.source_counts}"
    )


def format_swap_details(metrics_list: list[ImageMetrics]) -> str:
    lines = ["Swap details (predicted wine landed on a DIFFERENT GT bbox):"]
    any_swaps = False
    for m in metrics_list:
        for o in m.outcomes:
            if o.classification != "swap":
                continue
            any_swaps = True
            pred = o.matched_prediction
            other = o.swap_target
            lines.append(
                f"  [{m.image_id}] '{pred.wine_name}' was meant for "
                f"'{o.target.wine_name}' but landed in bbox of "
                f"'{other.wine_name if other else '?'}' (anchor={pred.anchor})"
            )
    if not any_swaps:
        lines.append("  (none)")
    return "\n".join(lines)
