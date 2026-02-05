"""Tests for the /report bug reporting endpoint."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.routes.report import ReportRepository, ReportRequest, ReportMetadata


# === Repository Tests ===


SCHEMA_PATH = Path(__file__).parent.parent / "app" / "data" / "schema.sql"


def _apply_schema(db_path: str):
    """Apply the canonical schema.sql to a test database."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.close()


@pytest.fixture
def repo(tmp_path):
    """Create a repository backed by a temp database with schema pre-applied."""
    db_path = str(tmp_path / "test.db")
    _apply_schema(db_path)
    return ReportRepository(db_path=db_path)


def make_report(**overrides) -> ReportRequest:
    """Create a ReportRequest with sensible defaults."""
    defaults = {
        "report_type": "error",
        "error_type": "NETWORK_ERROR",
        "error_message": "Unable to connect",
        "device_id": "test-device-123",
        "platform": "ios",
        "app_version": "1.0.0",
    }
    defaults.update(overrides)
    return ReportRequest(**defaults)


class TestReportRepository:
    def test_add_report_returns_id(self, repo):
        report = make_report()
        report_id = repo.add_report(report)
        assert report_id is not None
        assert len(report_id) == 36  # UUID format

    def test_add_report_stores_data(self, repo):
        report = make_report(
            report_type="partial_detection",
            error_message="Some bottles missing",
            image_id="img-abc",
            user_description="Only found 2 of 5 bottles",
        )
        report_id = repo.add_report(report)

        conn = sqlite3.connect(repo.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()

        assert row["report_type"] == "partial_detection"
        assert row["error_message"] == "Some bottles missing"
        assert row["image_id"] == "img-abc"
        assert row["user_description"] == "Only found 2 of 5 bottles"
        assert row["device_id"] == "test-device-123"
        assert row["platform"] == "ios"
        conn.close()

    def test_add_report_with_metadata(self, repo):
        import json
        metadata = ReportMetadata(
            wines_detected=2,
            wines_in_fallback=5,
            confidence_scores=[0.42, 0.38],
        )
        report = make_report(metadata=metadata)
        report_id = repo.add_report(report)

        conn = sqlite3.connect(repo.db_path)
        row = conn.execute("SELECT metadata FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
        meta = json.loads(row[0])
        assert meta["wines_detected"] == 2
        assert meta["wines_in_fallback"] == 5
        assert meta["confidence_scores"] == [0.42, 0.38]
        conn.close()

    def test_add_report_without_metadata(self, repo):
        report = make_report()
        report_id = repo.add_report(report)

        conn = sqlite3.connect(repo.db_path)
        row = conn.execute("SELECT metadata FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
        assert row[0] is None
        conn.close()

    def test_get_stats_empty(self, repo):
        stats = repo.get_stats()
        assert stats["total_reports"] == 0
        assert stats["by_type"] == {}
        assert stats["by_platform"] == {}

    def test_get_stats_with_reports(self, repo):
        repo.add_report(make_report(report_type="error", platform="ios"))
        repo.add_report(make_report(report_type="error", platform="web"))
        repo.add_report(make_report(report_type="partial_detection", platform="ios"))

        stats = repo.get_stats()
        assert stats["total_reports"] == 3
        assert stats["by_type"]["error"] == 2
        assert stats["by_type"]["partial_detection"] == 1
        assert stats["by_platform"]["ios"] == 2
        assert stats["by_platform"]["web"] == 1

    def test_unique_report_ids(self, repo):
        ids = set()
        for _ in range(10):
            report_id = repo.add_report(make_report())
            ids.add(report_id)
        assert len(ids) == 10


# === API Endpoint Tests ===


@pytest.fixture
def client(tmp_path):
    """Create a test client with isolated database."""
    from app.routes import report as report_module
    from main import app

    # Create schema before constructing repository
    db_path = str(tmp_path / "test.db")
    _apply_schema(db_path)
    test_repo = ReportRepository(db_path=db_path)
    original_repo = report_module._report_repo
    report_module._report_repo = test_repo

    yield TestClient(app)

    # Restore
    report_module._report_repo = original_repo


class TestReportEndpoint:
    def test_submit_report_success(self, client):
        response = client.post("/report", json={
            "report_type": "error",
            "error_type": "NETWORK_ERROR",
            "error_message": "Connection failed",
            "device_id": "device-abc",
            "platform": "ios",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "report_id" in data

    def test_submit_report_minimal(self, client):
        response = client.post("/report", json={
            "report_type": "full_failure",
            "device_id": "device-xyz",
            "platform": "web",
        })
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_submit_report_with_metadata(self, client):
        response = client.post("/report", json={
            "report_type": "partial_detection",
            "device_id": "device-abc",
            "platform": "ios",
            "metadata": {
                "wines_detected": 3,
                "wines_in_fallback": 5,
            },
        })
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_submit_report_missing_required_fields(self, client):
        response = client.post("/report", json={
            "report_type": "error",
        })
        assert response.status_code == 422

    def test_user_description_max_length(self, client):
        response = client.post("/report", json={
            "report_type": "error",
            "device_id": "device-abc",
            "platform": "ios",
            "user_description": "x" * 501,
        })
        assert response.status_code == 422

    def test_get_report_stats(self, client):
        # Submit some reports
        for platform in ["ios", "web", "ios"]:
            client.post("/report", json={
                "report_type": "error",
                "device_id": "device-abc",
                "platform": platform,
            })

        response = client.get("/report/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_reports"] == 3
        assert stats["by_platform"]["ios"] == 2
        assert stats["by_platform"]["web"] == 1
