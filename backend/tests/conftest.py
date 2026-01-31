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
