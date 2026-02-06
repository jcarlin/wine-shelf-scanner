"""Tests for wine_sync.sync_discovered_wines — review/blurb persistence."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.db import ensure_schema
from app.models.enums import WineSource
from app.services.llm_rating_cache import LLMRatingCache
from app.services.wine_repository import WineRepository


@pytest.fixture
def db_path(tmp_path):
    """Create a fresh DB with schema applied."""
    path = str(tmp_path / "test.db")
    ensure_schema(path)
    return path


@pytest.fixture
def repo(db_path):
    return WineRepository(db_path=db_path)


@pytest.fixture
def cache(db_path):
    return LLMRatingCache(db_path=db_path)


@pytest.fixture
def patched_sync(db_path, repo, cache):
    """Patch the lazy imports inside sync_discovered_wines to use test DB.

    The function uses lazy ``from .wine_repository import WineRepository``
    inside its body.  We patch the *source* modules so the lazy import
    picks up our test instances.
    """
    # WineRepository is a class — we need a callable that returns our repo
    mock_repo_cls = lambda *a, **kw: repo
    # get_llm_rating_cache is a function
    mock_cache_fn = lambda: cache

    with patch("app.services.wine_repository.WineRepository", mock_repo_cls), \
         patch("app.services.llm_rating_cache.get_llm_rating_cache", mock_cache_fn):
        from app.services.wine_sync import sync_discovered_wines
        yield sync_discovered_wines


def _make_wine(name="Test Cabernet", rating=4.5, source=WineSource.LLM,
               blurb=None, review_snippets=None, **kwargs):
    """Build a mock wine result object."""
    return SimpleNamespace(
        wine_name=name,
        rating=rating,
        source=source,
        blurb=blurb,
        review_snippets=review_snippets,
        wine_type=kwargs.get("wine_type"),
        brand=kwargs.get("brand"),
        region=kwargs.get("region"),
        varietal=kwargs.get("varietal"),
    )


def _get_reviews(repo, wine_name):
    """Fetch wine_reviews rows for a wine by name."""
    record = repo.find_by_name(wine_name)
    if record is None:
        return []
    return repo.get_reviews(record.id, text_only=False)


# ── Tests ────────────────────────────────────────────────────────────────


class TestSyncPersistsBlurbAsDescription:
    def test_sync_persists_blurb_as_description(self, repo, patched_sync):
        wine = _make_wine(blurb="A velvety Napa Cab with dark fruit and oak.")
        count = patched_sync(results=[wine])

        assert count == 1
        record = repo.find_by_name("Test Cabernet")
        assert record is not None
        assert record.description == "A velvety Napa Cab with dark fruit and oak."


class TestSyncPersistsReviewSnippets:
    def test_sync_persists_review_snippets(self, repo, patched_sync):
        snippets = ["Rich and full-bodied", "Notes of blackberry and tobacco"]
        wine = _make_wine(review_snippets=snippets)
        count = patched_sync(results=[wine])

        assert count == 1
        reviews = _get_reviews(repo, "Test Cabernet")
        assert len(reviews) == 2
        texts = {r.review_text for r in reviews}
        assert texts == set(snippets)
        assert all(r.source_name == "llm_generated" for r in reviews)


class TestSyncFallbackPersistsBlurbFromCache:
    def test_sync_fallback_persists_blurb_from_cache(self, repo, cache, patched_sync):
        # Pre-populate cache with blurb
        cache.set(
            wine_name="Château Margaux",
            estimated_rating=4.8,
            confidence=0.9,
            llm_provider="claude",
            blurb="Legendary Bordeaux with elegant tannins.",
            wine_type="Red",
            region="Bordeaux",
        )
        fallback = SimpleNamespace(wine_name="Château Margaux", rating=4.8)
        count = patched_sync(results=[], fallback=[fallback])

        assert count == 1
        record = repo.find_by_name("Château Margaux")
        assert record is not None
        assert record.description == "Legendary Bordeaux with elegant tannins."


class TestSyncFallbackPersistsReviewSnippetsFromCache:
    def test_sync_fallback_persists_review_snippets_from_cache(self, repo, cache, patched_sync):
        snippets = ["Silky and refined", "Long finish"]
        cache.set(
            wine_name="Penfolds Grange",
            estimated_rating=4.7,
            confidence=0.85,
            llm_provider="gemini",
            review_snippets=snippets,
        )
        fallback = SimpleNamespace(wine_name="Penfolds Grange", rating=4.7)
        count = patched_sync(results=[], fallback=[fallback])

        assert count == 1
        reviews = _get_reviews(repo, "Penfolds Grange")
        assert len(reviews) == 2
        texts = {r.review_text for r in reviews}
        assert texts == set(snippets)
        assert all(r.source_name == "llm_generated" for r in reviews)


class TestSyncWithoutBlurbOrSnippets:
    def test_sync_without_blurb_or_snippets(self, repo, patched_sync):
        wine = _make_wine(name="Plain Wine", rating=3.9)
        count = patched_sync(results=[wine])

        assert count == 1
        record = repo.find_by_name("Plain Wine")
        assert record is not None
        assert record.description is None
        reviews = _get_reviews(repo, "Plain Wine")
        assert reviews == []


class TestSyncEmptySnippetsNoReviewsCreated:
    def test_empty_list_creates_no_reviews(self, repo, patched_sync):
        wine = _make_wine(name="Empty List Wine", rating=4.0, review_snippets=[])
        count = patched_sync(results=[wine])

        assert count == 1
        reviews = _get_reviews(repo, "Empty List Wine")
        assert reviews == []

    def test_none_snippets_creates_no_reviews(self, repo, patched_sync):
        wine = _make_wine(name="None Snippets Wine", rating=4.0, review_snippets=None)
        count = patched_sync(results=[wine])

        assert count == 1
        reviews = _get_reviews(repo, "None Snippets Wine")
        assert reviews == []
