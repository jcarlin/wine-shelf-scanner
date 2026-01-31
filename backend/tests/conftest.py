"""
Pytest configuration for the wine shelf scanner tests.
"""

import pytest


# Configure pytest-asyncio to use auto mode for async tests
def pytest_configure(config):
    """Configure pytest-asyncio mode."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test"
    )
