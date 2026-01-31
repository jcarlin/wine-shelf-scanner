"""
Google Cloud Vision API client for wine bottle detection and OCR.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class BoundingBox:
    """Normalized bounding box (0-1 range)."""
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)


@dataclass
class DetectedObject:
    """Object detected by Vision API."""
    name: str
    confidence: float
    bbox: BoundingBox


@dataclass
class TextBlock:
    """Text block detected by OCR."""
    text: str
    bbox: BoundingBox
    confidence: float


@dataclass
class VisionResult:
    """Combined result from Vision API."""
    objects: list[DetectedObject]
    text_blocks: list[TextBlock]
    raw_text: str
    image_width: int = 0   # Image width in pixels (0 if unknown)
    image_height: int = 0  # Image height in pixels (0 if unknown)


class VisionServiceProtocol(Protocol):
    """Protocol for vision services (allows mocking)."""
    def analyze(self, image_bytes: bytes) -> VisionResult: ...


class VisionService:
    """Google Cloud Vision API client."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy load Vision client."""
        if self._client is None:
            from google.cloud import vision
            self._client = vision.ImageAnnotatorClient()
        return self._client

    def analyze(self, image_bytes: bytes) -> VisionResult:
        """
        Analyze image using Vision API.

        Performs:
        - OBJECT_LOCALIZATION: Detect bottles
        - TEXT_DETECTION: OCR for labels

        Args:
            image_bytes: Raw image bytes (JPEG or PNG)

        Returns:
            VisionResult with detected objects and text
        """
        from google.cloud import vision

        client = self._get_client()
        image = vision.Image(content=image_bytes)

        # Request both features in single call
        features = [
            vision.Feature(type_=vision.Feature.Type.OBJECT_LOCALIZATION),
            vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
        ]

        response = client.annotate_image({
            'image': image,
            'features': features
        })

        # Parse objects (filter for bottles/wine)
        objects = self._parse_objects(response.localized_object_annotations)

        # Extract image dimensions from the first text annotation bounding poly
        # (represents the full image bounds in pixel coordinates)
        image_width, image_height = self._extract_image_dimensions(
            response.text_annotations, image_bytes
        )

        # Parse text blocks with image dimensions for normalization
        text_blocks = self._parse_text(response.text_annotations, image_width, image_height)

        # Full raw text (first annotation is the complete text)
        raw_text = ""
        if response.text_annotations:
            raw_text = response.text_annotations[0].description

        return VisionResult(
            objects=objects,
            text_blocks=text_blocks,
            raw_text=raw_text,
            image_width=image_width,
            image_height=image_height
        )

    def _extract_image_dimensions(
        self, text_annotations, image_bytes: bytes
    ) -> tuple[int, int]:
        """
        Extract image dimensions from annotations or image bytes.

        The first text annotation from Vision API contains the full image
        bounds in pixel coordinates. Falls back to decoding image header.
        """
        # Try to get dimensions from first text annotation's bounding poly
        if text_annotations and len(text_annotations) > 0:
            first_ann = text_annotations[0]
            if first_ann.bounding_poly and first_ann.bounding_poly.vertices:
                vertices = first_ann.bounding_poly.vertices
                if len(vertices) >= 4:
                    x_coords = [v.x for v in vertices if v.x > 0]
                    y_coords = [v.y for v in vertices if v.y > 0]
                    if x_coords and y_coords:
                        return (max(x_coords), max(y_coords))

        # Fallback: decode image to get dimensions
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            return img.size
        except Exception:
            # Last resort: use reasonable defaults
            return (1000, 1000)

    def _parse_objects(self, annotations) -> list[DetectedObject]:
        """Parse object localization results, filtering for bottles."""
        objects = []
        bottle_keywords = {'bottle', 'wine', 'wine bottle', 'drink'}

        for obj in annotations:
            name_lower = obj.name.lower()
            if any(kw in name_lower for kw in bottle_keywords):
                # Convert vertices to normalized bbox
                vertices = obj.bounding_poly.normalized_vertices
                if len(vertices) >= 4:
                    x_coords = [v.x for v in vertices]
                    y_coords = [v.y for v in vertices]

                    bbox = BoundingBox(
                        x=min(x_coords),
                        y=min(y_coords),
                        width=max(x_coords) - min(x_coords),
                        height=max(y_coords) - min(y_coords)
                    )

                    objects.append(DetectedObject(
                        name=obj.name,
                        confidence=obj.score,
                        bbox=bbox
                    ))

        return objects

    def _parse_text(
        self, annotations, image_width: int, image_height: int
    ) -> list[TextBlock]:
        """Parse text detection results with normalized coordinates."""
        text_blocks = []

        # Avoid division by zero
        if image_width <= 0:
            image_width = 1000
        if image_height <= 0:
            image_height = 1000

        # Skip first annotation (it's the full text)
        for ann in annotations[1:] if annotations else []:
            vertices = ann.bounding_poly.vertices
            if len(vertices) >= 4:
                x_coords = [v.x for v in vertices]
                y_coords = [v.y for v in vertices]

                # Normalize pixel coordinates to 0-1 range
                min_x = min(x_coords) / image_width
                min_y = min(y_coords) / image_height
                width = (max(x_coords) - min(x_coords)) / image_width
                height = (max(y_coords) - min(y_coords)) / image_height

                bbox = BoundingBox(
                    x=min_x,
                    y=min_y,
                    width=width,
                    height=height
                )

                text_blocks.append(TextBlock(
                    text=ann.description,
                    bbox=bbox,
                    confidence=0.9  # Vision API doesn't provide per-word confidence
                ))

        return text_blocks


class MockVisionService:
    """Mock vision service for testing without API calls."""

    def __init__(self, scenario: str = "full_shelf"):
        self.scenario = scenario

    def analyze(self, image_bytes: bytes) -> VisionResult:
        """Return mock vision results."""
        if self.scenario == "full_shelf":
            return self._full_shelf_result()
        elif self.scenario == "partial":
            return self._partial_result()
        else:
            return self._empty_result()

    def _full_shelf_result(self) -> VisionResult:
        """8 bottles with OCR text."""
        objects = [
            DetectedObject("Bottle", 0.95, BoundingBox(0.05, 0.15, 0.08, 0.35)),
            DetectedObject("Bottle", 0.93, BoundingBox(0.15, 0.12, 0.09, 0.38)),
            DetectedObject("Bottle", 0.91, BoundingBox(0.26, 0.14, 0.08, 0.36)),
            DetectedObject("Bottle", 0.89, BoundingBox(0.36, 0.13, 0.08, 0.37)),
            DetectedObject("Bottle", 0.87, BoundingBox(0.46, 0.16, 0.08, 0.34)),
            DetectedObject("Bottle", 0.85, BoundingBox(0.56, 0.14, 0.08, 0.36)),
            DetectedObject("Bottle", 0.83, BoundingBox(0.66, 0.15, 0.08, 0.35)),
            DetectedObject("Bottle", 0.80, BoundingBox(0.76, 0.17, 0.08, 0.33)),
        ]

        text_blocks = [
            TextBlock("CAYMUS", BoundingBox(0.06, 0.25, 0.06, 0.04), 0.9),
            TextBlock("Cabernet Sauvignon", BoundingBox(0.05, 0.30, 0.08, 0.03), 0.9),
            TextBlock("2021", BoundingBox(0.06, 0.34, 0.04, 0.02), 0.9),
            TextBlock("OPUS ONE", BoundingBox(0.16, 0.22, 0.07, 0.04), 0.9),
            TextBlock("Napa Valley", BoundingBox(0.16, 0.27, 0.07, 0.03), 0.9),
            TextBlock("2019", BoundingBox(0.17, 0.31, 0.04, 0.02), 0.9),
            TextBlock("SILVER OAK", BoundingBox(0.27, 0.24, 0.06, 0.04), 0.9),
            TextBlock("Alexander Valley", BoundingBox(0.26, 0.29, 0.08, 0.03), 0.9),
            TextBlock("JORDAN", BoundingBox(0.37, 0.23, 0.06, 0.04), 0.9),
            TextBlock("Cabernet", BoundingBox(0.37, 0.28, 0.06, 0.03), 0.9),
            TextBlock("KENDALL", BoundingBox(0.47, 0.26, 0.06, 0.04), 0.9),
            TextBlock("JACKSON", BoundingBox(0.47, 0.30, 0.06, 0.03), 0.9),
            TextBlock("LA CREMA", BoundingBox(0.57, 0.24, 0.06, 0.04), 0.9),
            TextBlock("Pinot Noir", BoundingBox(0.57, 0.29, 0.06, 0.03), 0.9),
            TextBlock("MEIOMI", BoundingBox(0.67, 0.25, 0.06, 0.04), 0.9),
            TextBlock("Pinot Noir", BoundingBox(0.67, 0.30, 0.06, 0.03), 0.9),
            TextBlock("BREAD", BoundingBox(0.77, 0.27, 0.06, 0.04), 0.9),
            TextBlock("BUTTER", BoundingBox(0.77, 0.31, 0.06, 0.03), 0.9),
        ]

        return VisionResult(
            objects=objects,
            text_blocks=text_blocks,
            raw_text="",
            image_width=1000,
            image_height=1000
        )

    def _partial_result(self) -> VisionResult:
        """3 bottles detected."""
        objects = [
            DetectedObject("Bottle", 0.94, BoundingBox(0.10, 0.15, 0.10, 0.35)),
            DetectedObject("Bottle", 0.91, BoundingBox(0.30, 0.12, 0.10, 0.38)),
            DetectedObject("Bottle", 0.88, BoundingBox(0.50, 0.14, 0.10, 0.36)),
        ]

        text_blocks = [
            TextBlock("CAYMUS", BoundingBox(0.11, 0.25, 0.08, 0.04), 0.9),
            TextBlock("OPUS ONE", BoundingBox(0.31, 0.22, 0.08, 0.04), 0.9),
            TextBlock("SILVER OAK", BoundingBox(0.51, 0.24, 0.08, 0.04), 0.9),
        ]

        return VisionResult(
            objects=objects,
            text_blocks=text_blocks,
            raw_text="",
            image_width=1000,
            image_height=1000
        )

    def _empty_result(self) -> VisionResult:
        """No bottles detected."""
        return VisionResult(
            objects=[],
            text_blocks=[],
            raw_text="",
            image_width=1000,
            image_height=1000
        )


class ReplayVisionService:
    """
    Replay captured Vision API responses for deterministic testing.

    Loads a previously captured response from JSON and returns it
    regardless of the input image, enabling repeatable tests.
    """

    def __init__(self, fixture_path: str | Path):
        """
        Initialize with path to captured response fixture.

        Args:
            fixture_path: Path to JSON file containing captured Vision API response
        """
        self._fixture_path = Path(fixture_path)
        self._data: Optional[dict] = None

    def _load_fixture(self) -> dict:
        """Lazy load fixture data."""
        if self._data is None:
            with open(self._fixture_path) as f:
                self._data = json.load(f)
        return self._data

    def analyze(self, image_bytes: bytes) -> VisionResult:
        """
        Return captured Vision API response.

        Args:
            image_bytes: Ignored - returns captured response regardless of input

        Returns:
            VisionResult from captured fixture
        """
        data = self._load_fixture()

        # Parse objects from fixture
        objects = [
            DetectedObject(
                name=obj["name"],
                confidence=obj["score"],
                bbox=BoundingBox(
                    x=obj["bbox"]["x"],
                    y=obj["bbox"]["y"],
                    width=obj["bbox"]["width"],
                    height=obj["bbox"]["height"],
                )
            )
            for obj in data.get("objects", [])
        ]

        # Parse text blocks from fixture
        text_blocks = [
            TextBlock(
                text=block["text"],
                bbox=BoundingBox(
                    x=block["bbox"]["x"],
                    y=block["bbox"]["y"],
                    width=block["bbox"]["width"],
                    height=block["bbox"]["height"],
                ) if block.get("bbox") else BoundingBox(0, 0, 0, 0),
                confidence=block.get("confidence", 0.9),
            )
            for block in data.get("text_blocks", [])
        ]

        return VisionResult(
            objects=objects,
            text_blocks=text_blocks,
            raw_text=data.get("raw_text", ""),
            image_width=data.get("image_width", 1000),
            image_height=data.get("image_height", 1000)
        )
