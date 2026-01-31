"""
Tests for the upload flow: select image -> see results.
"""

import pytest
from playwright.sync_api import Page, expect


class TestUploadFlow:
    """Tests for the image upload flow."""

    def test_upload_screen_shows_on_load(self, page: Page):
        """Verify upload screen is visible when app loads."""
        upload_screen = page.locator('[data-testid="upload-screen"]')
        expect(upload_screen).to_be_visible()

    def test_scan_button_is_visible(self, page: Page):
        """Verify scan button is visible on upload screen."""
        scan_button = page.locator('[data-testid="scan-button"]')
        expect(scan_button).to_be_visible()
        expect(scan_button).to_have_text("Choose Photo")

    def test_file_input_exists(self, page: Page):
        """Verify file input element exists."""
        file_input = page.locator('[data-testid="image-input"]')
        expect(file_input).to_be_attached()

    def test_upload_area_accepts_drag_drop(self, page: Page):
        """Verify upload area has drag-drop styling."""
        upload_area = page.locator('[data-testid="upload-area"]')
        expect(upload_area).to_be_visible()

    def test_loading_screen_hidden_initially(self, page: Page):
        """Verify loading screen is hidden on initial load."""
        loading_screen = page.locator('[data-testid="loading-screen"]')
        expect(loading_screen).not_to_be_visible()

    def test_results_screen_hidden_initially(self, page: Page):
        """Verify results screen is hidden on initial load."""
        results_screen = page.locator('[data-testid="results-screen"]')
        expect(results_screen).not_to_be_visible()

    def test_error_screen_hidden_initially(self, page: Page):
        """Verify error screen is hidden on initial load."""
        error_screen = page.locator('[data-testid="error-screen"]')
        expect(error_screen).not_to_be_visible()
