"""
Device attestation endpoints (W1 abuse protection).

POST /device/challenge — issue a single-use challenge (used for both the
one-time attestation and each per-scan assertion).
POST /device/register — verify an App Attest attestation and store the
device's public key. The /scan route then accepts assertions from that key.
"""

import base64
import logging

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..config import Config
from ..services import app_attest
from ..services.abuse_protection import get_challenge_store, get_device_registry

logger = logging.getLogger(__name__)

router = APIRouter()


class ChallengeResponse(BaseModel):
    challenge: str = Field(..., description="Base64 single-use challenge (5 min TTL)")


class RegisterRequest(BaseModel):
    key_id: str = Field(..., description="Base64 App Attest key identifier")
    attestation: str = Field(..., description="Base64 CBOR attestation object")
    challenge: str = Field(..., description="The challenge the attestation was generated over")


@router.post("/device/challenge", response_model=ChallengeResponse)
async def issue_challenge() -> ChallengeResponse:
    return ChallengeResponse(challenge=get_challenge_store().issue())


@router.post("/device/register", status_code=204)
async def register_device(body: RegisterRequest) -> Response:
    if not Config.app_attest_team_id():
        raise HTTPException(
            status_code=503, detail="App Attest is not configured on this server"
        )
    if not get_challenge_store().consume(body.challenge):
        raise HTTPException(status_code=403, detail="Unknown or expired challenge")

    try:
        attested = app_attest.verify_attestation(
            base64.b64decode(body.attestation),
            base64.b64decode(body.key_id),
            base64.b64decode(body.challenge),
            app_id=Config.app_attest_app_id(),
            allow_development=Config.app_attest_allow_development(),
        )
    except (app_attest.AttestationError, ValueError) as e:
        logger.warning(f"device registration rejected: {e}")
        raise HTTPException(status_code=403, detail="Attestation verification failed")

    get_device_registry().register(body.key_id, attested.public_key_pem, attested.counter)
    logger.info(f"device registered: key_id={body.key_id[:12]}…")
    return Response(status_code=204)
