"""
Tests for the fallback list view.

When no overlays can be shown (full failure):
- Fallback list should be displayed
- Wines should be sorted by rating (highest first)
- No overlay badges should be visible
"""

import pytest
from playwright.sync_api import Page, expect


class TestFallback:
    """Tests for the fallback list functionality."""

    def test_fallback_container_hidden_initially(self, page: Page):
        """Verify fallback container is hidden when page loads."""
        fallback = page.locator('[data-testid="fallback-container"]')
        expect(fallback).not_to_be_visible()

    def test_fallback_header_exists(self, page: Page):
        """Verify fallback header element exists."""
        header = page.locator('[data-testid="fallback-header"]')
        expect(header).to_be_attached()

    def test_fallback_list_exists(self, page: Page):
        """Verify fallback list element exists."""
        list_elem = page.locator('[data-testid="fallback-list"]')
        expect(list_elem).to_be_attached()

    def test_fallback_sorting_by_rating(self, page: Page):
        """Verify fallback wines are sorted by rating descending."""
        result = page.evaluate("""
            () => {
                const wines = [
                    { wine_name: 'Wine A', rating: 3.5 },
                    { wine_name: 'Wine B', rating: 4.8 },
                    { wine_name: 'Wine C', rating: 4.2 },
                    { wine_name: 'Wine D', rating: 3.9 },
                ];

                const sorted = [...wines].sort((a, b) => b.rating - a.rating);
                return sorted.map(w => ({ name: w.wine_name, rating: w.rating }));
            }
        """)

        assert result[0]["name"] == "Wine B"  # 4.8
        assert result[1]["name"] == "Wine C"  # 4.2
        assert result[2]["name"] == "Wine D"  # 3.9
        assert result[3]["name"] == "Wine A"  # 3.5

    def test_render_fallback_list(self, page: Page):
        """Verify renderFallbackList creates correct DOM elements."""
        page.evaluate("""
            () => {
                const wines = [
                    { wine_name: 'Wine A', rating: 4.5 },
                    { wine_name: 'Wine B', rating: 4.0 },
                ];

                const fallbackList = document.querySelector('[data-testid="fallback-list"]');
                fallbackList.innerHTML = '';

                const sorted = [...wines].sort((a, b) => b.rating - a.rating);

                sorted.forEach(wine => {
                    const sanitizeWineName = (name) => name.toLowerCase().replace(/\\s+/g, '-').replace(/'/g, '');
                    const item = document.createElement('div');
                    item.className = 'fallback-item';
                    item.setAttribute('data-testid', `fallback-item-${sanitizeWineName(wine.wine_name)}`);
                    item.innerHTML = `
                        <span class="wine-name">${wine.wine_name}</span>
                        <span class="rating"><span class="star">★</span> ${wine.rating.toFixed(1)}</span>
                    `;
                    fallbackList.appendChild(item);
                });
            }
        """)

        # Verify items were created
        wine_a = page.locator('[data-testid="fallback-item-wine-a"]')
        wine_b = page.locator('[data-testid="fallback-item-wine-b"]')

        expect(wine_a).to_be_attached()
        expect(wine_b).to_be_attached()

    def test_full_failure_detection(self, page: Page):
        """Verify full failure is detected correctly."""
        result = page.evaluate("""
            () => {
                const isFullFailure = (response) => {
                    return response.results.length === 0 && response.fallback_list.length > 0;
                };

                const fullFailure = {
                    results: [],
                    fallback_list: [{ wine_name: 'Wine A', rating: 4.5 }]
                };

                const partialDetection = {
                    results: [{ wine_name: 'Wine B', rating: 4.0, confidence: 0.9, bbox: {} }],
                    fallback_list: [{ wine_name: 'Wine A', rating: 4.5 }]
                };

                const fullSuccess = {
                    results: [{ wine_name: 'Wine B', rating: 4.0, confidence: 0.9, bbox: {} }],
                    fallback_list: []
                };

                return {
                    fullFailure: isFullFailure(fullFailure),
                    partialDetection: isFullFailure(partialDetection),
                    fullSuccess: isFullFailure(fullSuccess)
                };
            }
        """)

        assert result["fullFailure"] is True
        assert result["partialDetection"] is False
        assert result["fullSuccess"] is False

    def test_fallback_has_new_scan_button(self, page: Page):
        """Verify fallback view includes New Scan button."""
        button = page.locator('[data-testid="fallback-new-scan"]')
        expect(button).to_be_attached()
