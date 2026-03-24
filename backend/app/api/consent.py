"""Consent management API — ФЗ-152 compliance."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.auth.service import AuthService
from app.db.consent_repository import ConsentRepository
from app.logging_config import enrich_ctx
from app.models.profile import (
    ConsentGrantRequest,
    ConsentItem,
    ConsentRevokeRequest,
    ConsentStatusResponse,
    ProfileRequest,
)

logger = logging.getLogger("api.consent")

router = APIRouter(prefix="/api/v1/consent", tags=["consent"])
auth_service = AuthService()
consent_repo = ConsentRepository()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/status", response_model=ConsentStatusResponse)
def consent_status(req: ProfileRequest, request: Request) -> ConsentStatusResponse:
    """Get all consent statuses for the current user."""
    actor = auth_service.resolve(req.auth)
    enrich_ctx(user_id=actor.actor_id)

    records = consent_repo.get_user_consents(actor.actor_id)
    items = [
        ConsentItem(
            purpose_id=r.purpose_id,
            title_ru=r.title_ru,
            description=r.description,
            required=r.required,
            granted=r.granted,
            version=r.version,
            granted_at=r.granted_at,
            revoked_at=r.revoked_at,
        )
        for r in records
    ]
    all_required = all(c.granted for c in items if c.required)
    return ConsentStatusResponse(consents=items, all_required_granted=all_required)


@router.post("/grant")
def grant_consent(req: ConsentGrantRequest, request: Request):
    """Grant consent for a specific purpose."""
    actor = auth_service.resolve(req.auth)
    enrich_ctx(user_id=actor.actor_id)

    ok = consent_repo.grant_consent(
        actor_id=actor.actor_id,
        purpose_id=req.purpose_id,
        method=req.method,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if not ok:
        raise HTTPException(500, "Failed to save consent")
    return {"status": "granted", "purpose_id": req.purpose_id}


@router.post("/revoke")
def revoke_consent(req: ConsentRevokeRequest, request: Request):
    """Revoke consent for a specific purpose. Triggers side effects (e.g., memory clear)."""
    actor = auth_service.resolve(req.auth)
    enrich_ctx(user_id=actor.actor_id)

    # Check if this is a required consent
    purposes = consent_repo.get_purposes()
    purpose = next((p for p in purposes if p.id == req.purpose_id), None)
    if not purpose:
        raise HTTPException(404, "Unknown consent purpose")

    ok = consent_repo.revoke_consent(
        actor_id=actor.actor_id,
        purpose_id=req.purpose_id,
        method=req.method,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if not ok:
        raise HTTPException(500, "Failed to revoke consent")

    result = {"status": "revoked", "purpose_id": req.purpose_id}
    if purpose.required:
        result["warning"] = "Отозвано обязательное согласие. Функции чата будут ограничены."
    if req.purpose_id == "ai_memory":
        result["side_effect"] = "Вся сохранённая память очищена."
    return result
