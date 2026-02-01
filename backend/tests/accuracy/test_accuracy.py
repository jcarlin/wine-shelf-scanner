"""
Tests for accuracy metrics module.

Validates precision/recall/F1 calculations and rating MAE.
"""

import pytest
from .metrics import (
    AccuracyMetrics,
    evaluate_results,
    aggregate_metrics,
    normalize_wine_name,
    names_match,
)


class TestAccuracyMetrics:
    """Tests for AccuracyMetrics class."""

    def test_perfect_precision_recall(self):
        """Perfect detection: all wines found, none wrong."""
        metrics = AccuracyMetrics(
            true_positives=10,
            false_positives=0,
            false_negatives=0
        )
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1 == 1.0

    def test_no_detections(self):
        """No detections should return 0 for all metrics."""
        metrics = AccuracyMetrics(
            true_positives=0,
            false_positives=0,
            false_negatives=5
        )
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1 == 0.0

    def test_precision_calculation(self):
        """Precision = TP / (TP + FP)."""
        metrics = AccuracyMetrics(
            true_positives=8,
            false_positives=2,
            false_negatives=0
        )
        assert metrics.precision == pytest.approx(0.8)

    def test_recall_calculation(self):
        """Recall = TP / (TP + FN)."""
        metrics = AccuracyMetrics(
            true_positives=6,
            false_positives=0,
            false_negatives=4
        )
        assert metrics.recall == pytest.approx(0.6)

    def test_f1_calculation(self):
        """F1 = 2 * (precision * recall) / (precision + recall)."""
        metrics = AccuracyMetrics(
            true_positives=7,
            false_positives=3,  # precision = 0.7
            false_negatives=3   # recall = 0.7
        )
        # F1 = 2 * 0.7 * 0.7 / 1.4 = 0.7
        assert metrics.f1 == pytest.approx(0.7)

    def test_rating_mae_db(self):
        """Rating MAE for database matches."""
        metrics = AccuracyMetrics()
        metrics.rating_errors_db = [0.1, -0.2, 0.3, -0.1, 0.2]
        # MAE = (0.1 + 0.2 + 0.3 + 0.1 + 0.2) / 5 = 0.18
        assert metrics.rating_mae_db == pytest.approx(0.18)

    def test_rating_mae_llm(self):
        """Rating MAE for LLM estimates."""
        metrics = AccuracyMetrics()
        metrics.rating_errors_llm = [0.5, -0.5, 0.3, -0.3]
        # MAE = (0.5 + 0.5 + 0.3 + 0.3) / 4 = 0.4
        assert metrics.rating_mae_llm == pytest.approx(0.4)

    def test_rating_mae_none_when_empty(self):
        """MAE returns None when no ratings to compare."""
        metrics = AccuracyMetrics()
        assert metrics.rating_mae_db is None
        assert metrics.rating_mae_llm is None

    def test_wines_with_ratings_pct(self):
        """Calculate percentage of wines with ratings."""
        metrics = AccuracyMetrics(true_positives=10)
        metrics.rating_errors_db = [0.1, 0.2, 0.3]  # 3 DB ratings
        metrics.rating_errors_llm = [0.4, 0.5]       # 2 LLM ratings
        # 5 wines with ratings out of 10 = 50%
        assert metrics.wines_with_ratings_pct == pytest.approx(50.0)


class TestNormalizeWineName:
    """Tests for wine name normalization."""

    def test_lowercase(self):
        """Names should be lowercased."""
        assert normalize_wine_name("CAYMUS CABERNET") == "caymus cabernet"

    def test_remove_vintage(self):
        """Vintage years should be removed."""
        assert normalize_wine_name("Caymus 2019 Cabernet") == "caymus cabernet"
        assert normalize_wine_name("Opus One 2015") == "opus one"

    def test_remove_bottle_size(self):
        """Bottle sizes should be removed."""
        assert normalize_wine_name("Caymus 750ml") == "caymus"
        assert normalize_wine_name("Opus One 1.5L") == "opus one"

    def test_whitespace_normalization(self):
        """Multiple spaces should become single space."""
        assert normalize_wine_name("Caymus   Cabernet  Sauvignon") == "caymus cabernet sauvignon"


class TestNamesMatch:
    """Tests for fuzzy name matching."""

    def test_exact_match(self):
        """Exact names should match."""
        assert names_match("Caymus Cabernet", "Caymus Cabernet")

    def test_case_insensitive(self):
        """Matching should be case insensitive."""
        assert names_match("CAYMUS CABERNET", "caymus cabernet")

    def test_vintage_difference(self):
        """Different vintages should still match."""
        assert names_match("Caymus 2019", "Caymus 2020")

    def test_partial_name(self):
        """Partial names should match if similar enough."""
        assert names_match(
            "Caymus Cabernet Sauvignon",
            "Caymus Cabernet Sauvignon Napa Valley"
        )

    def test_different_wines_no_match(self):
        """Different wines should not match."""
        assert not names_match("Caymus Cabernet", "Opus One")


class TestEvaluateResults:
    """Tests for evaluate_results function."""

    def test_all_correct(self):
        """All detected wines match ground truth."""
        detected = [
            {"wine_name": "Caymus Cabernet Sauvignon", "rating": 4.5, "rating_source": "database"},
            {"wine_name": "Opus One", "rating": 4.8, "rating_source": "database"},
        ]
        ground_truth = [
            {"wine_name": "Caymus Cabernet Sauvignon", "expected_rating": 4.5},
            {"wine_name": "Opus One", "expected_rating": 4.7},
        ]

        metrics = evaluate_results(detected, ground_truth)

        assert metrics.true_positives == 2
        assert metrics.false_positives == 0
        assert metrics.false_negatives == 0

    def test_false_positive(self):
        """Detected wine not in ground truth."""
        detected = [
            {"wine_name": "Caymus Cabernet Sauvignon", "rating": 4.5, "rating_source": "database"},
            {"wine_name": "Wrong Wine", "rating": 3.0, "rating_source": "database"},
        ]
        ground_truth = [
            {"wine_name": "Caymus Cabernet Sauvignon", "expected_rating": 4.5},
        ]

        metrics = evaluate_results(detected, ground_truth)

        assert metrics.true_positives == 1
        assert metrics.false_positives == 1
        assert metrics.false_negatives == 0

    def test_false_negative(self):
        """Ground truth wine not detected."""
        detected = [
            {"wine_name": "Caymus Cabernet Sauvignon", "rating": 4.5, "rating_source": "database"},
        ]
        ground_truth = [
            {"wine_name": "Caymus Cabernet Sauvignon", "expected_rating": 4.5},
            {"wine_name": "Opus One", "expected_rating": 4.7},
        ]

        metrics = evaluate_results(detected, ground_truth)

        assert metrics.true_positives == 1
        assert metrics.false_positives == 0
        assert metrics.false_negatives == 1

    def test_rating_error_tracking(self):
        """Rating errors should be tracked by source."""
        detected = [
            {"wine_name": "Caymus Cabernet Sauvignon", "rating": 4.6, "rating_source": "database"},
            {"wine_name": "Unknown Wine XYZ", "rating": 4.0, "rating_source": "llm_estimated"},
        ]
        ground_truth = [
            {"wine_name": "Caymus Cabernet Sauvignon", "expected_rating": 4.5},
            {"wine_name": "Unknown Wine XYZ", "expected_rating": 3.8},
        ]

        metrics = evaluate_results(detected, ground_truth)

        assert len(metrics.rating_errors_db) == 1
        assert metrics.rating_errors_db[0] == pytest.approx(0.1)  # 4.6 - 4.5

        assert len(metrics.rating_errors_llm) == 1
        assert metrics.rating_errors_llm[0] == pytest.approx(0.2)  # 4.0 - 3.8


class TestAggregateMetrics:
    """Tests for aggregating multiple AccuracyMetrics."""

    def test_aggregate_counts(self):
        """TP/FP/FN should sum across metrics."""
        m1 = AccuracyMetrics(true_positives=3, false_positives=1, false_negatives=2)
        m2 = AccuracyMetrics(true_positives=5, false_positives=2, false_negatives=1)

        combined = aggregate_metrics([m1, m2])

        assert combined.true_positives == 8
        assert combined.false_positives == 3
        assert combined.false_negatives == 3

    def test_aggregate_rating_errors(self):
        """Rating errors should be combined."""
        m1 = AccuracyMetrics()
        m1.rating_errors_db = [0.1, 0.2]
        m1.rating_errors_llm = [0.3]

        m2 = AccuracyMetrics()
        m2.rating_errors_db = [0.4]
        m2.rating_errors_llm = [0.5, 0.6]

        combined = aggregate_metrics([m1, m2])

        assert len(combined.rating_errors_db) == 3
        assert len(combined.rating_errors_llm) == 3
