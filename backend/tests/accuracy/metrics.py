"""
Accuracy metrics for wine recognition evaluation.

Provides precision, recall, F1 score, and rating MAE calculations
for evaluating pipeline performance against ground truth.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WineMatch:
    """Represents a match between detected and ground truth wine."""
    detected_name: str
    ground_truth_name: str
    detected_rating: Optional[float]
    expected_rating: Optional[float]
    rating_tolerance: float = 0.5
    is_name_match: bool = False
    rating_source: str = "database"  # 'database' or 'llm_estimated'


@dataclass
class AccuracyMetrics:
    """
    Accuracy metrics for wine recognition evaluation.

    Attributes:
        true_positives: Correctly identified wines (name matches ground truth)
        false_positives: Detected wines not in ground truth (wrong wine)
        false_negatives: Ground truth wines not detected (missed wines)
        rating_errors_db: List of (detected - expected) for database ratings
        rating_errors_llm: List of (detected - expected) for LLM-estimated ratings
    """
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    rating_errors_db: list[float] = field(default_factory=list)
    rating_errors_llm: list[float] = field(default_factory=list)

    # Track individual matches for detailed reporting
    matches: list[WineMatch] = field(default_factory=list)

    @property
    def precision(self) -> float:
        """
        Precision: Of all wines we detected, what fraction were correct?

        precision = TP / (TP + FP)
        """
        total_detected = self.true_positives + self.false_positives
        if total_detected == 0:
            return 0.0
        return self.true_positives / total_detected

    @property
    def recall(self) -> float:
        """
        Recall: Of all wines that existed, what fraction did we find?

        recall = TP / (TP + FN)
        """
        total_actual = self.true_positives + self.false_negatives
        if total_actual == 0:
            return 0.0
        return self.true_positives / total_actual

    @property
    def f1(self) -> float:
        """
        F1 Score: Harmonic mean of precision and recall.

        F1 = 2 * (precision * recall) / (precision + recall)
        """
        p = self.precision
        r = self.recall
        if p + r == 0:
            return 0.0
        return 2 * (p * r) / (p + r)

    @property
    def rating_mae_db(self) -> Optional[float]:
        """
        Mean Absolute Error for database ratings.

        Returns None if no database ratings were compared.
        """
        if not self.rating_errors_db:
            return None
        return sum(abs(e) for e in self.rating_errors_db) / len(self.rating_errors_db)

    @property
    def rating_mae_llm(self) -> Optional[float]:
        """
        Mean Absolute Error for LLM-estimated ratings.

        Returns None if no LLM ratings were compared.
        """
        if not self.rating_errors_llm:
            return None
        return sum(abs(e) for e in self.rating_errors_llm) / len(self.rating_errors_llm)

    @property
    def rating_mae_overall(self) -> Optional[float]:
        """
        Mean Absolute Error across all ratings (DB + LLM).

        Returns None if no ratings were compared.
        """
        all_errors = self.rating_errors_db + self.rating_errors_llm
        if not all_errors:
            return None
        return sum(abs(e) for e in all_errors) / len(all_errors)

    @property
    def wines_with_ratings_pct(self) -> float:
        """
        Percentage of correctly identified wines that have ratings.

        This measures the goal of "100% wines with ratings".
        """
        if self.true_positives == 0:
            return 0.0
        wines_with_ratings = len(self.rating_errors_db) + len(self.rating_errors_llm)
        return wines_with_ratings / self.true_positives * 100

    def add_true_positive(
        self,
        detected_name: str,
        ground_truth_name: str,
        detected_rating: Optional[float],
        expected_rating: Optional[float],
        rating_tolerance: float = 0.5,
        rating_source: str = "database"
    ) -> None:
        """Record a true positive (correct detection)."""
        self.true_positives += 1

        match = WineMatch(
            detected_name=detected_name,
            ground_truth_name=ground_truth_name,
            detected_rating=detected_rating,
            expected_rating=expected_rating,
            rating_tolerance=rating_tolerance,
            is_name_match=True,
            rating_source=rating_source
        )
        self.matches.append(match)

        # Record rating error if both ratings exist
        if detected_rating is not None and expected_rating is not None:
            error = detected_rating - expected_rating
            if rating_source == "llm_estimated":
                self.rating_errors_llm.append(error)
            else:
                self.rating_errors_db.append(error)

    def add_false_positive(self, detected_name: str) -> None:
        """Record a false positive (incorrect detection)."""
        self.false_positives += 1

        match = WineMatch(
            detected_name=detected_name,
            ground_truth_name="",
            detected_rating=None,
            expected_rating=None,
            is_name_match=False
        )
        self.matches.append(match)

    def add_false_negative(self, ground_truth_name: str, expected_rating: Optional[float] = None) -> None:
        """Record a false negative (missed detection)."""
        self.false_negatives += 1

        match = WineMatch(
            detected_name="",
            ground_truth_name=ground_truth_name,
            detected_rating=None,
            expected_rating=expected_rating,
            is_name_match=False
        )
        self.matches.append(match)

    def summary(self) -> str:
        """Generate a human-readable summary of metrics."""
        lines = [
            "Wine Recognition Accuracy Report",
            "=" * 40,
            f"Precision: {self.precision:.3f} | Recall: {self.recall:.3f} | F1: {self.f1:.3f}",
            f"",
            f"True Positives:  {self.true_positives}",
            f"False Positives: {self.false_positives}",
            f"False Negatives: {self.false_negatives}",
            f"",
        ]

        # Rating accuracy
        mae_db = self.rating_mae_db
        mae_llm = self.rating_mae_llm

        if mae_db is not None:
            lines.append(f"Rating MAE (DB):  {mae_db:.2f} stars ({len(self.rating_errors_db)} samples)")
        else:
            lines.append("Rating MAE (DB):  N/A (no database ratings)")

        if mae_llm is not None:
            lines.append(f"Rating MAE (LLM): {mae_llm:.2f} stars ({len(self.rating_errors_llm)} samples)")
        else:
            lines.append("Rating MAE (LLM): N/A (no LLM ratings)")

        lines.append(f"")
        lines.append(f"Wines with ratings: {self.wines_with_ratings_pct:.1f}%")

        return "\n".join(lines)


def normalize_wine_name(name: str) -> str:
    """
    Normalize wine name for comparison.

    - Lowercase
    - Remove vintage years (19xx, 20xx)
    - Remove common suffixes (Reserve, Estate, etc.)
    - Remove extra whitespace
    """
    import re

    if not name:
        return ""

    normalized = name.lower().strip()

    # Remove vintage years
    normalized = re.sub(r'\b(19|20)\d{2}\b', '', normalized)

    # Remove bottle sizes (750ml, 1.5L, etc.)
    normalized = re.sub(r'\b\d+\.?\d*\s*(ml|l|liter|litre)\b', '', normalized, flags=re.IGNORECASE)

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def names_match(detected: str, ground_truth: str, threshold: float = 0.8) -> bool:
    """
    Check if two wine names match using fuzzy matching.

    Args:
        detected: Detected wine name from pipeline
        ground_truth: Expected wine name from ground truth
        threshold: Minimum similarity score (0-1) to consider a match

    Returns:
        True if names match within threshold
    """
    from rapidfuzz import fuzz

    norm_detected = normalize_wine_name(detected)
    norm_ground_truth = normalize_wine_name(ground_truth)

    if not norm_detected or not norm_ground_truth:
        return False

    # Use token sort ratio for best matching across word order differences
    score = fuzz.token_sort_ratio(norm_detected, norm_ground_truth) / 100.0

    return score >= threshold


def evaluate_results(
    detected_wines: list[dict],
    ground_truth_wines: list[dict],
    name_match_threshold: float = 0.8
) -> AccuracyMetrics:
    """
    Evaluate pipeline results against ground truth.

    Args:
        detected_wines: List of detected wines with keys:
            - wine_name: str
            - rating: Optional[float]
            - rating_source: str ('database' or 'llm_estimated')
        ground_truth_wines: List of ground truth wines with keys:
            - wine_name: str
            - expected_rating: Optional[float]
            - rating_tolerance: float (default 0.5)

    Returns:
        AccuracyMetrics with calculated precision/recall/F1/MAE
    """
    metrics = AccuracyMetrics()

    # Track which ground truth wines have been matched
    matched_gt_indices = set()

    # For each detected wine, find best matching ground truth
    for detected in detected_wines:
        detected_name = detected.get("wine_name", "")
        detected_rating = detected.get("rating")
        rating_source = detected.get("rating_source", "database")

        # Find best matching ground truth wine
        best_match_idx = None
        best_match_score = 0.0

        for i, gt in enumerate(ground_truth_wines):
            if i in matched_gt_indices:
                continue

            gt_name = gt.get("wine_name", "")

            # Check if names match
            from rapidfuzz import fuzz
            norm_detected = normalize_wine_name(detected_name)
            norm_gt = normalize_wine_name(gt_name)

            if norm_detected and norm_gt:
                score = fuzz.token_sort_ratio(norm_detected, norm_gt) / 100.0
                if score >= name_match_threshold and score > best_match_score:
                    best_match_idx = i
                    best_match_score = score

        if best_match_idx is not None:
            # True positive - correct detection
            gt = ground_truth_wines[best_match_idx]
            matched_gt_indices.add(best_match_idx)

            metrics.add_true_positive(
                detected_name=detected_name,
                ground_truth_name=gt.get("wine_name", ""),
                detected_rating=detected_rating,
                expected_rating=gt.get("expected_rating"),
                rating_tolerance=gt.get("rating_tolerance", 0.5),
                rating_source=rating_source
            )
        else:
            # False positive - detected wine not in ground truth
            metrics.add_false_positive(detected_name)

    # Any unmatched ground truth wines are false negatives
    for i, gt in enumerate(ground_truth_wines):
        if i not in matched_gt_indices:
            metrics.add_false_negative(
                ground_truth_name=gt.get("wine_name", ""),
                expected_rating=gt.get("expected_rating")
            )

    return metrics


def aggregate_metrics(metrics_list: list[AccuracyMetrics]) -> AccuracyMetrics:
    """
    Aggregate multiple AccuracyMetrics into a single summary.

    Args:
        metrics_list: List of AccuracyMetrics from individual images

    Returns:
        Combined AccuracyMetrics
    """
    combined = AccuracyMetrics()

    for m in metrics_list:
        combined.true_positives += m.true_positives
        combined.false_positives += m.false_positives
        combined.false_negatives += m.false_negatives
        combined.rating_errors_db.extend(m.rating_errors_db)
        combined.rating_errors_llm.extend(m.rating_errors_llm)
        combined.matches.extend(m.matches)

    return combined
