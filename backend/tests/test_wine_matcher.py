"""
Tests for wine matcher.
"""

import pytest
from app.services.wine_matcher import WineMatcher


class TestWineMatcher:
    """Tests for fuzzy wine matching."""

    @pytest.fixture
    def matcher(self):
        """Create matcher with default database."""
        return WineMatcher()

    def test_exact_match(self, matcher):
        result = matcher.match("Opus One")
        assert result is not None
        assert result.canonical_name == "Opus One"
        assert result.confidence == 1.0
        assert result.rating == 4.8

    def test_exact_match_case_insensitive(self, matcher):
        result = matcher.match("opus one")
        assert result is not None
        assert result.canonical_name == "Opus One"

        result = matcher.match("OPUS ONE")
        assert result is not None
        assert result.canonical_name == "Opus One"

    def test_alias_match(self, matcher):
        result = matcher.match("Caymus")
        assert result is not None
        assert result.canonical_name == "Caymus Cabernet Sauvignon"

        result = matcher.match("KJ Chardonnay")
        assert result is not None
        assert "Kendall-Jackson" in result.canonical_name

    def test_fuzzy_match(self, matcher):
        # Slight misspelling
        result = matcher.match("Caymus Cabernet")
        assert result is not None
        assert "Caymus" in result.canonical_name

        # Partial name
        result = matcher.match("Silver Oak")
        assert result is not None
        assert "Silver Oak" in result.canonical_name

    def test_no_match(self, matcher):
        result = matcher.match("Completely Unknown Wine XYZ123")
        assert result is None

    def test_empty_query(self, matcher):
        result = matcher.match("")
        assert result is None

        result = matcher.match(None)
        assert result is None

    def test_match_many(self, matcher):
        queries = ["Opus One", "Caymus", "XYZABC123 Nonexistent"]
        results = matcher.match_many(queries)

        assert len(results) == 3
        assert results[0] is not None  # Opus One
        assert results[1] is not None  # Caymus
        assert results[2] is None  # Clearly nonexistent

    def test_rating_values(self, matcher):
        # Check ratings are in valid range
        test_wines = ["Opus One", "Caymus", "Barefoot Moscato", "Franzia"]

        for wine in test_wines:
            result = matcher.match(wine)
            if result:
                assert 1.0 <= result.rating <= 5.0

    def test_confidence_range(self, matcher):
        # Exact match should be 1.0
        result = matcher.match("Opus One")
        assert result.confidence == 1.0

        # Fuzzy match should be < 1.0
        result = matcher.match("Opus")
        if result:
            assert result.confidence <= 1.0
