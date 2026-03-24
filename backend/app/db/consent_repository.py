"""Consent management repository — ФЗ-152 compliance."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import psycopg

from app.db.pool import get_connection, has_pool

logger = logging.getLogger("consent")


@dataclass
class ConsentPurpose:
    id: str
    title_ru: str
    description: str
    required: bool
    version: str


@dataclass
class ConsentRecord:
    purpose_id: str
    title_ru: str
    description: str
    required: bool
    granted: bool
    version: str
    granted_at: datetime | None = None
    revoked_at: datetime | None = None


class ConsentRepository:
    def _has_db(self) -> bool:
        return has_pool()

    def get_purposes(self) -> list[ConsentPurpose]:
        """Get all consent purposes."""
        if not self._has_db():
            return []
        try:
            with get_connection() as conn:
                if conn is None:
                    return []
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, title_ru, description, required, version "
                        "FROM agent_consent_purposes ORDER BY id"
                    )
                    return [
                        ConsentPurpose(
                            id=r["id"], title_ru=r["title_ru"],
                            description=r["description"],
                            required=r["required"], version=r["version"],
                        )
                        for r in cur.fetchall()
                    ]
        except (psycopg.Error, OSError):
            logger.warning("Failed to get consent purposes", exc_info=True)
            return []

    def get_user_consents(self, actor_id: str) -> list[ConsentRecord]:
        """Get all consent statuses for a user (joined with purposes)."""
        if not self._has_db():
            return []
        try:
            with get_connection() as conn:
                if conn is None:
                    return []
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT p.id AS purpose_id, p.title_ru, p.description, p.required,
                               COALESCE(r.granted, FALSE) AS granted,
                               COALESCE(r.version, p.version) AS version,
                               r.granted_at, r.revoked_at
                        FROM agent_consent_purposes p
                        LEFT JOIN agent_consent_records r
                          ON r.purpose_id = p.id AND r.actor_id = %s
                        ORDER BY p.id
                        """,
                        [actor_id],
                    )
                    return [
                        ConsentRecord(
                            purpose_id=r["purpose_id"],
                            title_ru=r["title_ru"],
                            description=r["description"],
                            required=r["required"],
                            granted=r["granted"],
                            version=r["version"],
                            granted_at=r.get("granted_at"),
                            revoked_at=r.get("revoked_at"),
                        )
                        for r in cur.fetchall()
                    ]
        except (psycopg.Error, OSError):
            logger.warning("Failed to get consents for actor=%s", actor_id, exc_info=True)
            return []

    def check_consent(self, actor_id: str, purpose_id: str) -> bool:
        """Check if user has granted a specific consent."""
        if not self._has_db():
            return False
        try:
            with get_connection() as conn:
                if conn is None:
                    return False
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT granted FROM agent_consent_records "
                        "WHERE actor_id = %s AND purpose_id = %s",
                        [actor_id, purpose_id],
                    )
                    row = cur.fetchone()
                    return row["granted"] if row else False
        except (psycopg.Error, OSError):
            return False

    def grant_consent(
        self,
        actor_id: str,
        purpose_id: str,
        version: str = "1.0",
        method: str = "settings",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Grant consent — upsert record + append audit log."""
        if not self._has_db():
            return False
        try:
            with get_connection() as conn:
                if conn is None:
                    return False
                with conn.cursor() as cur:
                    # Upsert current state
                    cur.execute(
                        """
                        INSERT INTO agent_consent_records
                          (actor_id, purpose_id, granted, version, granted_at, method, ip_address, user_agent)
                        VALUES (%s, %s, TRUE, %s, NOW(), %s, %s, %s)
                        ON CONFLICT (actor_id, purpose_id) DO UPDATE SET
                          granted = TRUE,
                          version = EXCLUDED.version,
                          granted_at = NOW(),
                          revoked_at = NULL,
                          method = EXCLUDED.method,
                          ip_address = EXCLUDED.ip_address,
                          user_agent = EXCLUDED.user_agent
                        """,
                        [actor_id, purpose_id, version, method, ip_address, user_agent],
                    )
                    # Append-only audit
                    cur.execute(
                        """
                        INSERT INTO agent_consent_audit_log
                          (actor_id, purpose_id, action, version, method, ip_address, user_agent)
                        VALUES (%s, %s, 'grant', %s, %s, %s, %s)
                        """,
                        [actor_id, purpose_id, version, method, ip_address, user_agent],
                    )
                conn.commit()
                logger.info("Consent granted: actor=%s purpose=%s", actor_id, purpose_id)
                return True
        except (psycopg.Error, OSError):
            logger.warning("Failed to grant consent: actor=%s purpose=%s", actor_id, purpose_id, exc_info=True)
            return False

    def revoke_consent(
        self,
        actor_id: str,
        purpose_id: str,
        method: str = "settings",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Revoke consent — update record + append audit + trigger side effects."""
        if not self._has_db():
            return False
        try:
            # Get current version for audit
            consents = self.get_user_consents(actor_id)
            version = "1.0"
            for c in consents:
                if c.purpose_id == purpose_id:
                    version = c.version
                    break

            with get_connection() as conn:
                if conn is None:
                    return False
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE agent_consent_records
                        SET granted = FALSE, revoked_at = NOW(),
                            method = %s, ip_address = %s, user_agent = %s
                        WHERE actor_id = %s AND purpose_id = %s
                        """,
                        [method, ip_address, user_agent, actor_id, purpose_id],
                    )
                    cur.execute(
                        """
                        INSERT INTO agent_consent_audit_log
                          (actor_id, purpose_id, action, version, method, ip_address, user_agent)
                        VALUES (%s, %s, 'revoke', %s, %s, %s, %s)
                        """,
                        [actor_id, purpose_id, version, method, ip_address, user_agent],
                    )
                conn.commit()

            # Side effects based on purpose
            self._handle_revoke_side_effects(actor_id, purpose_id)

            logger.info("Consent revoked: actor=%s purpose=%s", actor_id, purpose_id)
            return True
        except (psycopg.Error, OSError):
            logger.warning("Failed to revoke consent: actor=%s purpose=%s", actor_id, purpose_id, exc_info=True)
            return False

    def _handle_revoke_side_effects(self, actor_id: str, purpose_id: str) -> None:
        """Execute side effects when consent is revoked."""
        if purpose_id == "ai_memory":
            # Clear all memory atoms
            try:
                from app.db.memory_repository import MemoryRepository
                count = MemoryRepository().clear_user_atoms(actor_id)
                logger.info("Revoke ai_memory: cleared %d atoms for actor=%s", count, actor_id)
            except Exception:
                logger.warning("Failed to clear atoms on ai_memory revoke", exc_info=True)

    def has_required_consents(self, actor_id: str) -> bool:
        """Check if user has granted all required consents."""
        consents = self.get_user_consents(actor_id)
        for c in consents:
            if c.required and not c.granted:
                return False
        return True
