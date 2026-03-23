"""Auto-renewal service.

Generates renewal deals for active students before the new school year.
Triggered via cron endpoint POST /api/v1/admin/trigger-renewals.
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.integrations.amocrm import AmoCRMClient
from app.integrations.dms import get_dms_service

logger = logging.getLogger("renewal")


class RenewalService:
    """Generates auto-renewal deals for active students."""

    def __init__(self) -> None:
        self.crm = AmoCRMClient()
        self.dms = get_dms_service()
        self._settings = get_settings()

    def generate_renewal_deals(self) -> dict:
        """Generate renewal deals for all active students in DMS.

        For each active student:
        1. Determine next year's grade (grade + 1)
        2. Check if renewal deal already exists in amoCRM
        3. Create new deal in sales pipeline if not
        4. Add qualification note

        Returns summary of created deals.
        """
        pipeline_id = self._settings.amocrm_sales_pipeline_id
        created = []
        skipped = []
        errors = []

        # Get all contacts with active students from DMS
        # Note: DMS doesn't have a "list all" endpoint, so we work with
        # contacts we already know about from amoCRM
        try:
            # Get all contacts from amoCRM that have deals in sales pipeline
            # This is a pragmatic approach — we renew clients we already know
            all_contacts = self._get_known_contacts()
        except Exception:
            logger.exception("Failed to get contacts for renewal")
            return {"created": [], "skipped": [], "errors": ["Failed to get contacts"]}

        for contact in all_contacts:
            try:
                result = self._process_contact_renewal(contact, pipeline_id)
                if result == "created":
                    created.append({"contact_id": contact["id"], "name": contact["name"]})
                elif result == "skipped":
                    skipped.append({"contact_id": contact["id"], "name": contact["name"]})
            except Exception as e:
                errors.append({"contact_id": contact["id"], "error": str(e)})
                logger.warning("Renewal failed for contact %d: %s", contact["id"], e)

        logger.info(
            "Renewal generation complete: created=%d skipped=%d errors=%d",
            len(created), len(skipped), len(errors),
        )
        return {
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "total_processed": len(all_contacts),
        }

    def _get_known_contacts(self) -> list[dict]:
        """Get contacts that have existing deals (won) in sales pipeline.

        These are the clients who need renewal for the next year.
        """
        contacts = []
        # Search for won deals in sales pipeline
        from app.db.pool import get_connection

        try:
            with get_connection() as conn:
                if conn is None:
                    return []
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT DISTINCT acm.amocrm_contact_id AS id,
                               acm.contact_name AS name,
                               aup.phone
                        FROM agent_contact_mapping acm
                        LEFT JOIN agent_user_profiles aup ON aup.actor_id = acm.actor_id
                        WHERE aup.dms_verified = true
                        LIMIT 500
                        """,
                    )
                    for row in cur.fetchall():
                        contacts.append({
                            "id": row["id"],
                            "name": row["name"],
                            "phone": row.get("phone"),
                        })
        except Exception:
            logger.warning("Failed to query known contacts", exc_info=True)

        return contacts

    def _process_contact_renewal(self, contact: dict, pipeline_id: int) -> str:
        """Process renewal for a single contact.

        Returns 'created', 'skipped', or raises exception.
        """
        contact_id = contact["id"]
        phone = contact.get("phone")

        # Check if already has active deal (skip if so)
        existing = self.crm.find_active_lead(contact_id, pipeline_id=pipeline_id)
        if existing:
            return "skipped"

        # Look up DMS for current students
        if not phone:
            return "skipped"

        dms_result = self.dms.search_contact_by_phone(phone)
        if not dms_result or not dms_result.students:
            return "skipped"

        # For each active student, create a renewal deal
        for student in dms_result.students:
            if student.state and student.state != "active":
                continue

            next_grade = (student.grade or 0) + 1
            if next_grade > 11:
                continue  # Graduated, no renewal

            deal_name = f"Автопролонгация: {student.fio} → {next_grade} класс"
            lead = self.crm.create_lead(
                name=deal_name,
                contact_id=contact_id,
                pipeline_id=pipeline_id,
                product=student.product_name,
            )
            if lead:
                note = (
                    f"🔄 Автопролонгация\n"
                    f"Ученик: {student.fio}\n"
                    f"Текущий класс: {student.grade}\n"
                    f"Новый класс: {next_grade}\n"
                    f"Текущий продукт: {student.product_name}\n"
                    f"Автоматически создано системой."
                )
                self.crm.add_note(lead.id, note)
                logger.info(
                    "Renewal deal created: lead=%d student=%s grade=%d→%d",
                    lead.id, student.fio, student.grade or 0, next_grade,
                )

        return "created"
