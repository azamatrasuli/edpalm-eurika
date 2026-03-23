"""Funnel stage management service.

Manages deal progression through amoCRM pipeline stages,
enforces transition rules, and tracks stage history.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.db.repository import ConversationRepository
from app.integrations.amocrm import AmoCRMClient

logger = logging.getLogger("funnel")

# ---------------------------------------------------------------------------
# Stage names (internal) — mapped to amoCRM status_id via config
# ---------------------------------------------------------------------------

SALES_STAGES = (
    "new",
    "info_gathering",
    "proposal",
    "manager_review",
    "awaiting_payment",
    "paid",
    "declined",
    "archive",
)

# Allowed transitions: stage → list of valid next stages
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "new": ["info_gathering"],
    "info_gathering": ["proposal"],
    "proposal": ["manager_review", "declined"],
    "manager_review": ["awaiting_payment", "declined"],
    "awaiting_payment": ["paid", "declined"],
    "paid": [],  # terminal
    "declined": [],  # terminal (reanimation handled separately)
    "archive": [],  # terminal, only via manager
}


class FunnelService:
    """Manages deal stage transitions in the sales funnel."""

    def __init__(
        self,
        repo: ConversationRepository | None = None,
        crm: AmoCRMClient | None = None,
    ) -> None:
        self.repo = repo or ConversationRepository()
        self.crm = crm or AmoCRMClient()
        self._settings = get_settings()

    def _stage_to_status_id(self, stage: str) -> int | None:
        """Map internal stage name to amoCRM status_id from config."""
        mapping = {
            "new": self._settings.amocrm_stage_new,
            "info_gathering": self._settings.amocrm_stage_info_gathering,
            "proposal": self._settings.amocrm_stage_proposal,
            "manager_review": self._settings.amocrm_stage_manager_review,
            "awaiting_payment": self._settings.amocrm_stage_awaiting_payment,
            "paid": self._settings.amocrm_stage_paid,
            "declined": self._settings.amocrm_stage_declined,
            "archive": self._settings.amocrm_stage_archive,
        }
        status_id = mapping.get(stage, 0)
        return status_id if status_id else None

    def can_advance(self, current_stage: str | None, target_stage: str) -> bool:
        """Check if transition from current_stage to target_stage is allowed."""
        if current_stage is None:
            # First stage — allow any starting point
            return target_stage in SALES_STAGES
        allowed = ALLOWED_TRANSITIONS.get(current_stage, [])
        return target_stage in allowed

    def get_current_stage(self, conversation_id: str) -> str | None:
        """Get the current funnel stage for a conversation."""
        info = self.repo.get_funnel_stage(conversation_id)
        return info["funnel_stage"] if info else None

    def advance_stage(
        self,
        conversation_id: str,
        lead_id: int | None,
        new_stage: str,
        *,
        force: bool = False,
    ) -> bool:
        """Advance deal to a new stage.

        Updates both local DB and amoCRM lead status.
        Returns True if successful.
        """
        current = self.get_current_stage(conversation_id)

        if not force and not self.can_advance(current, new_stage):
            logger.warning(
                "Invalid stage transition: %s → %s (conv=%s)",
                current, new_stage, conversation_id,
            )
            return False

        # Update local DB
        history_entry = {
            "stage": new_stage,
            "from": current,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.repo.update_funnel_stage(conversation_id, new_stage, pipeline="sales")
        self.repo.update_deal_funnel_stage(
            conversation_id, new_stage, stage_history_entry=history_entry,
        )

        # Update amoCRM lead if possible
        status_id = self._stage_to_status_id(new_stage)
        if lead_id and status_id:
            try:
                self.crm.update_lead(lead_id, status_id=status_id)
                logger.info(
                    "Stage advanced: %s → %s (lead=%d, conv=%s, status_id=%d)",
                    current, new_stage, lead_id, conversation_id, status_id,
                )
            except Exception:
                logger.warning(
                    "Failed to update amoCRM lead stage (non-blocking)",
                    exc_info=True,
                )
        else:
            logger.info(
                "Stage advanced locally: %s → %s (conv=%s, no CRM update)",
                current, new_stage, conversation_id,
            )

        return True

    def is_manager_approved(self, conversation_id: str) -> bool:
        """Check if manager has approved this deal for payment."""
        return self.repo.is_manager_approved(conversation_id)

    def approve_by_manager(self, conversation_id: str) -> bool:
        """Manager approves the deal — unlocks payment."""
        approved = self.repo.set_manager_approved(conversation_id)
        if approved:
            # Auto-advance to awaiting_payment
            deal = self.repo.get_deal_mapping(conversation_id)
            lead_id = deal.get("amocrm_lead_id") if deal else None
            self.advance_stage(
                conversation_id, lead_id, "awaiting_payment", force=True,
            )
            logger.info("Manager approved deal: conv=%s", conversation_id)
        return approved

    def is_archive_stage(self, status_id: int) -> bool:
        """Check if a status_id is the archive stage."""
        archive_id = self._settings.amocrm_stage_archive
        return archive_id != 0 and status_id == archive_id

    def move_to_reanimation(
        self,
        contact_id: int,
        decline_reasons: list[str],
        original_lead_id: int | None = None,
    ) -> int | None:
        """Create a reanimation deal for a declined client.

        Returns the new lead_id or None if reanimation pipeline is not configured.
        """
        pipeline_id = self._settings.amocrm_reanimation_pipeline_id
        if not pipeline_id:
            logger.info("Reanimation pipeline not configured, skipping")
            return None

        try:
            lead = self.crm.create_lead(
                name=f"Реанимация: контакт {contact_id}",
                contact_id=contact_id,
                pipeline_id=pipeline_id,
            )
            if lead:
                reasons_text = ", ".join(decline_reasons)
                note = f"🔄 Автоматическая реанимация\nПричины отказа: {reasons_text}"
                if original_lead_id:
                    note += f"\nОригинальная сделка: #{original_lead_id}"
                self.crm.add_note(lead.id, note)
                logger.info(
                    "Reanimation deal created: lead=%d contact=%d original=%s",
                    lead.id, contact_id, original_lead_id,
                )
                return lead.id
        except Exception:
            logger.warning("Failed to create reanimation deal", exc_info=True)
        return None

    def check_stale_deals(self) -> dict:
        """Check for deals past their stage TTL and take action.

        Returns summary of actions taken.
        """
        from datetime import timedelta

        STAGE_TTL = {
            "new": timedelta(hours=24),
            "info_gathering": timedelta(hours=48),
            "proposal": timedelta(hours=24),
            "manager_review": timedelta(hours=4),
            "awaiting_payment": timedelta(days=7),
        }

        actions = []
        # Query conversations with funnel_stage set and check staleness
        if not self.repo._has_db():
            return {"actions": [], "message": "No DB connection"}

        try:
            from app.db.pool import get_connection
            with get_connection() as conn:
                if conn is None:
                    return {"actions": [], "message": "No DB connection"}
                with conn.cursor() as cur:
                    for stage, ttl in STAGE_TTL.items():
                        cur.execute(
                            """
                            SELECT c.id, c.actor_id, d.amocrm_lead_id
                            FROM conversations c
                            LEFT JOIN agent_deal_mapping d ON d.conversation_id = c.id
                            WHERE c.funnel_stage = %s
                              AND c.updated_at < NOW() - %s::interval
                              AND c.status != 'escalated'
                              AND c.archived_at IS NULL
                            LIMIT 50
                            """,
                            (stage, str(ttl)),
                        )
                        stale = cur.fetchall()
                        for row in stale:
                            conv_id = str(row["id"])
                            lead_id = row.get("amocrm_lead_id")
                            action = {
                                "conversation_id": conv_id,
                                "stage": stage,
                                "action": "reminded" if stage == "manager_review" else "stale_flagged",
                            }
                            # Manager review past 4h → send reminder
                            if stage == "manager_review" and lead_id:
                                try:
                                    self.crm.add_note(
                                        lead_id,
                                        "⏰ Напоминание: сделка ожидает согласования более 4 часов.",
                                    )
                                except Exception:
                                    pass
                            # Awaiting payment past 7d → decline
                            elif stage == "awaiting_payment":
                                self.advance_stage(conv_id, lead_id, "declined", force=True)
                                action["action"] = "auto_declined"

                            actions.append(action)
                            logger.info("Stale deal: conv=%s stage=%s action=%s", conv_id, stage, action["action"])

        except Exception:
            logger.warning("check_stale_deals failed", exc_info=True)
            return {"actions": actions, "error": "Partial failure"}

        return {"actions": actions, "total": len(actions)}
