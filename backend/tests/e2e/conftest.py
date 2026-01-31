"""
Pytest fixtures for Playwright e2e tests.

This module provides:
- Live FastAPI server fixture
- Browser and page fixtures
- Test data (mock scan responses)
"""

import pytest
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright, Page, Browser


# Test server configuration
TEST_HOST = "127.0.0.1"
TEST_PORT = 8765
TEST_BASE_URL = f"http://{TEST_HOST}:{TEST_PORT}"


class ServerThread(threading.Thread):
    """Thread for running the FastAPI server during tests."""

    def __init__(self):
        super().__init__(daemon=True)
        self.server = None

    def run(self):
        # Import here to avoid circular imports
        import sys
        backend_dir = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(backend_dir))

        from main import app

        config = uvicorn.Config(
            app,
            host=TEST_HOST,
            port=TEST_PORT,
            log_level="warning"
        )
        self.server = uvicorn.Server(config)
        self.server.run()


@pytest.fixture(scope="session")
def live_server():
    """Start a live FastAPI server for e2e tests."""
    server_thread = ServerThread()
    server_thread.start()

    # Wait for server to start
    import httpx
    max_retries = 30
    for _ in range(max_retries):
        try:
            response = httpx.get(f"{TEST_BASE_URL}/")
            if response.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Failed to start test server")

    yield TEST_BASE_URL


@pytest.fixture(scope="session")
def browser_context():
    """Create a browser context for the test session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        context.close()
        browser.close()


@pytest.fixture
def page(browser_context, live_server) -> Page:
    """Create a fresh page for each test."""
    page = browser_context.new_page()
    page.goto(f"{live_server}/app")
    yield page
    page.close()


# Test data - mock scan responses
@pytest.fixture
def full_shelf_response():
    """Full shelf response with 8 wines."""
    return {
        "image_id": "test-full-shelf",
        "results": [
            {
                "wine_name": "Caymus Cabernet Sauvignon",
                "rating": 4.5,
                "confidence": 0.94,
                "bbox": {"x": 0.05, "y": 0.15, "width": 0.08, "height": 0.35}
            },
            {
                "wine_name": "Opus One",
                "rating": 4.8,
                "confidence": 0.91,
                "bbox": {"x": 0.15, "y": 0.12, "width": 0.09, "height": 0.38}
            },
            {
                "wine_name": "Silver Oak Alexander Valley",
                "rating": 4.4,
                "confidence": 0.88,
                "bbox": {"x": 0.26, "y": 0.14, "width": 0.08, "height": 0.36}
            },
            {
                "wine_name": "Jordan Cabernet Sauvignon",
                "rating": 4.3,
                "confidence": 0.85,
                "bbox": {"x": 0.36, "y": 0.13, "width": 0.08, "height": 0.37}
            },
            {
                "wine_name": "Kendall-Jackson Vintners Reserve",
                "rating": 3.8,
                "confidence": 0.79,
                "bbox": {"x": 0.46, "y": 0.16, "width": 0.08, "height": 0.34}
            },
            {
                "wine_name": "La Crema Sonoma Coast Pinot Noir",
                "rating": 4.1,
                "confidence": 0.72,
                "bbox": {"x": 0.56, "y": 0.14, "width": 0.08, "height": 0.36}
            },
            {
                "wine_name": "Meiomi Pinot Noir",
                "rating": 3.9,
                "confidence": 0.68,
                "bbox": {"x": 0.66, "y": 0.15, "width": 0.08, "height": 0.35}
            },
            {
                "wine_name": "Bread and Butter Chardonnay",
                "rating": 3.7,
                "confidence": 0.52,
                "bbox": {"x": 0.76, "y": 0.17, "width": 0.08, "height": 0.33}
            },
        ],
        "fallback_list": []
    }


@pytest.fixture
def partial_detection_response():
    """Partial detection with some wines in fallback list."""
    return {
        "image_id": "test-partial",
        "results": [
            {
                "wine_name": "Caymus Cabernet Sauvignon",
                "rating": 4.5,
                "confidence": 0.92,
                "bbox": {"x": 0.10, "y": 0.15, "width": 0.10, "height": 0.35}
            },
            {
                "wine_name": "Opus One",
                "rating": 4.8,
                "confidence": 0.89,
                "bbox": {"x": 0.30, "y": 0.12, "width": 0.10, "height": 0.38}
            },
            {
                "wine_name": "Silver Oak Alexander Valley",
                "rating": 4.4,
                "confidence": 0.86,
                "bbox": {"x": 0.50, "y": 0.14, "width": 0.10, "height": 0.36}
            },
        ],
        "fallback_list": [
            {"wine_name": "Jordan Cabernet Sauvignon", "rating": 4.3},
            {"wine_name": "Kendall-Jackson Vintners Reserve", "rating": 3.8},
            {"wine_name": "La Crema Sonoma Coast Pinot Noir", "rating": 4.1},
        ]
    }


@pytest.fixture
def empty_results_response():
    """Full failure - no overlays, only fallback list."""
    return {
        "image_id": "test-empty",
        "results": [],
        "fallback_list": [
            {"wine_name": "Caymus Cabernet Sauvignon", "rating": 4.5},
            {"wine_name": "Opus One", "rating": 4.8},
            {"wine_name": "Silver Oak Alexander Valley", "rating": 4.4},
            {"wine_name": "Jordan Cabernet Sauvignon", "rating": 4.3},
            {"wine_name": "La Crema Sonoma Coast Pinot Noir", "rating": 4.1},
        ]
    }


@pytest.fixture
def low_confidence_response():
    """Low confidence wines - varying opacity and tappability."""
    return {
        "image_id": "test-low-confidence",
        "results": [
            {
                "wine_name": "Unknown Red Wine",
                "rating": 3.5,
                "confidence": 0.58,
                "bbox": {"x": 0.10, "y": 0.15, "width": 0.12, "height": 0.35}
            },
            {
                "wine_name": "Unknown White Wine",
                "rating": 3.3,
                "confidence": 0.52,
                "bbox": {"x": 0.30, "y": 0.12, "width": 0.12, "height": 0.38}
            },
            {
                "wine_name": "Unknown Rose",
                "rating": 3.6,
                "confidence": 0.48,
                "bbox": {"x": 0.50, "y": 0.14, "width": 0.12, "height": 0.36}
            },
            {
                "wine_name": "Unknown Sparkling",
                "rating": 3.4,
                "confidence": 0.41,  # Below visibility threshold
                "bbox": {"x": 0.70, "y": 0.13, "width": 0.12, "height": 0.37}
            },
        ],
        "fallback_list": [
            {"wine_name": "Possible Cabernet", "rating": 3.8},
            {"wine_name": "Possible Chardonnay", "rating": 3.5},
        ]
    }


# Utility functions for tests
def get_test_image_path() -> Path:
    """Get path to a test image for upload tests."""
    test_images_dir = Path(__file__).parent.parent.parent.parent / "test-images"
    if test_images_dir.exists():
        # Find any image file
        for ext in ['jpg', 'jpeg', 'png']:
            images = list(test_images_dir.glob(f"*.{ext}"))
            if images:
                return images[0]

    # Create a minimal test image if none exists
    # This is a 1x1 red PNG
    import base64
    minimal_png = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    )
    test_image_path = Path(__file__).parent / "test_image.png"
    test_image_path.write_bytes(minimal_png)
    return test_image_path
