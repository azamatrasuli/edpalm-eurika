"""Data export and deletion service — GDPR/ФЗ-152 compliance."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.types.json import Json

from app.db.pool import get_connection, has_pool

logger = logging.getLogger("data_lifecycle")

DELETION_GRACE_DAYS = 30  # 152-ФЗ: 30 дней grace period

# Tables to delete from, in order (respects FK constraints)
_DELETION_CASCADE = [
    ("chat_messages", "conversation_id IN (SELECT id FROM conversations WHERE actor_id = %s)"),
    ("agent_memory_atoms", "actor_id = %s"),
    ("agent_conversation_summaries", "actor_id = %s"),
    ("agent_deal_mapping", "conversation_id IN (SELECT id FROM conversations WHERE actor_id = %s)"),
    ("agent_contact_mapping", "actor_id = %s"),
    ("agent_chat_mapping", "actor_id = %s"),
    ("agent_consent_records", "actor_id = %s"),
    ("agent_pii_maps", "actor_id = %s"),
    ("agent_user_profiles", "actor_id = %s"),
    ("agent_followup_chain", "conversation_id IN (SELECT id FROM conversations WHERE actor_id = %s)"),
    ("agent_payment_orders", "actor_id = %s"),
    ("agent_events", "actor_id = %s"),
    ("conversations", "actor_id = %s"),
]


class DataLifecycleService:

    def _has_db(self) -> bool:
        return has_pool()

    # ---- Export ---------------------------------------------------------------

    def create_export_request(
        self, actor_id: str, ip_address: str | None = None, user_agent: str | None = None,
    ) -> str | None:
        """Create export request and build export data synchronously.

        Returns request_id or None on failure.
        For large datasets this should be async, but current scale is small enough.
        """
        if not self._has_db():
            return None
        try:
            export_data = self._build_export(actor_id)
            with get_connection() as conn:
                if conn is None:
                    return None
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_data_requests
                          (actor_id, request_type, status, export_data, completed_at, ip_address, user_agent)
                        VALUES (%s, 'export', 'ready', %s, NOW(), %s, %s)
                        RETURNING id
                        """,
                        (actor_id, Json(export_data), ip_address, user_agent),
                    )
                    row = cur.fetchone()
                conn.commit()
                request_id = str(row["id"]) if row else None
                logger.info("Export created: actor=%s request=%s", actor_id, request_id)
                return request_id
        except (psycopg.Error, OSError):
            logger.warning("Failed to create export for actor=%s", actor_id, exc_info=True)
            return None

    def get_export_data(self, request_id: str, actor_id: str) -> dict | None:
        """Retrieve export data for download. Actor check for security."""
        if not self._has_db():
            return None
        try:
            with get_connection() as conn:
                if conn is None:
                    return None
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT export_data FROM agent_data_requests
                        WHERE id = %s::uuid AND actor_id = %s AND request_type = 'export'
                        """,
                        (request_id, actor_id),
                    )
                    row = cur.fetchone()
                    return row["export_data"] if row else None
        except (psycopg.Error, OSError):
            logger.warning("Failed to get export data: request=%s", request_id, exc_info=True)
            return None

    def _build_export(self, actor_id: str) -> dict:
        """Collect all user data into a single dict."""
        export: dict = {
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
            "actor_id": actor_id,
        }
        try:
            with get_connection() as conn:
                if conn is None:
                    return export
                with conn.cursor() as cur:
                    # Profile
                    cur.execute(
                        "SELECT * FROM agent_user_profiles WHERE actor_id = %s", (actor_id,)
                    )
                    row = cur.fetchone()
                    export["profile"] = self._row_to_dict(row) if row else None

                    # Conversations
                    cur.execute(
                        """SELECT id, channel, agent_role, status, title, message_count,
                                  created_at, updated_at, archived_at
                           FROM conversations WHERE actor_id = %s ORDER BY created_at""",
                        (actor_id,),
                    )
                    export["conversations"] = [self._row_to_dict(r) for r in cur.fetchall()]

                    # Messages (last 500)
                    cur.execute(
                        """SELECT cm.conversation_id, cm.role, cm.content, cm.created_at
                           FROM chat_messages cm
                           JOIN conversations c ON c.id = cm.conversation_id
                           WHERE c.actor_id = %s
                           ORDER BY cm.created_at DESC LIMIT 500""",
                        (actor_id,),
                    )
                    export["messages"] = [self._row_to_dict(r) for r in cur.fetchall()]

                    # Memory atoms
                    cur.execute(
                        """SELECT fact_type, subject, predicate, object, created_at
                           FROM agent_memory_atoms
                           WHERE actor_id = %s AND superseded_by IS NULL""",
                        (actor_id,),
                    )
                    export["memories"] = [self._row_to_dict(r) for r in cur.fetchall()]

                    # Consents
                    cur.execute(
                        """SELECT purpose_id, granted, granted_at, revoked_at, version
                           FROM agent_consent_records WHERE actor_id = %s""",
                        (actor_id,),
                    )
                    export["consents"] = [self._row_to_dict(r) for r in cur.fetchall()]

        except (psycopg.Error, OSError):
            logger.warning("Failed to build export for actor=%s", actor_id, exc_info=True)

        return export

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert psycopg Row to JSON-safe dict."""
        d = dict(row)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
            elif hasattr(v, "__str__") and not isinstance(v, (str, int, float, bool, list, dict, type(None))):
                d[k] = str(v)
        return d

    # ---- Deletion -------------------------------------------------------------

    def create_deletion_request(
        self, actor_id: str, reason: str | None = None,
        ip_address: str | None = None, user_agent: str | None = None,
    ) -> str | None:
        """Create a deletion request with grace period. Returns request_id."""
        if not self._has_db():
            return None
        try:
            execute_after = datetime.now(tz=timezone.utc) + timedelta(days=DELETION_GRACE_DAYS)
            with get_connection() as conn:
                if conn is None:
                    return None
                with conn.cursor() as cur:
                    # Cancel any existing pending deletion first
                    cur.execute(
                        """
                        UPDATE agent_data_requests SET status = 'cancelled'
                        WHERE actor_id = %s AND request_type = 'deletion' AND status = 'pending'
                        """,
                        (actor_id,),
                    )
                    cur.execute(
                        """
                        INSERT INTO agent_data_requests
                          (actor_id, request_type, status, execute_after, reason, ip_address, user_agent)
                        VALUES (%s, 'deletion', 'pending', %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (actor_id, execute_after, reason, ip_address, user_agent),
                    )
                    row = cur.fetchone()
                conn.commit()
                request_id = str(row["id"]) if row else None
                logger.info(
                    "Deletion request created: actor=%s request=%s execute_after=%s",
                    actor_id, request_id, execute_after.isoformat(),
                )
                return request_id
        except (psycopg.Error, OSError):
            logger.warning("Failed to create deletion request for actor=%s", actor_id, exc_info=True)
            return None

    def cancel_deletion(self, actor_id: str) -> bool:
        """Cancel pending deletion request during grace period."""
        if not self._has_db():
            return False
        try:
            with get_connection() as conn:
                if conn is None:
                    return False
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE agent_data_requests SET status = 'cancelled'
                        WHERE actor_id = %s AND request_type = 'deletion' AND status = 'pending'
                        """,
                        (actor_id,),
                    )
                    cancelled = cur.rowcount > 0
                conn.commit()
                if cancelled:
                    logger.info("Deletion cancelled for actor=%s", actor_id)
                return cancelled
        except (psycopg.Error, OSError):
            logger.warning("Failed to cancel deletion for actor=%s", actor_id, exc_info=True)
            return False

    def get_pending_deletion(self, actor_id: str) -> dict | None:
        """Check if actor has a pending deletion request."""
        if not self._has_db():
            return None
        try:
            with get_connection() as conn:
                if conn is None:
                    return None
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, execute_after, created_at, reason
                        FROM agent_data_requests
                        WHERE actor_id = %s AND request_type = 'deletion' AND status = 'pending'
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (actor_id,),
                    )
                    row = cur.fetchone()
                    return self._row_to_dict(row) if row else None
        except (psycopg.Error, OSError):
            return None

    def execute_pending_deletions(self) -> int:
        """Background job: execute deletions past grace period. Returns count."""
        if not self._has_db():
            return 0
        try:
            with get_connection() as conn:
                if conn is None:
                    return 0
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, actor_id FROM agent_data_requests
                        WHERE request_type = 'deletion'
                          AND status = 'pending'
                          AND execute_after <= NOW()
                        LIMIT 10
                        """,
                    )
                    rows = cur.fetchall()

            count = 0
            for row in rows:
                try:
                    self._execute_deletion(str(row["id"]), row["actor_id"])
                    count += 1
                except Exception:
                    logger.warning("Deletion failed for actor=%s", row["actor_id"], exc_info=True)

            if count:
                logger.info("Executed %d/%d pending deletions", count, len(rows))
            return count
        except (psycopg.Error, OSError):
            logger.warning("Failed to process pending deletions", exc_info=True)
            return 0

    def _execute_deletion(self, request_id: str, actor_id: str) -> None:
        """Cascade delete all user data across all tables."""
        with get_connection() as conn:
            if conn is None:
                raise OSError("No DB connection")
            with conn.cursor() as cur:
                # Mark as processing
                cur.execute(
                    "UPDATE agent_data_requests SET status = 'processing' WHERE id = %s::uuid",
                    (request_id,),
                )

                for table, where_clause in _DELETION_CASCADE:
                    try:
                        cur.execute(f"DELETE FROM {table} WHERE {where_clause}", (actor_id,))
                        deleted = cur.rowcount
                        if deleted:
                            logger.info("Deleted %d rows from %s for actor=%s", deleted, table, actor_id)
                    except psycopg.Error:
                        # Table might not exist or FK issue — continue with others
                        logger.debug("Skip deletion from %s for actor=%s", table, actor_id, exc_info=True)

                # Mark completed (keep the request record itself for audit)
                cur.execute(
                    "UPDATE agent_data_requests SET status = 'completed', completed_at = NOW() WHERE id = %s::uuid",
                    (request_id,),
                )
            conn.commit()
            logger.info("Deletion completed: actor=%s request=%s", actor_id, request_id)
