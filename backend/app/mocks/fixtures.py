"""
Mock response fixtures for development and testing.

Scenarios:
- full_shelf: 8 bottles with varied confidence levels
- partial_detection: 3 detected, 5 in fallback list
- low_confidence: All bottles below 0.65 confidence
- empty_results: No detection, fallback list only
"""

from ..models import ScanResponse, WineResult, FallbackWine, BoundingBox


MOCK_SCENARIOS = {
    "full_shelf": {
        "results": [
            WineResult(
                wine_name="Caymus Cabernet Sauvignon",
                rating=4.5,
                confidence=0.94,
                bbox=BoundingBox(x=0.05, y=0.15, width=0.08, height=0.35),
            ),
            WineResult(
                wine_name="Opus One",
                rating=4.8,
                confidence=0.91,
                bbox=BoundingBox(x=0.15, y=0.12, width=0.09, height=0.38),
            ),
            WineResult(
                wine_name="Silver Oak Alexander Valley",
                rating=4.4,
                confidence=0.88,
                bbox=BoundingBox(x=0.26, y=0.14, width=0.08, height=0.36),
            ),
            WineResult(
                wine_name="Jordan Cabernet Sauvignon",
                rating=4.3,
                confidence=0.85,
                bbox=BoundingBox(x=0.36, y=0.13, width=0.08, height=0.37),
            ),
            WineResult(
                wine_name="Kendall-Jackson Vintner's Reserve",
                rating=3.8,
                confidence=0.79,
                bbox=BoundingBox(x=0.46, y=0.16, width=0.08, height=0.34),
            ),
            WineResult(
                wine_name="La Crema Sonoma Coast Pinot Noir",
                rating=4.1,
                confidence=0.72,
                bbox=BoundingBox(x=0.56, y=0.14, width=0.08, height=0.36),
            ),
            WineResult(
                wine_name="Meiomi Pinot Noir",
                rating=3.9,
                confidence=0.68,
                bbox=BoundingBox(x=0.66, y=0.15, width=0.08, height=0.35),
            ),
            WineResult(
                wine_name="Bread & Butter Chardonnay",
                rating=3.7,
                confidence=0.52,
                bbox=BoundingBox(x=0.76, y=0.17, width=0.08, height=0.33),
            ),
        ],
        "fallback_list": []
    },

    "partial_detection": {
        "results": [
            WineResult(
                wine_name="Caymus Cabernet Sauvignon",
                rating=4.5,
                confidence=0.92,
                bbox=BoundingBox(x=0.10, y=0.15, width=0.10, height=0.35)
            ),
            WineResult(
                wine_name="Opus One",
                rating=4.8,
                confidence=0.89,
                bbox=BoundingBox(x=0.30, y=0.12, width=0.10, height=0.38)
            ),
            WineResult(
                wine_name="Silver Oak Alexander Valley",
                rating=4.4,
                confidence=0.86,
                bbox=BoundingBox(x=0.50, y=0.14, width=0.10, height=0.36)
            ),
        ],
        "fallback_list": [
            FallbackWine(wine_name="Jordan Cabernet Sauvignon", rating=4.3),
            FallbackWine(wine_name="Kendall-Jackson Vintner's Reserve", rating=3.8),
            FallbackWine(wine_name="La Crema Sonoma Coast Pinot Noir", rating=4.1),
            FallbackWine(wine_name="Meiomi Pinot Noir", rating=3.9),
            FallbackWine(wine_name="Bread & Butter Chardonnay", rating=3.7),
        ]
    },

    "low_confidence": {
        "results": [
            WineResult(
                wine_name="Unknown Red Wine",
                rating=3.5,
                confidence=0.58,
                bbox=BoundingBox(x=0.10, y=0.15, width=0.12, height=0.35)
            ),
            WineResult(
                wine_name="Unknown White Wine",
                rating=3.3,
                confidence=0.52,
                bbox=BoundingBox(x=0.30, y=0.12, width=0.12, height=0.38)
            ),
            WineResult(
                wine_name="Unknown Rose",
                rating=3.6,
                confidence=0.48,
                bbox=BoundingBox(x=0.50, y=0.14, width=0.12, height=0.36)
            ),
            WineResult(
                wine_name="Unknown Sparkling",
                rating=3.4,
                confidence=0.41,
                bbox=BoundingBox(x=0.70, y=0.13, width=0.12, height=0.37)
            ),
        ],
        "fallback_list": [
            FallbackWine(wine_name="Possible Cabernet", rating=3.8),
            FallbackWine(wine_name="Possible Chardonnay", rating=3.5),
        ]
    },

    "empty_results": {
        "results": [],
        "fallback_list": [
            FallbackWine(wine_name="Caymus Cabernet Sauvignon", rating=4.5),
            FallbackWine(wine_name="Opus One", rating=4.8),
            FallbackWine(wine_name="Silver Oak Alexander Valley", rating=4.4),
            FallbackWine(wine_name="Jordan Cabernet Sauvignon", rating=4.3),
            FallbackWine(wine_name="La Crema Sonoma Coast Pinot Noir", rating=4.1),
            FallbackWine(wine_name="Meiomi Pinot Noir", rating=3.9),
            FallbackWine(wine_name="Kendall-Jackson Vintner's Reserve", rating=3.8),
            FallbackWine(wine_name="Bread & Butter Chardonnay", rating=3.7),
        ]
    }
}


def get_mock_response(image_id: str, scenario: str = "full_shelf") -> ScanResponse:
    """
    Get a mock response for the given scenario.

    Args:
        image_id: Unique identifier for this scan
        scenario: One of full_shelf, partial_detection, low_confidence, empty_results

    Returns:
        ScanResponse with mock data
    """
    if scenario not in MOCK_SCENARIOS:
        scenario = "full_shelf"

    data = MOCK_SCENARIOS[scenario]

    return ScanResponse(
        image_id=image_id,
        results=data["results"],
        fallback_list=data["fallback_list"]
    )
