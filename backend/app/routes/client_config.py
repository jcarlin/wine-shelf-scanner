"""
GET /config — server-driven client configuration (W4).

The iOS app fetches this at launch and overrides its local feature flags,
so the paywall (feature_subscription) can be activated after launch without
an App Store resubmission. Add fields conservatively: everything here is
public and consumed by shipped clients.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..feature_flags import FeatureFlags, get_feature_flags

router = APIRouter()


class ClientConfig(BaseModel):
    feature_subscription: bool = Field(
        ..., description="Whether the client should enforce the free-scan paywall"
    )


@router.get("/config", response_model=ClientConfig)
async def client_config(flags: FeatureFlags = Depends(get_feature_flags)) -> ClientConfig:
    return ClientConfig(feature_subscription=flags.feature_subscription)
