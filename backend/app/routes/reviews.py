"""
GET /wines/{id}/reviews endpoint for Wine Shelf Scanner.

Returns reviews and review stats for a specific wine.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.wine_repository import WineRepository

logger = logging.getLogger(__name__)
router = APIRouter()


class ReviewItem(BaseModel):
    """A single review in the response."""
    source_name: str
    reviewer: Optional[str] = None
    rating: Optional[float] = None
    review_text: Optional[str] = None
    review_date: Optional[str] = None
    vintage: Optional[str] = None


class WineReviewsResponse(BaseModel):
    """Response from /wines/{id}/reviews."""
    wine_id: int
    wine_name: str
    total_reviews: int
    text_reviews: int
    avg_rating: Optional[float] = None
    reviews: list[ReviewItem] = Field(default_factory=list)


def _get_repository() -> WineRepository:
    """Get or create wine repository (lazy singleton)."""
    if not hasattr(_get_repository, "_instance"):
        _get_repository._instance = WineRepository()
    return _get_repository._instance


@router.get("/wines/{wine_id}/reviews", response_model=WineReviewsResponse)
async def get_wine_reviews(
    wine_id: int,
    limit: int = Query(default=10, ge=1, le=50, description="Max reviews to return"),
    text_only: bool = Query(default=True, description="Only return reviews with text"),
) -> WineReviewsResponse:
    """
    Get reviews for a specific wine.

    Returns review stats and individual reviews (text reviews by default).
    """
    repo = _get_repository()

    # Verify the wine exists
    wine = repo.find_by_id(wine_id)
    if not wine:
        raise HTTPException(status_code=404, detail="Wine not found")

    # Get stats and reviews
    stats = repo.get_review_stats(wine_id)
    reviews = repo.get_reviews(wine_id, limit=limit, text_only=text_only)

    return WineReviewsResponse(
        wine_id=wine_id,
        wine_name=wine.canonical_name,
        total_reviews=stats["total_reviews"],
        text_reviews=stats["text_reviews"],
        avg_rating=stats["avg_rating"],
        reviews=[
            ReviewItem(
                source_name=r.source_name,
                reviewer=r.user_id,
                rating=r.rating,
                review_text=r.review_text,
                review_date=r.review_date,
                vintage=r.vintage,
            )
            for r in reviews
        ],
    )
