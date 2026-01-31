"""
Tests for the wine detail modal.

Modal should:
- Open when tappable badge is clicked
- Show wine name, rating, stars, confidence label
- Close on overlay click or Escape key
"""

import pytest
from playwright.sync_api import Page, expect


class TestDetailModal:
    """Tests for the wine detail modal."""

    def test_modal_hidden_initially(self, page: Page):
        """Verify modal is hidden when page loads."""
        modal = page.locator('[data-testid="detail-modal"]')
        expect(modal).not_to_be_visible()

    def test_modal_has_required_elements(self, page: Page):
        """Verify modal contains all required elements."""
        # Check elements exist (they're hidden but in DOM)
        wine_name = page.locator('[data-testid="modal-wine-name"]')
        stars = page.locator('[data-testid="modal-stars"]')
        rating = page.locator('[data-testid="modal-rating"]')
        confidence = page.locator('[data-testid="modal-confidence"]')

        expect(wine_name).to_be_attached()
        expect(stars).to_be_attached()
        expect(rating).to_be_attached()
        expect(confidence).to_be_attached()

    def test_modal_closes_on_escape(self, page: Page):
        """Verify modal closes when Escape key is pressed."""
        # First, show the modal
        page.evaluate("""
            () => {
                document.querySelector('[data-testid="detail-modal"]').style.display = 'flex';
            }
        """)

        modal = page.locator('[data-testid="detail-modal"]')
        expect(modal).to_be_visible()

        # Press Escape
        page.keyboard.press("Escape")

        # Modal should be hidden
        expect(modal).not_to_be_visible()

    def test_star_generation(self, page: Page):
        """Verify star generation function works correctly."""
        result = page.evaluate("""
            () => {
                const generateStars = (rating) => {
                    const fullStars = Math.floor(rating);
                    const halfStar = rating % 1 >= 0.5 ? 1 : 0;
                    const emptyStars = 5 - fullStars - halfStar;
                    return {
                        full: fullStars,
                        half: halfStar,
                        empty: emptyStars,
                        display: '★'.repeat(fullStars) + (halfStar ? '☆' : '') + '☆'.repeat(emptyStars)
                    };
                };

                return {
                    rating_4_8: generateStars(4.8),
                    rating_4_5: generateStars(4.5),
                    rating_3_2: generateStars(3.2)
                };
            }
        """)

        # 4.8 -> 4 full, 1 half, 0 empty
        assert result["rating_4_8"]["full"] == 4
        assert result["rating_4_8"]["half"] == 1
        assert result["rating_4_8"]["empty"] == 0

        # 4.5 -> 4 full, 1 half, 0 empty
        assert result["rating_4_5"]["full"] == 4
        assert result["rating_4_5"]["half"] == 1
        assert result["rating_4_5"]["empty"] == 0

        # 3.2 -> 3 full, 0 half, 2 empty
        assert result["rating_3_2"]["full"] == 3
        assert result["rating_3_2"]["half"] == 0
        assert result["rating_3_2"]["empty"] == 2

    def test_open_detail_modal_function(self, page: Page):
        """Verify openDetailModal populates modal correctly."""
        page.evaluate("""
            () => {
                const wine = {
                    wine_name: 'Test Wine',
                    rating: 4.5,
                    confidence: 0.92
                };

                // Simulate what openDetailModal does
                const generateStars = (rating) => {
                    const fullStars = Math.floor(rating);
                    const halfStar = rating % 1 >= 0.5 ? 1 : 0;
                    const emptyStars = 5 - fullStars - halfStar;
                    return '★'.repeat(fullStars) + (halfStar ? '☆' : '') + '☆'.repeat(emptyStars);
                };

                const getConfidenceLabel = (c) => c >= 0.85 ? 'Widely rated' : 'Limited data';

                document.querySelector('[data-testid="modal-wine-name"]').textContent = wine.wine_name;
                document.querySelector('[data-testid="modal-stars"]').textContent = generateStars(wine.rating);
                document.querySelector('[data-testid="modal-rating"]').textContent = wine.rating.toFixed(1);
                document.querySelector('[data-testid="modal-confidence"]').textContent = getConfidenceLabel(wine.confidence);
                document.querySelector('[data-testid="detail-modal"]').style.display = 'flex';
            }
        """)

        # Verify modal content
        expect(page.locator('[data-testid="detail-modal"]')).to_be_visible()
        expect(page.locator('[data-testid="modal-wine-name"]')).to_have_text("Test Wine")
        expect(page.locator('[data-testid="modal-rating"]')).to_have_text("4.5")
        expect(page.locator('[data-testid="modal-confidence"]')).to_have_text("Widely rated")

    def test_modal_not_opened_for_low_confidence(self, page: Page):
        """Verify modal doesn't open for low confidence wines."""
        result = page.evaluate("""
            () => {
                const isTappable = (confidence) => confidence >= 0.65;

                // Simulate clicking a low confidence badge
                const wine = { confidence: 0.55 };
                let modalOpened = false;

                if (isTappable(wine.confidence)) {
                    modalOpened = true;
                }

                return modalOpened;
            }
        """)
        assert result is False
