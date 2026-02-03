"""
Pydantic models for the Wine Shelf Scanner API response.

API Contract (DO NOT CHANGE):
{
  "image_id": "string",
  "results": [
    {
      "wine_name": "string",
      "rating": 4.6,
      "confidence": 0.92,
      "bbox": {
        "x": 0.25,
        "y": 0.40,
        "width": 0.10,
        "height": 0.30
      }
    }
  ],
  "fallback_list": [
    {
      "wine_name": "string",
      "rating": 4.3
    }
  ]
}
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BoundingBox(BaseModel):
    """Normalized bounding box (0-1 range)."""
    x: float = Field(..., ge=0, le=1, description="Left edge (normalized)")
    y: float = Field(..., ge=0, le=1, description="Top edge (normalized)")
    width: float = Field(..., ge=0, le=1, description="Width (normalized)")
    height: float = Field(..., ge=0, le=1, description="Height (normalized)")


class WineResult(BaseModel):
    """A detected wine bottle with rating and position."""
    wine_name: str = Field(..., description="Canonical wine name")
    rating: Optional[float] = Field(None, description="Star rating (1-5), None if no rating available")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence")
    bbox: BoundingBox = Field(..., description="Bounding box position")
    identified: bool = Field(True, description="True if recognized as wine (checkmark)")
    source: str = Field("database", description="Match source: 'database' or 'llm'")
    rating_source: str = Field(
        "database",
        description="Rating provenance: 'database', 'llm_estimated', or 'none'"
    )
    # Extended metadata (optional - populated from DB or LLM)
    wine_type: Optional[str] = Field(None, description="Wine type: 'Red', 'White', 'Rosé', 'Sparkling', etc.")
    brand: Optional[str] = Field(None, description="Winery or brand name")
    region: Optional[str] = Field(None, description="Wine region (e.g., 'Napa Valley', 'Burgundy')")
    varietal: Optional[str] = Field(None, description="Grape varietal (e.g., 'Cabernet Sauvignon')")
    blurb: Optional[str] = Field(None, description="Brief description of the wine or producer")
    review_count: Optional[int] = Field(None, description="Number of reviews")
    review_snippets: Optional[list[str]] = Field(None, description="Sample review quotes")

    @field_validator('rating')
    @classmethod
    def validate_rating_range(cls, v: Optional[float]) -> Optional[float]:
        """Validate rating is in range 1-5 when not None."""
        if v is not None and (v < 1 or v > 5):
            raise ValueError('rating must be between 1 and 5')
        return v


class FallbackWine(BaseModel):
    """Wine in fallback list (no position data)."""
    wine_name: str = Field(..., description="Wine name")
    rating: float = Field(..., ge=1, le=5, description="Star rating (1-5)")


class ScanResponse(BaseModel):
    """Response from /scan endpoint."""
    image_id: str = Field(..., description="Unique identifier for this scan")
    results: list[WineResult] = Field(
        default_factory=list,
        description="Detected wines with positions"
    )
    fallback_list: list[FallbackWine] = Field(
        default_factory=list,
        description="Wines detected but not positioned"
    )
    # Debug data is only included when ?debug=true
    debug: Optional["DebugData"] = Field(
        None,
        description="Pipeline debug info (only when debug=true)"
    )


# Import at bottom to avoid circular imports
from .debug import DebugData  # noqa: E402
