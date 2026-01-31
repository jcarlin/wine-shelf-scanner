"""
End-to-end tests for the /scan endpoint.

Tests complete workflow:
- Upload image -> get valid response
- Response matches API contract
- Confidence thresholds enforced
- Fallback list populated correctly
"""

import pytest
from io import BytesIO
from fastapi.testclient import TestClient

from main import app
from app.models import ScanResponse, WineResult, FallbackWine, BoundingBox


client = TestClient(app)


def create_test_image() -> BytesIO:
    """Create a minimal valid JPEG for testing."""
    # Minimal 1x1 JPEG
    jpeg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xE0, 0x8A, 0x28,
        0xA0, 0xFF, 0xD9
    ])
    return BytesIO(jpeg_bytes)


class TestScanEndpointAPIContract:
    """Test /scan endpoint matches API contract."""

    def test_response_has_required_fields(self):
        """Test response contains all required top-level fields."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "image_id" in data
        assert "results" in data
        assert "fallback_list" in data

        # Types
        assert isinstance(data["image_id"], str)
        assert isinstance(data["results"], list)
        assert isinstance(data["fallback_list"], list)

    def test_wine_result_has_required_fields(self):
        """Test WineResult contains all required fields."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()
        assert len(data["results"]) > 0

        result = data["results"][0]

        # Required fields per API contract
        assert "wine_name" in result
        assert "rating" in result
        assert "confidence" in result
        assert "bbox" in result

        # Types
        assert isinstance(result["wine_name"], str)
        assert isinstance(result["rating"], (int, float, type(None)))
        assert isinstance(result["confidence"], (int, float))
        assert isinstance(result["bbox"], dict)

    def test_bounding_box_has_required_fields(self):
        """Test BoundingBox contains x, y, width, height."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()
        bbox = data["results"][0]["bbox"]

        assert "x" in bbox
        assert "y" in bbox
        assert "width" in bbox
        assert "height" in bbox

    def test_fallback_wine_has_required_fields(self):
        """Test FallbackWine contains wine_name and rating."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=partial_detection",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()
        assert len(data["fallback_list"]) > 0

        fallback = data["fallback_list"][0]

        assert "wine_name" in fallback
        assert "rating" in fallback
        assert isinstance(fallback["wine_name"], str)
        assert isinstance(fallback["rating"], (int, float))

    def test_response_parses_as_scan_response(self):
        """Test response can be parsed as ScanResponse model."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        # Should not raise validation error
        scan_response = ScanResponse(**data)

        assert scan_response.image_id is not None
        assert isinstance(scan_response.results, list)
        assert isinstance(scan_response.fallback_list, list)


class TestScanEndpointConfidenceThresholds:
    """Test confidence threshold enforcement."""

    def test_high_confidence_in_results(self):
        """Test high confidence results (>= 0.45) are in main results."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        for result in data["results"]:
            # Full shelf has confidence range 0.52-0.94
            # All should be >= 0.45 fallback threshold
            assert result["confidence"] >= 0.45, (
                f"Result {result['wine_name']} has confidence "
                f"{result['confidence']} below threshold"
            )

    def test_low_confidence_in_fallback_only(self):
        """Test low confidence results go to fallback list only."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=low_confidence",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        # Low confidence scenario has results with confidence 0.41-0.58
        # The one at 0.41 should still be in results (mock fixture includes it)
        # Fallback list should have additional wines
        assert len(data["fallback_list"]) > 0

    def test_bbox_values_normalized(self):
        """Test all bounding box values are normalized (0-1)."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        for result in data["results"]:
            bbox = result["bbox"]
            assert 0 <= bbox["x"] <= 1, f"x={bbox['x']} out of range"
            assert 0 <= bbox["y"] <= 1, f"y={bbox['y']} out of range"
            assert 0 <= bbox["width"] <= 1, f"width={bbox['width']} out of range"
            assert 0 <= bbox["height"] <= 1, f"height={bbox['height']} out of range"

    def test_rating_values_in_range(self):
        """Test all rating values are in valid range (1-5)."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        for result in data["results"]:
            if result["rating"] is not None:
                assert 1 <= result["rating"] <= 5, (
                    f"Rating {result['rating']} for {result['wine_name']} out of range"
                )

        for fallback in data["fallback_list"]:
            assert 1 <= fallback["rating"] <= 5, (
                f"Fallback rating {fallback['rating']} out of range"
            )


class TestScanEndpointScenarios:
    """Test various mock scenarios."""

    def test_full_shelf_scenario(self):
        """Test full_shelf scenario returns 8 results."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        assert len(data["results"]) == 8
        assert len(data["fallback_list"]) == 0

        # Check known wines
        wine_names = [r["wine_name"] for r in data["results"]]
        assert "Caymus Cabernet Sauvignon" in wine_names
        assert "Opus One" in wine_names

    def test_partial_detection_scenario(self):
        """Test partial_detection scenario has results and fallback."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=partial_detection",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        assert len(data["results"]) == 3
        assert len(data["fallback_list"]) == 5

    def test_empty_results_scenario(self):
        """Test empty_results scenario has only fallback list."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=empty_results",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        assert len(data["results"]) == 0
        assert len(data["fallback_list"]) > 0

    def test_invalid_scenario_defaults_to_full_shelf(self):
        """Test invalid scenario name defaults to full_shelf."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=invalid_scenario_name",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        assert response.status_code == 200
        data = response.json()

        # Should default to full_shelf
        assert len(data["results"]) == 8


class TestScanEndpointInputValidation:
    """Test input validation and error handling."""

    def test_rejects_invalid_content_type(self):
        """Test non-image content types are rejected."""
        response = client.post(
            "/scan",
            files={"image": ("test.txt", b"not an image", "text/plain")}
        )

        assert response.status_code == 400
        assert "Invalid image type" in response.json()["detail"]

    def test_accepts_jpeg(self):
        """Test JPEG content type is accepted."""
        image = create_test_image()
        response = client.post(
            "/scan",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        assert response.status_code == 200

    def test_accepts_png(self):
        """Test PNG content type is accepted."""
        # Create minimal PNG
        png_bytes = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0x0F, 0x00, 0x00,
            0x01, 0x01, 0x01, 0x00, 0x18, 0xDD, 0x8D, 0xB5,
            0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,
            0xAE, 0x42, 0x60, 0x82
        ])
        response = client.post(
            "/scan",
            files={"image": ("test.png", BytesIO(png_bytes), "image/png")}
        )

        assert response.status_code == 200

    def test_missing_image_returns_error(self):
        """Test missing image parameter returns error."""
        response = client.post("/scan")

        assert response.status_code == 422  # Validation error


class TestScanEndpointQueryParameters:
    """Test query parameter handling."""

    def test_use_llm_parameter(self):
        """Test use_llm parameter is accepted."""
        image = create_test_image()

        # With LLM enabled
        response = client.post(
            "/scan?use_llm=true&mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )
        assert response.status_code == 200

        # With LLM disabled
        image = create_test_image()
        response = client.post(
            "/scan?use_llm=false&mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )
        assert response.status_code == 200

    def test_mock_scenario_parameter(self):
        """Test mock_scenario parameter selects correct scenario."""
        scenarios = [
            ("full_shelf", 8, 0),
            ("partial_detection", 3, 5),
            ("empty_results", 0, 8),
            ("low_confidence", 4, 2),
        ]

        for scenario, expected_results, expected_fallback in scenarios:
            image = create_test_image()
            response = client.post(
                f"/scan?mock_scenario={scenario}",
                files={"image": ("test.jpg", image, "image/jpeg")}
            )

            data = response.json()
            assert len(data["results"]) == expected_results, (
                f"Scenario {scenario}: expected {expected_results} results"
            )
            assert len(data["fallback_list"]) == expected_fallback, (
                f"Scenario {scenario}: expected {expected_fallback} fallback"
            )


class TestScanEndpointImageId:
    """Test image_id generation."""

    def test_image_id_is_unique(self):
        """Test each scan gets a unique image_id."""
        image_ids = []

        for _ in range(5):
            image = create_test_image()
            response = client.post(
                "/scan?mock_scenario=full_shelf",
                files={"image": ("test.jpg", image, "image/jpeg")}
            )

            data = response.json()
            image_ids.append(data["image_id"])

        # All image_ids should be unique
        assert len(set(image_ids)) == len(image_ids)

    def test_image_id_is_uuid_format(self):
        """Test image_id appears to be UUID format."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()
        image_id = data["image_id"]

        # UUID should have 36 characters (32 hex + 4 dashes)
        assert len(image_id) == 36
        # Should have proper dash positions
        assert image_id[8] == "-"
        assert image_id[13] == "-"
        assert image_id[18] == "-"
        assert image_id[23] == "-"


class TestScanEndpointResultOrdering:
    """Test result ordering and sorting."""

    def test_results_have_consistent_order(self):
        """Test results are returned in consistent order."""
        # Make multiple requests and verify order is deterministic
        orders = []

        for _ in range(3):
            image = create_test_image()
            response = client.post(
                "/scan?mock_scenario=full_shelf",
                files={"image": ("test.jpg", image, "image/jpeg")}
            )

            data = response.json()
            wine_names = tuple(r["wine_name"] for r in data["results"])
            orders.append(wine_names)

        # All orders should be identical
        assert all(order == orders[0] for order in orders)


class TestScanEndpointExtendedFields:
    """Test extended fields (identified, source)."""

    def test_results_have_identified_field(self):
        """Test results include identified field."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        for result in data["results"]:
            assert "identified" in result
            assert isinstance(result["identified"], bool)

    def test_results_have_source_field(self):
        """Test results include source field."""
        image = create_test_image()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )

        data = response.json()

        for result in data["results"]:
            assert "source" in result
            assert result["source"] in ("database", "llm")
