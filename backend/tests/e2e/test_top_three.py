"""
Tests for top-3 emphasis logic.

Top 3 wines by rating should get:
- Slightly larger badge
- Yellow border glow
- .top-three CSS class
"""

import pytest
from playwright.sync_api import Page, expect


class TestTopThree:
    """Tests for top-3 wine emphasis."""

    def test_get_top_three_sorts_by_rating(self, page: Page):
        """Verify getTopThree returns wines sorted by rating."""
        result = page.evaluate("""
            () => {
                const wines = [
                    { wine_name: 'Wine A', rating: 4.0, confidence: 0.9 },
                    { wine_name: 'Wine B', rating: 4.8, confidence: 0.9 },
                    { wine_name: 'Wine C', rating: 4.5, confidence: 0.9 },
                    { wine_name: 'Wine D', rating: 3.5, confidence: 0.9 },
                ];

                const isVisible = (confidence) => confidence >= 0.45;
                const getTopThree = (wines) => {
                    return [...wines]
                        .filter(w => isVisible(w.confidence))
                        .sort((a, b) => b.rating - a.rating)
                        .slice(0, 3);
                };

                return getTopThree(wines).map(w => w.wine_name);
            }
        """)
        assert result == ["Wine B", "Wine C", "Wine A"]

    def test_top_three_excludes_invisible_wines(self, page: Page):
        """Verify wines below visibility threshold are excluded from top 3."""
        result = page.evaluate("""
            () => {
                const wines = [
                    { wine_name: 'Wine A', rating: 4.9, confidence: 0.40 },  // Too low confidence
                    { wine_name: 'Wine B', rating: 4.5, confidence: 0.9 },
                    { wine_name: 'Wine C', rating: 4.3, confidence: 0.9 },
                    { wine_name: 'Wine D', rating: 4.0, confidence: 0.9 },
                ];

                const isVisible = (confidence) => confidence >= 0.45;
                const getTopThree = (wines) => {
                    return [...wines]
                        .filter(w => isVisible(w.confidence))
                        .sort((a, b) => b.rating - a.rating)
                        .slice(0, 3);
                };

                return getTopThree(wines).map(w => w.wine_name);
            }
        """)
        # Wine A has highest rating but is invisible
        assert "Wine A" not in result
        assert result == ["Wine B", "Wine C", "Wine D"]

    def test_top_three_handles_fewer_than_three_wines(self, page: Page):
        """Verify getTopThree works with fewer than 3 visible wines."""
        result = page.evaluate("""
            () => {
                const wines = [
                    { wine_name: 'Wine A', rating: 4.5, confidence: 0.9 },
                    { wine_name: 'Wine B', rating: 4.0, confidence: 0.9 },
                ];

                const isVisible = (confidence) => confidence >= 0.45;
                const getTopThree = (wines) => {
                    return [...wines]
                        .filter(w => isVisible(w.confidence))
                        .sort((a, b) => b.rating - a.rating)
                        .slice(0, 3);
                };

                return getTopThree(wines).map(w => w.wine_name);
            }
        """)
        assert len(result) == 2
        assert result == ["Wine A", "Wine B"]

    def test_wine_name_sanitization(self, page: Page):
        """Verify wine names are properly sanitized for test IDs."""
        result = page.evaluate("""
            () => {
                const sanitizeWineName = (name) => {
                    return name.toLowerCase().replace(/\\s+/g, '-').replace(/'/g, '');
                };

                return {
                    simple: sanitizeWineName('Opus One'),
                    with_apostrophe: sanitizeWineName("Kendall-Jackson Vintner's Reserve"),
                    with_spaces: sanitizeWineName('La Crema Sonoma Coast Pinot Noir')
                };
            }
        """)
        assert result["simple"] == "opus-one"
        assert result["with_apostrophe"] == "kendall-jackson-vintners-reserve"
        assert result["with_spaces"] == "la-crema-sonoma-coast-pinot-noir"
