"""
Pytest configuration for the wine shelf scanner tests.
"""

import json
import pytest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"
DATA_DIR = Path(__file__).parent.parent / "app" / "data"


# Configure pytest-asyncio to use auto mode for async tests
def pytest_configure(config):
    """Configure pytest-asyncio mode."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test"
    )

    # Mark the service as ready for tests (bypasses warmup middleware)
    # This is needed because TestClient doesn't trigger lifespan events
    from main import set_ready
    set_ready(True)


def pytest_sessionstart(session):
    """Seed test database and mark app ready for tests.

    In CI, wines.db doesn't exist (stored in GCS, not git).
    This seeds the SQLite DB with 60 wines from ratings.json so
    tests that depend on finding wines like "Opus One" pass.
    """
    _seed_test_db()

    # Mark app as ready so warmup middleware doesn't return 503 in tests.
    # The warmup middleware is a production concern (Cloud Run cold starts).
    from main import set_ready
    set_ready(True)


def _seed_test_db():
    """Seed test database from ratings.json if wines.db is empty."""
    from app.config import Config

    if not Config.use_sqlite():
        return

    db_path = Path(Config.database_path())
    ratings_path = DATA_DIR / "ratings.json"

    if not ratings_path.exists():
        return

    # Import repository to create/open DB and check if it needs seeding
    from app.services.wine_repository import WineRepository
    repo = WineRepository(str(db_path))

    if repo.count() > 0:
        repo.close()
        return

    # Seed from ratings.json
    with open(ratings_path) as f:
        data = json.load(f)

    wines = []
    for wine in data.get("wines", []):
        wines.append({
            "canonical_name": wine["canonical_name"],
            "rating": wine["rating"],
            "aliases": wine.get("aliases", []),
            "wine_type": wine.get("wine_type"),
            "region": wine.get("region"),
            "winery": wine.get("winery"),
            "country": wine.get("country"),
            "varietal": wine.get("varietal"),
        })

    inserted, skipped = repo.bulk_insert(wines)
    repo.close()

    # Clear any cached matcher state from previous test runs
    from app.services.wine_matcher import WineMatcher
    WineMatcher.clear_cache()


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
