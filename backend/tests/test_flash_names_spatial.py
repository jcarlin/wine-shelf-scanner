"""
Tests for flash_names pipeline spatial matching.

Tests the spatial nearest-neighbor merge strategy that matches Gemini-identified
wines (with approximate x,y positions) to Vision API-detected bottles (with bboxes).
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.flash_names_pipeline import FlashNamesPipeline
from app.services.ocr_processor import BottleText
from app.services.recognition_pipeline import RecognizedWine
from app.services.vision import BoundingBox, DetectedObject, TextBlock
from app.services.wine_matcher import WineMatch
from app.models.enums import RatingSource, WineSource


def _make_bottle_text(name: str, bbox: BoundingBox, ocr_text: str = "") -> BottleText:
    """Create a BottleText with a DetectedObject and OCR text."""
    obj = DetectedObject(name="Bottle", confidence=0.95, bbox=bbox)
    return BottleText(
        bottle=obj,
        text_fragments=[ocr_text] if ocr_text else [],
        combined_text=ocr_text,
        normalized_name=ocr_text.lower().strip() if ocr_text else "",
    )


def _make_pipeline() -> FlashNamesPipeline:
    """Create a FlashNamesPipeline with a mocked WineMatcher (no DB hits)."""
    mock_matcher = MagicMock()
    mock_matcher.match.return_value = None
    return FlashNamesPipeline(wine_matcher=mock_matcher, use_llm_cache=False)


class TestSpatialMerge:
    """Test spatial nearest-neighbor matching."""

    def test_basic_3_bottles_correct_assignment(self):
        """3 wines at known positions match to the correct 3 bottles."""
        pipeline = _make_pipeline()

        # 3 bottles spread horizontally
        bottles = [
            _make_bottle_text("b0", BoundingBox(0.05, 0.30, 0.10, 0.40), "CAYMUS"),
            _make_bottle_text("b1", BoundingBox(0.35, 0.30, 0.10, 0.40), "OPUS ONE"),
            _make_bottle_text("b2", BoundingBox(0.65, 0.30, 0.10, 0.40), "SILVER OAK"),
        ]
        # Bottle centers: (0.10, 0.50), (0.40, 0.50), (0.70, 0.50)

        llm_wines = [
            {'name': 'Caymus Cabernet', 'rating': None, 'x': 0.11, 'y': 0.48},
            {'name': 'Opus One 2019', 'rating': None, 'x': 0.39, 'y': 0.51},
            {'name': 'Silver Oak Alexander Valley', 'rating': None, 'x': 0.71, 'y': 0.49},
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 3
        assert len(fallback) == 0

        # Verify correct assignment by checking which bottle each wine got
        wine_to_bottle = {r.wine_name: r.bottle_text for r in recognized}
        assert wine_to_bottle['Caymus Cabernet'].combined_text == "CAYMUS"
        assert wine_to_bottle['Opus One 2019'].combined_text == "OPUS ONE"
        assert wine_to_bottle['Silver Oak Alexander Valley'].combined_text == "SILVER OAK"

    def test_multi_row_shelf(self):
        """Wines on 2 rows are matched correctly using y-separation."""
        pipeline = _make_pipeline()

        # Top row
        bottles = [
            _make_bottle_text("top-left", BoundingBox(0.10, 0.10, 0.10, 0.30), "TOP LEFT WINE"),
            _make_bottle_text("top-right", BoundingBox(0.50, 0.10, 0.10, 0.30), "TOP RIGHT WINE"),
            # Bottom row
            _make_bottle_text("bot-left", BoundingBox(0.10, 0.55, 0.10, 0.30), "BOT LEFT WINE"),
            _make_bottle_text("bot-right", BoundingBox(0.50, 0.55, 0.10, 0.30), "BOT RIGHT WINE"),
        ]
        # Centers: (0.15, 0.25), (0.55, 0.25), (0.15, 0.70), (0.55, 0.70)

        llm_wines = [
            {'name': 'Top Left', 'rating': None, 'x': 0.16, 'y': 0.24},
            {'name': 'Top Right', 'rating': None, 'x': 0.54, 'y': 0.26},
            {'name': 'Bottom Left', 'rating': None, 'x': 0.14, 'y': 0.71},
            {'name': 'Bottom Right', 'rating': None, 'x': 0.56, 'y': 0.69},
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 4
        assert len(fallback) == 0

        wine_to_bottle = {r.wine_name: r.bottle_text for r in recognized}
        assert wine_to_bottle['Top Left'].combined_text == "TOP LEFT WINE"
        assert wine_to_bottle['Top Right'].combined_text == "TOP RIGHT WINE"
        assert wine_to_bottle['Bottom Left'].combined_text == "BOT LEFT WINE"
        assert wine_to_bottle['Bottom Right'].combined_text == "BOT RIGHT WINE"

    def test_max_distance_threshold_uses_synthetic_bbox(self):
        """Wine beyond MAX_SPATIAL_DISTANCE gets synthetic bbox (not fallback)."""
        pipeline = _make_pipeline()

        bottles = [
            _make_bottle_text("b0", BoundingBox(0.05, 0.30, 0.10, 0.40), "SOME WINE"),
        ]
        # Center: (0.10, 0.50)

        llm_wines = [
            {'name': 'Close Wine', 'rating': None, 'x': 0.12, 'y': 0.48},  # dist ~0.03
            {'name': 'Far Wine', 'rating': None, 'x': 0.80, 'y': 0.80},    # dist ~0.75
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        # Close Wine matches b0 spatially, Far Wine gets synthetic bbox
        assert len(recognized) == 2
        assert len(fallback) == 0
        close = next(r for r in recognized if r.wine_name == 'Close Wine')
        far = next(r for r in recognized if r.wine_name == 'Far Wine')
        assert close.bottle_text.combined_text == "SOME WINE"  # matched real bottle
        assert far.bottle_text.combined_text == ""  # synthetic bbox has no OCR
        assert far.confidence <= 0.70  # capped

    def test_greedy_conflict_resolution(self):
        """When 2 wines are closest to the same bottle, the closer one wins."""
        pipeline = _make_pipeline()

        bottles = [
            _make_bottle_text("b0", BoundingBox(0.20, 0.30, 0.10, 0.40), "TARGET"),
            _make_bottle_text("b1", BoundingBox(0.45, 0.30, 0.10, 0.40), "OTHER"),
        ]
        # Centers: (0.25, 0.50), (0.50, 0.50)

        llm_wines = [
            {'name': 'Wine A', 'rating': None, 'x': 0.24, 'y': 0.49},  # very close to b0
            {'name': 'Wine B', 'rating': None, 'x': 0.30, 'y': 0.50},  # also close to b0, but further; within 0.20 of b1
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        # Wine A should get b0 (closer), Wine B should get b1 (next best)
        assert len(recognized) == 2
        wine_to_bottle = {r.wine_name: r.bottle_text for r in recognized}
        assert wine_to_bottle['Wine A'].combined_text == "TARGET"
        assert wine_to_bottle['Wine B'].combined_text == "OTHER"

    def test_wines_without_positions_go_to_fallback(self):
        """LLM wines missing x,y positions are placed in fallback."""
        pipeline = _make_pipeline()

        bottles = [
            _make_bottle_text("b0", BoundingBox(0.10, 0.30, 0.10, 0.40), "CAYMUS"),
        ]

        llm_wines = [
            {'name': 'Wine With Position', 'rating': None, 'x': 0.15, 'y': 0.50},
            {'name': 'Wine Without Position', 'rating': None, 'x': None, 'y': None},
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 1
        assert recognized[0].wine_name == 'Wine With Position'
        assert len(fallback) == 1
        assert fallback[0]['wine_name'] == 'Wine Without Position'

    def test_unmatched_llm_wine_with_position_gets_synthetic_bbox(self):
        """LLM wine with position but no Vision match gets synthetic bbox in recognized (not fallback)."""
        pipeline = _make_pipeline()

        # Only one Vision bottle at left side
        bottles = [
            _make_bottle_text("b0", BoundingBox(0.05, 0.30, 0.10, 0.40), "CAYMUS"),
        ]

        llm_wines = [
            {'name': 'Caymus Cabernet', 'rating': None, 'x': 0.10, 'y': 0.50},  # matches b0
            {'name': 'Opus One 2019', 'rating': None, 'x': 0.75, 'y': 0.50},    # no Vision bottle here
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 2
        assert len(fallback) == 0

        # Opus One should have a synthetic bbox centered at (0.75, 0.50)
        opus = next(r for r in recognized if r.wine_name == 'Opus One 2019')
        bbox = opus.bottle_text.bottle.bbox
        assert abs(bbox.x - (0.75 - 0.04)) < 0.001  # x = center - width/2
        assert abs(bbox.y - (0.50 - 0.125)) < 0.001  # y = center - height/2
        assert abs(bbox.width - 0.08) < 0.001
        assert abs(bbox.height - 0.25) < 0.001

    def test_unmatched_llm_wine_without_position_goes_to_fallback(self):
        """LLM wine without position and no Vision match still goes to fallback."""
        pipeline = _make_pipeline()

        bottles = [
            _make_bottle_text("b0", BoundingBox(0.05, 0.30, 0.10, 0.40), "CAYMUS"),
        ]

        llm_wines = [
            {'name': 'Caymus Cabernet', 'rating': None, 'x': 0.10, 'y': 0.50},  # matches b0
            {'name': 'Mystery Wine', 'rating': None, 'x': None, 'y': None},       # no position
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 1
        assert recognized[0].wine_name == 'Caymus Cabernet'
        assert len(fallback) == 1
        assert fallback[0]['wine_name'] == 'Mystery Wine'

    def test_synthetic_bbox_confidence_capped_at_070(self):
        """Synthetic-bbox wines have confidence capped at 0.70."""
        pipeline = _make_pipeline()

        bottles = []  # No Vision bottles at all

        llm_wines = [
            {'name': 'Opus One 2019', 'rating': None, 'x': 0.50, 'y': 0.50},
        ]
        llm_ratings = {'Opus One 2019': 4.5}
        db_results = {'Opus One 2019': None}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 1
        assert recognized[0].confidence <= 0.70

    def test_synthetic_bbox_dimensions_correct(self):
        """Synthetic bbox is 0.08 x 0.25, centered on Gemini position, clamped to image bounds."""
        pipeline = _make_pipeline()

        bottles = []

        # Wine near the top-left edge — bbox should be clamped to 0
        llm_wines = [
            {'name': 'Edge Wine', 'rating': None, 'x': 0.02, 'y': 0.05},
        ]
        llm_ratings = {'Edge Wine': 3.5}
        db_results = {'Edge Wine': None}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 1
        bbox = recognized[0].bottle_text.bottle.bbox
        # x = max(0.0, 0.02 - 0.04) = 0.0
        assert bbox.x == 0.0
        # y = max(0.0, 0.05 - 0.125) = 0.0
        assert bbox.y == 0.0
        assert abs(bbox.width - 0.08) < 0.001
        assert abs(bbox.height - 0.25) < 0.001

    def test_synthetic_bbox_calibrated_from_matched_pairs(self):
        """Synthetic bbox position is corrected using offset from matched pairs."""
        pipeline = _make_pipeline()

        # Vision bottle center at (0.15, 0.50)
        bottles = [
            _make_bottle_text("b0", BoundingBox(0.10, 0.30, 0.10, 0.40), "CAYMUS"),
        ]

        # Gemini says Caymus is at (0.18, 0.52) — offset of +0.03 x, +0.02 y
        # Gemini says Opus One is at (0.75, 0.50)
        llm_wines = [
            {'name': 'Caymus Cabernet', 'rating': None, 'x': 0.18, 'y': 0.52},
            {'name': 'Opus One 2019', 'rating': None, 'x': 0.75, 'y': 0.50},
        ]
        llm_ratings = {w['name']: 3.5 for w in llm_wines}
        db_results = {w['name']: None for w in llm_wines}

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 2
        opus = next(r for r in recognized if r.wine_name == 'Opus One 2019')
        bbox = opus.bottle_text.bottle.bbox

        # Calibration: Vision center (0.15, 0.50) - Gemini pos (0.18, 0.52) = (-0.03, -0.02)
        # Corrected Opus position: (0.75 + (-0.03), 0.50 + (-0.02)) = (0.72, 0.48)
        # bbox.x = 0.72 - 0.04 = 0.68
        expected_center_x = 0.75 - 0.03  # = 0.72
        expected_center_y = 0.50 - 0.02  # = 0.48
        actual_center_x = bbox.x + bbox.width / 2
        actual_center_y = bbox.y + bbox.height / 2
        assert abs(actual_center_x - expected_center_x) < 0.01
        assert abs(actual_center_y - expected_center_y) < 0.01

    def test_db_match_uses_canonical_name_and_rating(self):
        """When DB has a match, recognized wine uses canonical name and DB rating."""
        pipeline = _make_pipeline()

        bottles = [
            _make_bottle_text("b0", BoundingBox(0.10, 0.30, 0.10, 0.40), "CAYMUS"),
        ]

        llm_wines = [
            {'name': 'Caymus Cab Sauv', 'rating': None, 'x': 0.15, 'y': 0.50},
        ]
        llm_ratings = {'Caymus Cab Sauv': 3.5}
        db_results = {
            'Caymus Cab Sauv': WineMatch(
                canonical_name='Caymus Cabernet Sauvignon Napa Valley',
                rating=4.6,
                confidence=0.88,
                wine_id=42,
            ),
        }

        recognized, fallback = pipeline._spatial_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 1
        assert recognized[0].wine_name == 'Caymus Cabernet Sauvignon Napa Valley'
        assert recognized[0].rating == 4.6
        assert recognized[0].source == WineSource.DATABASE
        assert recognized[0].rating_source == RatingSource.DATABASE
        assert recognized[0].wine_id == 42


class TestOCRTextMergeFallback:
    """Test OCR text matching fallback (when Gemini omits positions)."""

    def test_plain_string_wines_trigger_ocr_fallback(self):
        """When all LLM wines lack positions, _merge_with_vision falls back to OCR text matching."""
        pipeline = _make_pipeline()

        bottles = [
            _make_bottle_text("b0", BoundingBox(0.05, 0.30, 0.10, 0.40), "caymus cabernet sauvignon"),
        ]

        llm_wines = [
            {'name': 'Caymus Cabernet Sauvignon', 'rating': None, 'x': None, 'y': None},
        ]
        llm_ratings = {'Caymus Cabernet Sauvignon': 3.5}
        db_results = {'Caymus Cabernet Sauvignon': None}

        recognized, fallback = pipeline._ocr_text_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 1
        assert recognized[0].wine_name == 'Caymus Cabernet Sauvignon'

    def test_ocr_threshold_raised_to_055(self):
        """OCR text match threshold is 0.55 (raised from 0.40) — low matches go to fallback."""
        pipeline = _make_pipeline()

        bottles = [
            _make_bottle_text("b0", BoundingBox(0.05, 0.30, 0.10, 0.40), "completely unrelated text xyz"),
        ]

        llm_wines = [
            {'name': 'Caymus Cabernet Sauvignon', 'rating': None, 'x': None, 'y': None},
        ]
        llm_ratings = {'Caymus Cabernet Sauvignon': 3.5}
        db_results = {'Caymus Cabernet Sauvignon': None}

        recognized, fallback = pipeline._ocr_text_merge(
            llm_wines, llm_ratings, db_results, bottles
        )

        assert len(recognized) == 0
        assert len(fallback) == 1


class TestMergeWithVisionRouting:
    """Test that _merge_with_vision routes to spatial vs OCR correctly."""

    def test_routes_to_spatial_when_positions_available(self):
        """When any LLM wine has x,y, uses spatial merge."""
        pipeline = _make_pipeline()

        from app.services.vision import VisionResult
        vision_result = VisionResult(
            objects=[DetectedObject("Bottle", 0.95, BoundingBox(0.10, 0.30, 0.10, 0.40))],
            text_blocks=[TextBlock("CAYMUS", BoundingBox(0.11, 0.35, 0.08, 0.03), 0.9)],
            raw_text="CAYMUS",
            image_width=1000,
            image_height=1000,
        )

        llm_wines = [
            {'name': 'Caymus', 'rating': None, 'x': 0.15, 'y': 0.50},
        ]
        llm_ratings = {'Caymus': 3.5}
        db_results = {'Caymus': None}

        with patch.object(pipeline, '_spatial_merge', wraps=pipeline._spatial_merge) as mock_spatial:
            pipeline._merge_with_vision(llm_wines, llm_ratings, db_results, vision_result, b"img")
            mock_spatial.assert_called_once()

    def test_routes_to_ocr_when_no_positions(self):
        """When no LLM wine has x,y, falls back to OCR text matching."""
        pipeline = _make_pipeline()

        from app.services.vision import VisionResult
        vision_result = VisionResult(
            objects=[DetectedObject("Bottle", 0.95, BoundingBox(0.10, 0.30, 0.10, 0.40))],
            text_blocks=[TextBlock("CAYMUS", BoundingBox(0.11, 0.35, 0.08, 0.03), 0.9)],
            raw_text="CAYMUS",
            image_width=1000,
            image_height=1000,
        )

        llm_wines = [
            {'name': 'Caymus', 'rating': None, 'x': None, 'y': None},
        ]
        llm_ratings = {'Caymus': 3.5}
        db_results = {'Caymus': None}

        with patch.object(pipeline, '_ocr_text_merge', wraps=pipeline._ocr_text_merge) as mock_ocr:
            pipeline._merge_with_vision(llm_wines, llm_ratings, db_results, vision_result, b"img")
            mock_ocr.assert_called_once()


class TestGeminiResponseParsing:
    """Test that _run_gemini_names correctly parses x,y positions.

    Since pytest-asyncio is not installed, we test the parsing logic by
    simulating what _run_gemini_names does with the parsed JSON.
    """

    @staticmethod
    def _parse_gemini_response(json_text: str) -> list[dict]:
        """Replicate the parsing logic from _run_gemini_names."""
        import json as _json
        parsed = _json.loads(json_text)
        if not isinstance(parsed, list):
            return []
        seen = set()
        wines = []
        for item in parsed:
            if isinstance(item, str):
                name = item
                x, y = None, None
            elif isinstance(item, dict):
                name = item.get('name')
                x = item.get('x')
                y = item.get('y')
            else:
                continue
            if not name:
                continue
            if x is not None and y is not None:
                try:
                    x = max(0.0, min(1.0, float(x)))
                    y = max(0.0, min(1.0, float(y)))
                except (ValueError, TypeError):
                    x, y = None, None
            else:
                x, y = None, None
            key = name.lower().strip()
            if key not in seen:
                seen.add(key)
                wines.append({'name': name, 'rating': None, 'x': x, 'y': y})
        return wines

    def test_parses_dict_with_positions(self):
        """Gemini response with name + x + y parsed correctly."""
        wines = self._parse_gemini_response(
            '[{"name": "Caymus Cabernet", "x": 0.15, "y": 0.45},'
            ' {"name": "Opus One", "x": 0.55, "y": 0.44}]'
        )

        assert len(wines) == 2
        assert wines[0] == {'name': 'Caymus Cabernet', 'rating': None, 'x': 0.15, 'y': 0.45}
        assert wines[1] == {'name': 'Opus One', 'rating': None, 'x': 0.55, 'y': 0.44}

    def test_parses_plain_strings_backward_compat(self):
        """Plain string array (old Gemini format) still works, x/y are None."""
        wines = self._parse_gemini_response('["Caymus Cabernet", "Opus One"]')

        assert len(wines) == 2
        assert wines[0] == {'name': 'Caymus Cabernet', 'rating': None, 'x': None, 'y': None}
        assert wines[1] == {'name': 'Opus One', 'rating': None, 'x': None, 'y': None}

    def test_clamps_out_of_range_positions(self):
        """x,y values outside 0-1 are clamped."""
        wines = self._parse_gemini_response('[{"name": "Wine", "x": -0.1, "y": 1.5}]')

        assert len(wines) == 1
        assert wines[0]['x'] == 0.0
        assert wines[0]['y'] == 1.0


class TestCarryForwardPhase1Ratings:
    """Test that phase 1 DB ratings are preserved when phase 2 replaces them with LLM estimates."""

    @staticmethod
    def _make_recognized(
        wine_name: str,
        rating: float,
        rating_source: RatingSource,
        source: WineSource,
        bbox: BoundingBox,
        wine_id: int = None,
        wine_type: str = None,
        varietal: str = None,
        region: str = None,
        brand: str = None,
        blurb: str = None,
    ) -> RecognizedWine:
        bt = _make_bottle_text(wine_name, bbox, wine_name.upper())
        return RecognizedWine(
            wine_name=wine_name,
            rating=rating,
            confidence=0.80,
            source=source,
            identified=True,
            bottle_text=bt,
            rating_source=rating_source,
            wine_id=wine_id,
            wine_type=wine_type,
            varietal=varietal,
            region=region,
            brand=brand,
            blurb=blurb,
        )

    def test_phase2_llm_rating_replaced_by_phase1_db_rating(self):
        """Phase 2 LLM-estimated rating is replaced by phase 1 DB rating for the same bottle."""
        bbox = BoundingBox(0.10, 0.30, 0.10, 0.40)

        phase1 = [self._make_recognized(
            "Caymus Cabernet Sauvignon 2020", 4.5, RatingSource.DATABASE, WineSource.DATABASE,
            bbox, wine_id=42,
        )]
        phase2 = [self._make_recognized(
            "Caymus Cabernet Sauvignon Napa Valley", 4.2, RatingSource.LLM_ESTIMATED, WineSource.LLM,
            bbox,
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings(phase1, phase2)

        assert len(result) == 1
        assert result[0].rating == 4.5
        assert result[0].rating_source == RatingSource.DATABASE
        assert result[0].source == WineSource.DATABASE
        assert result[0].wine_name == "Caymus Cabernet Sauvignon 2020"
        assert result[0].wine_id == 42

    def test_phase2_db_rating_not_overridden(self):
        """Phase 2 wine with its own DB rating is NOT overridden by phase 1."""
        bbox = BoundingBox(0.10, 0.30, 0.10, 0.40)

        phase1 = [self._make_recognized(
            "Caymus Cab Sauv 2020", 4.5, RatingSource.DATABASE, WineSource.DATABASE,
            bbox, wine_id=42,
        )]
        phase2 = [self._make_recognized(
            "Caymus Cabernet Sauvignon Napa Valley 2020", 4.6, RatingSource.DATABASE, WineSource.DATABASE,
            bbox, wine_id=99,
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings(phase1, phase2)

        assert len(result) == 1
        # Phase 2's own DB match is preserved
        assert result[0].rating == 4.6
        assert result[0].wine_id == 99
        assert result[0].wine_name == "Caymus Cabernet Sauvignon Napa Valley 2020"

    def test_phase2_metadata_preserved_when_rating_carried(self):
        """Phase 2 metadata (wine_type, varietal, region, brand) is kept even when rating is from phase 1."""
        bbox = BoundingBox(0.10, 0.30, 0.10, 0.40)

        phase1 = [self._make_recognized(
            "Caymus Cabernet Sauvignon", 4.5, RatingSource.DATABASE, WineSource.DATABASE,
            bbox, wine_id=42,
        )]
        phase2 = [self._make_recognized(
            "Caymus Cab Sauv Napa", 4.2, RatingSource.LLM_ESTIMATED, WineSource.LLM,
            bbox, wine_type="Red", varietal="Cabernet Sauvignon", region="Napa Valley", brand="Caymus Vineyards",
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings(phase1, phase2)

        assert len(result) == 1
        # Rating carried from phase 1
        assert result[0].rating == 4.5
        assert result[0].rating_source == RatingSource.DATABASE
        # Metadata kept from phase 2
        assert result[0].wine_type == "Red"
        assert result[0].varietal == "Cabernet Sauvignon"
        assert result[0].region == "Napa Valley"
        assert result[0].brand == "Caymus Vineyards"

    def test_phase1_db_wine_missing_from_phase2_remerged(self):
        """Phase 1 DB-matched wine absent from phase 2 is re-merged into results."""
        bbox1 = BoundingBox(0.10, 0.30, 0.10, 0.40)
        bbox2 = BoundingBox(0.40, 0.30, 0.10, 0.40)

        phase1 = [
            self._make_recognized(
                "Caymus Cabernet", 4.5, RatingSource.DATABASE, WineSource.DATABASE,
                bbox1, wine_id=42,
            ),
            self._make_recognized(
                "Opus One 2019", 4.8, RatingSource.DATABASE, WineSource.DATABASE,
                bbox2, wine_id=99,
            ),
        ]
        # Phase 2 only found Caymus (different bbox2 bottle was missed by Gemini)
        phase2 = [self._make_recognized(
            "Caymus Cabernet Sauvignon", 4.2, RatingSource.LLM_ESTIMATED, WineSource.LLM,
            bbox1,
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings(phase1, phase2)

        assert len(result) == 2
        names = {rw.wine_name for rw in result}
        assert "Caymus Cabernet" in names  # carried forward rating + name
        assert "Opus One 2019" in names    # re-merged

    def test_phase1_llm_cache_wine_not_remerged(self):
        """Phase 1 LLM-cache wine missing from phase 2 is NOT re-merged (only DB wines)."""
        bbox1 = BoundingBox(0.10, 0.30, 0.10, 0.40)
        bbox2 = BoundingBox(0.40, 0.30, 0.10, 0.40)

        phase1 = [
            self._make_recognized(
                "Caymus Cabernet", 4.5, RatingSource.DATABASE, WineSource.DATABASE,
                bbox1, wine_id=42,
            ),
            self._make_recognized(
                "Some Obscure Wine", 3.8, RatingSource.LLM_ESTIMATED, WineSource.LLM,
                bbox2,
            ),
        ]
        # Phase 2 only found Caymus
        phase2 = [self._make_recognized(
            "Caymus Cabernet Sauvignon", 4.2, RatingSource.LLM_ESTIMATED, WineSource.LLM,
            bbox1,
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings(phase1, phase2)

        assert len(result) == 1
        assert result[0].wine_name == "Caymus Cabernet"  # carried forward
        # The LLM-cache wine was NOT re-merged
        names = {rw.wine_name for rw in result}
        assert "Some Obscure Wine" not in names

    def test_empty_phase1_is_noop(self):
        """Empty phase 1 list returns phase 2 unchanged."""
        bbox = BoundingBox(0.10, 0.30, 0.10, 0.40)

        phase2 = [self._make_recognized(
            "Caymus Cabernet", 4.2, RatingSource.LLM_ESTIMATED, WineSource.LLM,
            bbox,
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings([], phase2)

        assert len(result) == 1
        assert result[0].rating == 4.2
        assert result[0].rating_source == RatingSource.LLM_ESTIMATED

    def test_metadata_backfilled_from_phase1_when_phase2_lacks_it(self):
        """Phase 2 missing metadata fields are backfilled from phase 1."""
        bbox = BoundingBox(0.10, 0.30, 0.10, 0.40)

        phase1 = [self._make_recognized(
            "Caymus Cabernet Sauvignon", 4.5, RatingSource.DATABASE, WineSource.DATABASE,
            bbox, wine_id=42, wine_type="Red", region="Napa Valley", brand="Caymus",
        )]
        # Phase 2 has varietal but lacks other metadata
        phase2 = [self._make_recognized(
            "Caymus Cab Sauv", 4.2, RatingSource.LLM_ESTIMATED, WineSource.LLM,
            bbox, varietal="Cabernet Sauvignon",
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings(phase1, phase2)

        assert len(result) == 1
        # Backfilled from phase 1
        assert result[0].wine_type == "Red"
        assert result[0].region == "Napa Valley"
        assert result[0].brand == "Caymus"
        # Kept from phase 2
        assert result[0].varietal == "Cabernet Sauvignon"

    def test_duplicate_name_not_remerged(self):
        """Phase 1 wine with same name as phase 2 wine is not re-merged (avoids duplicates)."""
        bbox1 = BoundingBox(0.10, 0.30, 0.10, 0.40)
        bbox2 = BoundingBox(0.40, 0.30, 0.10, 0.40)

        phase1 = [self._make_recognized(
            "Caymus Cabernet", 4.5, RatingSource.DATABASE, WineSource.DATABASE,
            bbox1, wine_id=42,
        )]
        # Phase 2 has the same wine name but from a different bbox
        phase2 = [self._make_recognized(
            "Caymus Cabernet", 4.6, RatingSource.DATABASE, WineSource.DATABASE,
            bbox2, wine_id=42,
        )]

        result = FlashNamesPipeline._carry_forward_phase1_ratings(phase1, phase2)

        # bbox1 is not covered by phase 2, but the name already exists — don't re-merge
        assert len(result) == 1
        assert result[0].wine_name == "Caymus Cabernet"
