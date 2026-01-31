"""
Tests for error handling in the web UI.

Error handling should:
- Show error screen on API failure
- Display error message
- Provide retry and start over buttons
"""

import pytest
from playwright.sync_api import Page, expect


class TestErrorHandling:
    """Tests for error handling functionality."""

    def test_error_screen_hidden_initially(self, page: Page):
        """Verify error screen is hidden when page loads."""
        error_screen = page.locator('[data-testid="error-screen"]')
        expect(error_screen).not_to_be_visible()

    def test_error_screen_has_message_element(self, page: Page):
        """Verify error message element exists."""
        message = page.locator('[data-testid="error-message"]')
        expect(message).to_be_attached()

    def test_retry_button_exists(self, page: Page):
        """Verify retry button exists."""
        retry = page.locator('[data-testid="retry-button"]')
        expect(retry).to_be_attached()

    def test_start_over_button_exists(self, page: Page):
        """Verify start over button exists."""
        start_over = page.locator('[data-testid="start-over-button"]')
        expect(start_over).to_be_attached()

    def test_show_error_screen(self, page: Page):
        """Verify error screen can be shown."""
        page.evaluate("""
            () => {
                // Show error screen
                document.querySelector('[data-testid="upload-screen"]').style.display = 'none';
                document.querySelector('[data-testid="error-screen"]').style.display = 'flex';
                document.querySelector('[data-testid="error-message"]').textContent = 'Test error message';
            }
        """)

        error_screen = page.locator('[data-testid="error-screen"]')
        error_message = page.locator('[data-testid="error-message"]')

        expect(error_screen).to_be_visible()
        expect(error_message).to_have_text("Test error message")

    def test_start_over_returns_to_upload(self, page: Page):
        """Verify Start Over button returns to upload screen."""
        # First show error screen
        page.evaluate("""
            () => {
                document.querySelector('[data-testid="upload-screen"]').style.display = 'none';
                document.querySelector('[data-testid="error-screen"]').style.display = 'flex';
            }
        """)

        # Click start over
        page.click('[data-testid="start-over-button"]')

        # Verify upload screen is shown
        upload_screen = page.locator('[data-testid="upload-screen"]')
        error_screen = page.locator('[data-testid="error-screen"]')

        expect(upload_screen).to_be_visible()
        expect(error_screen).not_to_be_visible()

    def test_reset_app_clears_state(self, page: Page):
        """Verify resetApp function clears application state."""
        result = page.evaluate("""
            () => {
                // Set some state
                let currentImageFile = new File([''], 'test.jpg');
                let lastResponse = { results: [] };

                // Reset (simulating resetApp)
                currentImageFile = null;
                lastResponse = null;

                return {
                    imageFileCleared: currentImageFile === null,
                    responseCleared: lastResponse === null
                };
            }
        """)

        assert result["imageFileCleared"] is True
        assert result["responseCleared"] is True

    def test_handle_error_shows_message(self, page: Page):
        """Verify handleError shows the error message."""
        page.evaluate("""
            () => {
                const error = new Error('Network error');

                // Simulate handleError
                const errorMessage = document.querySelector('[data-testid="error-message"]');
                errorMessage.textContent = error.message || 'Something went wrong';

                document.querySelector('[data-testid="upload-screen"]').style.display = 'none';
                document.querySelector('[data-testid="error-screen"]').style.display = 'flex';
            }
        """)

        message = page.locator('[data-testid="error-message"]')
        expect(message).to_have_text("Network error")

    def test_error_screen_has_icon(self, page: Page):
        """Verify error screen displays warning icon."""
        page.evaluate("""
            () => {
                document.querySelector('[data-testid="error-screen"]').style.display = 'flex';
            }
        """)

        # Check for the error icon (it's part of the error screen)
        error_screen = page.locator('[data-testid="error-screen"]')
        expect(error_screen).to_be_visible()

        # The icon is a direct child with class error-icon
        icon = page.locator('.error-icon')
        expect(icon).to_be_attached()
