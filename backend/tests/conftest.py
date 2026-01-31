"""
Pytest configuration for the wine shelf scanner tests.
"""

import json
import pytest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# Configure pytest-asyncio to use auto mode for async tests
def pytest_configure(config):
    """Configure pytest-asyncio mode."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test"
    )


def pytest_collection_modifyitems(config, items):
    """
    Reorder tests so e2e tests run last.

    The e2e tests start a uvicorn server which can corrupt asyncio state
    for subsequent async tests. Running e2e tests last avoids this issue.
    """
    e2e_tests = []
    other_tests = []

    for item in items:
        if "/e2e/" in str(item.fspath) or "\\e2e\\" in str(item.fspath):
            e2e_tests.append(item)
        else:
            other_tests.append(item)

    # Reorder: unit tests first, then e2e tests
    items[:] = other_tests + e2e_tests


def load_ground_truth(image_name: str) -> dict:
    """Load ground truth expectations for a test image."""
    path = FIXTURES_DIR / "ground_truth" / f"{image_name}.json"
    with open(path) as f:
        return json.load(f)


def load_vision_response(image_name: str):
    """Load captured Vision API response for replay in tests."""
    path = FIXTURES_DIR / "vision_responses" / f"{image_name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None
