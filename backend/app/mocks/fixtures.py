"""
Mock response fixtures for development and testing.

Scenarios:
- full_shelf: 8 bottles with varied confidence levels
- partial_detection: 3 detected, 5 in fallback list
- low_confidence: All bottles below 0.65 confidence
- empty_results: No detection, fallback list only
"""

from ..models import ScanResponse, WineResult, FallbackWine, BoundingBox, DebugData, DebugPipelineStep, FuzzyMatchDebug, FuzzyMatchScores, LLMValidationDebug, NearMissCandidate, NormalizationTrace, LLMRawDebug


MOCK_DEBUG_STEPS = [
    DebugPipelineStep(
        raw_text="CAYMUS CABERNET SAUVIGNON NAPA VALLEY 2019",
        normalized_text="Caymus Cabernet Sauvignon Napa Valley",
        bottle_index=0,
        fuzzy_match=FuzzyMatchDebug(
            candidate="Caymus Cabernet Sauvignon",
            scores=FuzzyMatchScores(ratio=0.91, partial_ratio=0.95, token_sort_ratio=0.93, phonetic_bonus=0.05, weighted_score=0.93),
            rating=4.5
        ),
        llm_validation=None,
        final_result={"wine_name": "Caymus Cabernet Sauvignon", "confidence": 0.94, "source": "fuzzy"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="OPUS ONE MONDAVI ROTHSCHILD 2018",
        normalized_text="Opus One Mondavi Rothschild",
        bottle_index=1,
        fuzzy_match=FuzzyMatchDebug(
            candidate="Opus One",
            scores=FuzzyMatchScores(ratio=0.72, partial_ratio=0.88, token_sort_ratio=0.78, phonetic_bonus=0.0, weighted_score=0.79),
            rating=4.8
        ),
        llm_validation=LLMValidationDebug(
            is_valid_match=True,
            wine_name="Opus One",
            confidence=0.95,
            reasoning="Opus One is the correct wine. Mondavi Rothschild are the producers."
        ),
        final_result={"wine_name": "Opus One", "confidence": 0.91, "source": "llm"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="SILVER OAK ALEXANDER VALLEY CAB",
        normalized_text="Silver Oak Alexander Valley Cab",
        bottle_index=2,
        fuzzy_match=FuzzyMatchDebug(
            candidate="Silver Oak Alexander Valley",
            scores=FuzzyMatchScores(ratio=0.89, partial_ratio=0.94, token_sort_ratio=0.91, phonetic_bonus=0.03, weighted_score=0.91),
            rating=4.4
        ),
        llm_validation=None,
        final_result={"wine_name": "Silver Oak Alexander Valley", "confidence": 0.88, "source": "fuzzy"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="JORDAN CABERNET SAUVIGNON",
        normalized_text="Jordan Cabernet Sauvignon",
        bottle_index=3,
        fuzzy_match=FuzzyMatchDebug(
            candidate="Jordan Cabernet Sauvignon",
            scores=FuzzyMatchScores(ratio=0.97, partial_ratio=0.97, token_sort_ratio=0.97, phonetic_bonus=0.05, weighted_score=0.97),
            rating=4.3
        ),
        llm_validation=None,
        final_result={"wine_name": "Jordan Cabernet Sauvignon", "confidence": 0.85, "source": "fuzzy"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="KENDALL JACKSON VINTNERS RESERVE",
        normalized_text="Kendall Jackson Vintners Reserve",
        bottle_index=4,
        fuzzy_match=FuzzyMatchDebug(
            candidate="Kendall-Jackson Vintner's Reserve",
            scores=FuzzyMatchScores(ratio=0.85, partial_ratio=0.90, token_sort_ratio=0.88, phonetic_bonus=0.04, weighted_score=0.87),
            rating=3.8
        ),
        llm_validation=None,
        final_result={"wine_name": "Kendall-Jackson Vintner's Reserve", "confidence": 0.79, "source": "fuzzy"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="LA CREMA SONOMA",
        normalized_text="La Crema Sonoma",
        bottle_index=5,
        fuzzy_match=FuzzyMatchDebug(
            candidate="La Crema Sonoma Coast Pinot Noir",
            scores=FuzzyMatchScores(ratio=0.62, partial_ratio=0.78, token_sort_ratio=0.68, phonetic_bonus=0.0, weighted_score=0.68),
            rating=4.1
        ),
        llm_validation=LLMValidationDebug(
            is_valid_match=True,
            wine_name="La Crema Sonoma Coast Pinot Noir",
            confidence=0.82,
            reasoning="Partial label match. 'La Crema Sonoma' is the abbreviated form of the full wine name."
        ),
        final_result={"wine_name": "La Crema Sonoma Coast Pinot Noir", "confidence": 0.72, "source": "llm"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="MEIOMI PINOT NOIR",
        normalized_text="Meiomi Pinot Noir",
        bottle_index=6,
        fuzzy_match=FuzzyMatchDebug(
            candidate="Meiomi Pinot Noir",
            scores=FuzzyMatchScores(ratio=0.96, partial_ratio=0.96, token_sort_ratio=0.96, phonetic_bonus=0.05, weighted_score=0.96),
            rating=3.9
        ),
        llm_validation=None,
        final_result={"wine_name": "Meiomi Pinot Noir", "confidence": 0.68, "source": "fuzzy"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="BREAD BUTTER CHARD",
        normalized_text="Bread Butter Chard",
        bottle_index=7,
        fuzzy_match=FuzzyMatchDebug(
            candidate="Bread & Butter Chardonnay",
            scores=FuzzyMatchScores(ratio=0.58, partial_ratio=0.72, token_sort_ratio=0.65, phonetic_bonus=0.0, weighted_score=0.64),
            rating=3.7
        ),
        llm_validation=LLMValidationDebug(
            is_valid_match=True,
            wine_name="Bread & Butter Chardonnay",
            confidence=0.68,
            reasoning="Abbreviated label. 'Bread Butter Chard' maps to Bread & Butter Chardonnay."
        ),
        final_result={"wine_name": "Bread & Butter Chardonnay", "confidence": 0.52, "source": "llm"},
        step_failed=None,
        included_in_results=True
    ),
    DebugPipelineStep(
        raw_text="WILLAMETTE JOURNAL BOWN IN OREGON PINOT NOIR 2021 750ml",
        normalized_text="Willametter Journal Bown Pinot",
        bottle_index=7,
        fuzzy_match=FuzzyMatchDebug(
            candidate=None,
            scores=None,
            rating=None,
            near_misses=[
                NearMissCandidate(wine_name="Willamette Valley Vineyards Pinot Noir", score=0.58, rejection_reason="below_threshold"),
                NearMissCandidate(wine_name="William Hill Pinot Noir", score=0.52, rejection_reason="below_threshold"),
            ],
            fts_candidates_count=12,
            rejection_reason="below_threshold",
        ),
        llm_validation=LLMValidationDebug(
            is_valid_match=False,
            wine_name=None,
            confidence=0.0,
            reasoning="No valid wine name found"
        ),
        normalization_trace=NormalizationTrace(
            original_text="WILLAMETTE JOURNAL BOWN IN OREGON PINOT NOIR 2021 750ml",
            after_pattern_removal="WILLAMETTE JOURNAL BOWN IN OREGON PINOT NOIR",
            removed_patterns=["2021", "750ml"],
            removed_filler_words=["in", "oregon"],
            final_text="Willametter Journal Bown Pinot",
        ),
        llm_raw=LLMRawDebug(
            prompt_text="You are a wine label validator...\n0. OCR: \"WILLAMETTE JOURNAL BOWN IN OREGON PINOT NOIR 2021 750ml\" → DB: null",
            raw_response='[{"index": 0, "is_valid_match": false, "wine_name": null, "confidence": 0.0, "reasoning": "No valid wine name found"}]',
            model_used="gemini/gemini-2.0-flash",
        ),
        final_result=None,
        step_failed="llm_validation",
        included_in_results=False
    ),
    DebugPipelineStep(
        raw_text="SHELF TAG $24.99",
        normalized_text="Shelf Tag",
        bottle_index=7,
        fuzzy_match=None,
        llm_validation=None,
        final_result=None,
        step_failed="normalization_filtered",
        included_in_results=False
    ),
]

MOCK_DEBUG_DATA = DebugData(
    pipeline_steps=MOCK_DEBUG_STEPS,
    total_ocr_texts=10,
    bottles_detected=8,
    texts_matched=8,
    llm_calls_made=3
)


MOCK_SCENARIOS = {
    "full_shelf": {
        "results": [
            WineResult(
                wine_name="Caymus Cabernet Sauvignon",
                rating=4.5,
                confidence=0.94,
                bbox=BoundingBox(x=0.05, y=0.15, width=0.08, height=0.35)
            ),
            WineResult(
                wine_name="Opus One",
                rating=4.8,
                confidence=0.91,
                bbox=BoundingBox(x=0.15, y=0.12, width=0.09, height=0.38)
            ),
            WineResult(
                wine_name="Silver Oak Alexander Valley",
                rating=4.4,
                confidence=0.88,
                bbox=BoundingBox(x=0.26, y=0.14, width=0.08, height=0.36)
            ),
            WineResult(
                wine_name="Jordan Cabernet Sauvignon",
                rating=4.3,
                confidence=0.85,
                bbox=BoundingBox(x=0.36, y=0.13, width=0.08, height=0.37)
            ),
            WineResult(
                wine_name="Kendall-Jackson Vintner's Reserve",
                rating=3.8,
                confidence=0.79,
                bbox=BoundingBox(x=0.46, y=0.16, width=0.08, height=0.34)
            ),
            WineResult(
                wine_name="La Crema Sonoma Coast Pinot Noir",
                rating=4.1,
                confidence=0.72,
                bbox=BoundingBox(x=0.56, y=0.14, width=0.08, height=0.36)
            ),
            WineResult(
                wine_name="Meiomi Pinot Noir",
                rating=3.9,
                confidence=0.68,
                bbox=BoundingBox(x=0.66, y=0.15, width=0.08, height=0.35)
            ),
            WineResult(
                wine_name="Bread & Butter Chardonnay",
                rating=3.7,
                confidence=0.52,
                bbox=BoundingBox(x=0.76, y=0.17, width=0.08, height=0.33)
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
        fallback_list=data["fallback_list"],
        debug=MOCK_DEBUG_DATA if scenario == "full_shelf" else None
    )
