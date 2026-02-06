"""Tests for the /wines/{id}/reviews endpoint and review repository methods."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import ensure_schema
from app.services.wine_repository import WineRepository, WineReview


# === Repository Tests ===


@pytest.fixture
def repo(tmp_path):
    """Create a repository backed by a temp database with schema pre-applied."""
    db_path = str(tmp_path / "test.db")
    ensure_schema(db_path)
    return WineRepository(db_path=db_path)


def _seed_wine(repo, name="Test Cabernet", rating=4.5):
    """Insert a wine and return its ID."""
    return repo.add_wine(canonical_name=name, rating=rating)


def _seed_review(repo, wine_id, source="kaggle_winemag", rating=4.0,
                 review_text=None, user_id=None):
    """Insert a review directly via SQL."""
    conn = repo._get_connection()
    conn.execute(
        """INSERT INTO wine_reviews (wine_id, source_name, user_id, rating, review_text)
           VALUES (?, ?, ?, ?, ?)""",
        (wine_id, source, user_id, rating, review_text),
    )
    conn.commit()


class TestGetReviews:
    def test_returns_empty_for_no_reviews(self, repo):
        wine_id = _seed_wine(repo)
        reviews = repo.get_reviews(wine_id)
        assert reviews == []

    def test_returns_text_reviews_only_by_default(self, repo):
        wine_id = _seed_wine(repo)
        _seed_review(repo, wine_id, review_text="Lovely nose of cherry")
        _seed_review(repo, wine_id, review_text=None)  # rating-only

        reviews = repo.get_reviews(wine_id, text_only=True)
        assert len(reviews) == 1
        assert reviews[0].review_text == "Lovely nose of cherry"

    def test_returns_all_reviews_when_text_only_false(self, repo):
        wine_id = _seed_wine(repo)
        _seed_review(repo, wine_id, review_text="Great wine")
        _seed_review(repo, wine_id, review_text=None)

        reviews = repo.get_reviews(wine_id, text_only=False)
        assert len(reviews) == 2

    def test_respects_limit(self, repo):
        wine_id = _seed_wine(repo)
        for i in range(5):
            _seed_review(repo, wine_id, review_text=f"Review {i}")

        reviews = repo.get_reviews(wine_id, limit=3)
        assert len(reviews) == 3

    def test_review_fields_populated(self, repo):
        wine_id = _seed_wine(repo)
        _seed_review(repo, wine_id, source="kaggle_winemag", rating=4.5,
                     review_text="Ripe aromas of fig", user_id="Roger Voss")

        reviews = repo.get_reviews(wine_id)
        assert len(reviews) == 1
        r = reviews[0]
        assert r.source_name == "kaggle_winemag"
        assert r.user_id == "Roger Voss"
        assert r.rating == 4.5
        assert r.review_text == "Ripe aromas of fig"


class TestGetReviewStats:
    def test_stats_for_no_reviews(self, repo):
        wine_id = _seed_wine(repo)
        stats = repo.get_review_stats(wine_id)
        assert stats["total_reviews"] == 0
        assert stats["avg_rating"] is None
        assert stats["text_reviews"] == 0

    def test_stats_with_mixed_reviews(self, repo):
        wine_id = _seed_wine(repo)
        _seed_review(repo, wine_id, rating=4.0, review_text="Good")
        _seed_review(repo, wine_id, rating=3.0, review_text=None)
        _seed_review(repo, wine_id, rating=5.0, review_text="Excellent")

        stats = repo.get_review_stats(wine_id)
        assert stats["total_reviews"] == 3
        assert stats["avg_rating"] == 4.0
        assert stats["text_reviews"] == 2


# === API Endpoint Tests ===


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with a temp database."""
    db_path = str(tmp_path / "test.db")
    ensure_schema(db_path)

    # Patch the repository factory in the reviews route
    test_repo = WineRepository(db_path=db_path)

    from app.routes import reviews as reviews_module
    monkeypatch.setattr(reviews_module, "_get_repository", lambda: test_repo)

    from main import app
    return TestClient(app), test_repo


class TestReviewsEndpoint:
    def test_404_for_missing_wine(self, client):
        test_client, repo = client
        response = test_client.get("/wines/99999/reviews")
        assert response.status_code == 404

    def test_empty_reviews(self, client):
        test_client, repo = client
        wine_id = _seed_wine(repo, "Opus One", 4.8)

        response = test_client.get(f"/wines/{wine_id}/reviews")
        assert response.status_code == 200
        data = response.json()
        assert data["wine_id"] == wine_id
        assert data["wine_name"] == "Opus One"
        assert data["total_reviews"] == 0
        assert data["reviews"] == []

    def test_with_reviews(self, client):
        test_client, repo = client
        wine_id = _seed_wine(repo, "Caymus Cabernet", 4.6)
        _seed_review(repo, wine_id, review_text="Bold and complex", rating=4.5,
                     user_id="Roger Voss")
        _seed_review(repo, wine_id, review_text=None, rating=3.5)

        response = test_client.get(f"/wines/{wine_id}/reviews")
        assert response.status_code == 200
        data = response.json()
        assert data["total_reviews"] == 2
        assert data["text_reviews"] == 1
        assert len(data["reviews"]) == 1  # text_only=True by default
        assert data["reviews"][0]["review_text"] == "Bold and complex"
        assert data["reviews"][0]["reviewer"] == "Roger Voss"

    def test_text_only_false(self, client):
        test_client, repo = client
        wine_id = _seed_wine(repo, "Test Wine", 4.0)
        _seed_review(repo, wine_id, review_text="Good", rating=4.0)
        _seed_review(repo, wine_id, review_text=None, rating=3.0)

        response = test_client.get(f"/wines/{wine_id}/reviews?text_only=false")
        assert response.status_code == 200
        data = response.json()
        assert len(data["reviews"]) == 2

    def test_limit_parameter(self, client):
        test_client, repo = client
        wine_id = _seed_wine(repo, "Test Wine", 4.0)
        for i in range(5):
            _seed_review(repo, wine_id, review_text=f"Review {i}", rating=4.0)

        response = test_client.get(f"/wines/{wine_id}/reviews?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["reviews"]) == 2

    def test_limit_validation(self, client):
        test_client, repo = client
        response = test_client.get("/wines/1/reviews?limit=0")
        assert response.status_code == 422

        response = test_client.get("/wines/1/reviews?limit=100")
        assert response.status_code == 422
