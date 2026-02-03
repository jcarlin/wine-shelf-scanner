"""
E2E tests using real test images with ground truth validation.

These tests validate that scan results are meaningful by checking
detected wines against known image contents.

When vision response fixtures are available in tests/fixtures/vision_responses/,
tests run in deterministic replay mode. Otherwise, they use the live Vision API.
"""

import json
import pytest
from pathlib import Path
from typing import Optional
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)

# Paths
TEST_IMAGES = Path(__file__).parent.parent.parent / "test-images"
GROUND_TRUTH = Path(__file__).parent / "fixtures" / "ground_truth"
VISION_FIXTURES = Path(__file__).parent / "fixtures" / "vision_responses"


def load_ground_truth(image_name: str) -> dict:
    """Load ground truth expectations for a test image."""
    path = GROUND_TRUTH / f"{image_name}.json"
    with open(path) as f:
        return json.load(f)


def get_vision_fixture(image_name: str) -> Optional[Path]:
    """Get path to vision response fixture if it exists."""
    fixture_path = VISION_FIXTURES / f"{image_name}.json"
    return fixture_path if fixture_path.exists() else None


def build_scan_url(vision_fixture: Optional[Path], use_llm: bool = True) -> str:
    """Build scan URL with appropriate parameters."""
    if vision_fixture:
        # Use captured fixture for deterministic replay
        # Note: With exact-match-only architecture, LLM is required for OCR normalization
        # Keep LLM enabled by default since exact matching alone can't handle OCR fragments
        llm_param = "&use_llm=true" if use_llm else "&use_llm=false"
        return f"/scan?use_vision_fixture={vision_fixture}{llm_param}"
    else:
        # Fall back to live Vision API
        llm_param = "&use_llm=true" if use_llm else "&use_llm=false"
        return f"/scan?use_vision_api=true{llm_param}"


class TestRealImageDetection:
    """Validate scan results against known image contents."""

    @pytest.mark.parametrize("image_name,image_file", [
        ("wine1_jpeg", "wine1.jpeg"),
        ("wine_photos_jpg", "wine-photos.jpg"),
    ])
    def test_detects_expected_wines(self, image_name: str, image_file: str):
        """Required wines from ground truth should be detected."""
        # Skip if test image doesn't exist
        image_path = TEST_IMAGES / image_file
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        # Load ground truth
        truth = load_ground_truth(image_name)

        # Check for vision fixture (deterministic mode)
        vision_fixture = get_vision_fixture(image_name)
        scan_url = build_scan_url(vision_fixture)

        # Scan image
        with open(image_path, "rb") as f:
            response = client.post(
                scan_url,
                files={"image": (image_file, f, "image/jpeg")}
            )

        assert response.status_code == 200, f"Scan failed: {response.text}"
        data = response.json()

        # Check count bounds
        total_count = len(data["results"]) + len(data["fallback_list"])
        assert total_count >= truth["min_result_count"], (
            f"Too few wines detected: {total_count} < {truth['min_result_count']}"
        )
        assert len(data["results"]) <= truth["max_result_count"], (
            f"Too many results: {len(data['results'])} > {truth['max_result_count']}"
        )

        # Collect all wine names (results + fallback)
        all_names = [r["wine_name"].lower() for r in data["results"]]
        all_names += [f["wine_name"].lower() for f in data["fallback_list"]]

        # Check required wines found
        for expected in truth["expected_wines"]:
            if expected.get("required"):
                pattern = expected["name_pattern"].lower()
                found = any(pattern in name for name in all_names)
                assert found, (
                    f"Required wine '{pattern}' not found in detected wines: {all_names}"
                )

    def test_wine1_results_are_meaningful(self):
        """wine1.jpeg results should look like real wine names."""
        image_path = TEST_IMAGES / "wine1.jpeg"
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        vision_fixture = get_vision_fixture("wine1_jpeg")
        scan_url = build_scan_url(vision_fixture)

        with open(image_path, "rb") as f:
            response = client.post(
                scan_url,
                files={"image": ("wine1.jpeg", f, "image/jpeg")}
            )

        assert response.status_code == 200
        data = response.json()

        # Should have some results
        assert len(data["results"]) > 0, "No wines detected in wine1.jpeg"

        for result in data["results"]:
            name = result["wine_name"]

            # Name should not be garbage
            assert len(name) >= 3, f"Wine name too short: '{name}'"
            assert any(c.isalpha() for c in name), f"Wine name has no letters: '{name}'"

            # Should have a rating or be low confidence
            if result["confidence"] >= 0.7:
                assert result["rating"] is not None, (
                    f"High-confidence wine '{name}' has no rating"
                )

    def test_wine1_bbox_positions_are_reasonable(self):
        """wine1.jpeg bounding boxes should be in reasonable positions."""
        image_path = TEST_IMAGES / "wine1.jpeg"
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        vision_fixture = get_vision_fixture("wine1_jpeg")
        scan_url = build_scan_url(vision_fixture)

        with open(image_path, "rb") as f:
            response = client.post(
                scan_url,
                files={"image": ("wine1.jpeg", f, "image/jpeg")}
            )

        assert response.status_code == 200
        data = response.json()

        for result in data["results"]:
            bbox = result["bbox"]

            # Bounding boxes should be normalized (0-1)
            assert 0 <= bbox["x"] <= 1, f"bbox x out of range: {bbox['x']}"
            assert 0 <= bbox["y"] <= 1, f"bbox y out of range: {bbox['y']}"
            assert 0 < bbox["width"] <= 1, f"bbox width invalid: {bbox['width']}"
            assert 0 < bbox["height"] <= 1, f"bbox height invalid: {bbox['height']}"

            # Box should fit within image
            assert bbox["x"] + bbox["width"] <= 1.01, (
                f"bbox extends past right edge: x={bbox['x']}, width={bbox['width']}"
            )
            assert bbox["y"] + bbox["height"] <= 1.01, (
                f"bbox extends past bottom edge: y={bbox['y']}, height={bbox['height']}"
            )

    def test_no_duplicate_wine_names(self):
        """Detected wines should not have exact duplicate names."""
        image_path = TEST_IMAGES / "wine1.jpeg"
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        vision_fixture = get_vision_fixture("wine1_jpeg")
        scan_url = build_scan_url(vision_fixture)

        with open(image_path, "rb") as f:
            response = client.post(
                scan_url,
                files={"image": ("wine1.jpeg", f, "image/jpeg")}
            )

        assert response.status_code == 200
        data = response.json()

        # Check for duplicates in results
        result_names = [r["wine_name"].lower() for r in data["results"]]
        unique_names = set(result_names)

        # Allow some duplicates (same wine might appear multiple times on shelf)
        # Wine shelves often show multiple bottles of the same wine, so 70% threshold
        duplicate_ratio = 1 - (len(unique_names) / max(len(result_names), 1))
        assert duplicate_ratio <= 0.7, (
            f"Too many duplicate wines: {duplicate_ratio:.0%} duplicates in {result_names}"
        )


class TestRealImageEdgeCases:
    """Edge case tests using real images."""

    def test_scan_without_llm_still_works(self):
        """Scanning with LLM disabled should return valid response.

        With exact-match-only architecture, results without LLM will be limited
        to exact name/alias matches and FTS prefix matches. This test validates
        the endpoint works correctly, not that it finds wines.
        """
        image_path = TEST_IMAGES / "wine1.jpeg"
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        vision_fixture = get_vision_fixture("wine1_jpeg")
        if vision_fixture:
            scan_url = f"/scan?use_vision_fixture={vision_fixture}&use_llm=false"
        else:
            scan_url = "/scan?use_vision_api=true&use_llm=false"

        with open(image_path, "rb") as f:
            response = client.post(
                scan_url,
                files={"image": ("wine1.jpeg", f, "image/jpeg")}
            )

        assert response.status_code == 200
        data = response.json()

        # Endpoint should return valid response structure
        assert "results" in data
        assert "fallback_list" in data
        assert "image_id" in data
        # With exact matching only, we may not find wines from OCR fragments
        # The test validates the endpoint works, not that it finds specific wines

    def test_response_matches_api_contract(self):
        """Response should match the documented API contract."""
        image_path = TEST_IMAGES / "wine1.jpeg"
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        vision_fixture = get_vision_fixture("wine1_jpeg")
        scan_url = build_scan_url(vision_fixture)

        with open(image_path, "rb") as f:
            response = client.post(
                scan_url,
                files={"image": ("wine1.jpeg", f, "image/jpeg")}
            )

        assert response.status_code == 200
        data = response.json()

        # Required top-level fields
        assert "image_id" in data
        assert "results" in data
        assert "fallback_list" in data
        assert isinstance(data["image_id"], str)
        assert isinstance(data["results"], list)
        assert isinstance(data["fallback_list"], list)

        # Result item structure
        for result in data["results"]:
            assert "wine_name" in result
            assert "rating" in result
            assert "confidence" in result
            assert "bbox" in result

            # Bbox structure
            bbox = result["bbox"]
            assert "x" in bbox
            assert "y" in bbox
            assert "width" in bbox
            assert "height" in bbox

        # Fallback item structure
        for fallback in data["fallback_list"]:
            assert "wine_name" in fallback
            assert "rating" in fallback
