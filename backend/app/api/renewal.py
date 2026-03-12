"""Renewal trigger endpoint — initiates proactive renewal conversations."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db.repository import ConversationRepository
from app.integrations.dms import get_dms_service
from app.models.chat import ActorContext, AgentRole, Channel
from app.services.followup import create_followup_chain

logger = logging.getLogger("api.renewal")

router = APIRouter(prefix="/api/v1", tags=["renewal"])


class RenewalRequest(BaseModel):
    phone: str
    actor_id: str | None = None


class RenewalResponse(BaseModel):
    success: bool
    conversation_id: str | None = None
    greeting: str | None = None
    error: str | None = None


@router.post("/renewal/trigger", response_model=RenewalResponse)
def trigger_renewal(req: RenewalRequest) -> RenewalResponse:
    """
    Trigger a renewal conversation for an existing client.
    1. Look up client in DMS by phone
    2. Create conversation with renewal metadata
    3. Generate personalized greeting
    4. Send Telegram push (if applicable)
    """
    dms = get_dms_service()
    repo = ConversationRepository()

    # 1. Look up client in DMS
    search_result = dms.search_contact_by_phone(req.phone)
    if not search_result:
        return RenewalResponse(
            success=False,
            error=f"Клиент с телефоном {req.phone} не найден в системе",
        )

    contact = search_result.contact
    students = search_result.students

    if not students:
        return RenewalResponse(
            success=False,
            error="У контакта нет привязанных учеников",
        )

    # Use first active student for context
    student = next((s for s in students if s.is_active), students[0])
    client_name = f"{contact.surname} {contact.name}".strip()

    # 2. Build actor and create conversation
    actor_id = req.actor_id or f"renewal:{contact.contact_id}"
    actor = ActorContext(
        actor_id=actor_id,
        display_name=client_name,
        channel=Channel.external,
        phone=contact.phone,
        agent_role=AgentRole.sales,
    )

    conv = repo.start_or_resume_conversation(actor)

    # Save renewal metadata on the conversation
    metadata = {
        "scenario_type": "renewal",
        "student_name": student.fio,
        "current_product": student.product_name or "—",
        "grade": student.grade,
        "contact_id": contact.contact_id,
    }
    try:
        repo.update_conversation_metadata(conv.id, metadata)
    except Exception:
        logger.exception("Failed to save renewal metadata for conv=%s", conv.id)

    # 3. Generate personalized greeting
    product_display = student.product_name or "текущую программу"
    grade_next = (student.grade or 0) + 1
    greeting = (
        f"Здравствуйте, {contact.name}! Это Эврика, виртуальный менеджер EdPalm.\n\n"
        f"Рада видеть вас снова! Учебный год подходит к концу, "
        f"и я хотела бы обсудить продление обучения для {student.fio}.\n\n"
        f"Сейчас у вас подключён тариф «{product_display}». "
        f"Как бы вы оценили обучение за этот год по шкале от 1 до 10?"
    )
    repo.save_message(conversation_id=conv.id, role="assistant", content=greeting)

    # 4. Send Telegram push if client has telegram
    _send_renewal_push(actor_id, client_name, greeting)

    logger.info("Renewal triggered for %s (conv=%s)", client_name, conv.id)

    return RenewalResponse(
        success=True,
        conversation_id=conv.id,
        greeting=greeting,
    )


def _send_renewal_push(actor_id: str, name: str, greeting: str) -> None:
    """Send Telegram push to client if actor_id is telegram-based."""
    if not actor_id.startswith("telegram:"):
        return

    settings = get_settings()
    bot_token = settings.telegram_bot_token
    if not bot_token:
        return

    chat_id = actor_id.replace("telegram:", "")
    try:
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": greeting},
            timeout=10,
        )
        logger.info("Renewal push sent to %s (%s)", name, chat_id)
    except Exception:
        logger.exception("Failed to send renewal push to %s", chat_id)
