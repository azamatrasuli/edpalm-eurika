"""Dashboard data access: aggregation queries for metrics, conversations, escalations."""

from __future__ import annotations

import logging
from datetime import date

import psycopg
from psycopg.types.json import Json

from app.db.pool import get_connection, has_pool

logger = logging.getLogger("db.dashboard")


class DashboardRepository:

    def _has_db(self) -> bool:
        return has_pool()

    def get_metrics(
        self,
        date_from: date,
        date_to: date,
        channel: str | None = None,
        agent_role: str | None = None,
    ) -> dict:
        """Aggregate dashboard metrics for the given period."""
        if not self._has_db():
            return self._empty_metrics()

        try:
            with get_connection() as conn:
                if conn is None:
                    return self._empty_metrics()
                with conn.cursor() as cur:
                    # Conversations
                    where = "WHERE c.created_at >= %s AND c.created_at < %s + INTERVAL '1 day'"
                    params: list = [date_from, date_to]
                    if channel:
                        where += " AND c.channel = %s"
                        params.append(channel)
                    if agent_role:
                        where += " AND c.agent_role = %s"
                        params.append(agent_role)

                    cur.execute(
                        f"""
                        SELECT
                          COUNT(*) AS total,
                          COUNT(*) FILTER (WHERE c.archived_at IS NULL AND c.status != 'escalated') AS active,
                          COUNT(*) FILTER (WHERE c.archived_at IS NOT NULL) AS completed,
                          COUNT(*) FILTER (WHERE c.status = 'escalated') AS escalated
                        FROM conversations c
                        {where}
                        """,
                        params,
                    )
                    conv_row = cur.fetchone()

                    # GMV + conversion from payment orders
                    pay_where = "WHERE po.created_at >= %s AND po.created_at < %s + INTERVAL '1 day'"
                    pay_params: list = [date_from, date_to]
                    if channel:
                        pay_where += """
                            AND po.conversation_id IN (
                                SELECT id FROM conversations WHERE channel = %s
                            )
                        """
                        pay_params.append(channel)

                    cur.execute(
                        f"""
                        SELECT
                          COUNT(*) AS total_with_payment,
                          COUNT(*) FILTER (WHERE po.status = 'paid') AS paid,
                          COALESCE(SUM(po.amount_kopecks) FILTER (WHERE po.status = 'paid'), 0) AS gmv_kopecks
                        FROM agent_payment_orders po
                        {pay_where}
                        """,
                        pay_params,
                    )
                    pay_row = cur.fetchone()

                    # Escalation reasons from events
                    esc_where = "WHERE e.event_type = 'escalation' AND e.created_at >= %s AND e.created_at < %s + INTERVAL '1 day'"
                    esc_params: list = [date_from, date_to]
                    if channel:
                        esc_where += " AND e.channel = %s"
                        esc_params.append(channel)

                    cur.execute(
                        f"""
                        SELECT
                          e.event_data->>'reason' AS reason,
                          COUNT(*) AS cnt
                        FROM agent_events e
                        {esc_where}
                        GROUP BY e.event_data->>'reason'
                        ORDER BY cnt DESC
                        LIMIT 10
                        """,
                        esc_params,
                    )
                    esc_reasons = [dict(r) for r in cur.fetchall()]

                    # Channels breakdown
                    cur.execute(
                        f"""
                        SELECT c.channel, COUNT(*) AS cnt
                        FROM conversations c
                        {where}
                        GROUP BY c.channel
                        """,
                        params,
                    )
                    channels = {r["channel"]: r["cnt"] for r in cur.fetchall()}

                    # Daily series
                    cur.execute(
                        f"""
                        SELECT
                          c.created_at::date AS day,
                          COUNT(*) AS conversations,
                          COALESCE(SUM(po.amount_kopecks) FILTER (WHERE po.status = 'paid'), 0) AS gmv_kopecks
                        FROM conversations c
                        LEFT JOIN agent_payment_orders po ON po.conversation_id = c.id AND po.status = 'paid'
                        {where}
                        GROUP BY c.created_at::date
                        ORDER BY day
                        """,
                        params,
                    )
                    daily = [
                        {
                            "date": str(r["day"]),
                            "conversations": r["conversations"],
                            "gmv_rub": r["gmv_kopecks"] / 100,
                        }
                        for r in cur.fetchall()
                    ]

            total = conv_row["total"] or 0
            paid = pay_row["paid"] or 0
            total_payment = pay_row["total_with_payment"] or 0
            gmv_kopecks = pay_row["gmv_kopecks"] or 0

            return {
                "conversations": {
                    "total": total,
                    "active": conv_row["active"] or 0,
                    "completed": conv_row["completed"] or 0,
                    "escalated": conv_row["escalated"] or 0,
                },
                "conversion": {
                    "total_with_payment": total_payment,
                    "paid": paid,
                    "rate_percent": round(paid / total * 100, 2) if total else 0,
                },
                "gmv": {
                    "total_rub": gmv_kopecks / 100,
                    "avg_check_rub": round(gmv_kopecks / paid / 100, 2) if paid else 0,
                    "count": paid,
                },
                "escalations": {
                    "total": conv_row["escalated"] or 0,
                    "reasons": [{"reason": r["reason"] or "—", "count": r["cnt"]} for r in esc_reasons],
                },
                "channels": channels,
                "daily": daily,
            }

        except (psycopg.Error, OSError):
            logger.exception("Failed to get dashboard metrics")
            return self._empty_metrics()

    def get_conversations(
        self,
        date_from: date,
        date_to: date,
        channel: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        if not self._has_db():
            return {"items": [], "total": 0, "page": page, "per_page": per_page}

        try:
            with get_connection() as conn:
                if conn is None:
                    return {"items": [], "total": 0, "page": page, "per_page": per_page}
                with conn.cursor() as cur:
                    where = "WHERE c.created_at >= %s AND c.created_at < %s + INTERVAL '1 day'"
                    params: list = [date_from, date_to]
                    if channel:
                        where += " AND c.channel = %s"
                        params.append(channel)
                    if status == "active":
                        where += " AND c.archived_at IS NULL AND c.status != 'escalated'"
                    elif status == "completed":
                        where += " AND c.archived_at IS NOT NULL"
                    elif status == "escalated":
                        where += " AND c.status = 'escalated'"

                    cur.execute(f"SELECT COUNT(*) AS cnt FROM conversations c {where}", params)
                    total = cur.fetchone()["cnt"]

                    offset = (page - 1) * per_page
                    cur.execute(
                        f"""
                        SELECT
                          c.id, c.actor_id, c.channel, c.agent_role, c.status,
                          c.title, c.created_at, c.archived_at,
                          (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id) AS message_count,
                          EXISTS(SELECT 1 FROM agent_payment_orders po WHERE po.conversation_id = c.id) AS has_payment,
                          (SELECT po.status FROM agent_payment_orders po WHERE po.conversation_id = c.id ORDER BY po.created_at DESC LIMIT 1) AS payment_status
                        FROM conversations c
                        {where}
                        ORDER BY c.created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        params + [per_page, offset],
                    )
                    items = []
                    for r in cur.fetchall():
                        items.append({
                            "id": str(r["id"]),
                            "actor_id": r["actor_id"],
                            "channel": r["channel"],
                            "agent_role": r.get("agent_role", "sales"),
                            "status": r.get("status"),
                            "display_name": r.get("title"),
                            "started_at": r["created_at"].isoformat() if r["created_at"] else None,
                            "ended_at": r["archived_at"].isoformat() if r.get("archived_at") else None,
                            "message_count": r["message_count"],
                            "has_payment": r["has_payment"],
                            "payment_status": r.get("payment_status"),
                        })

            return {"items": items, "total": total, "page": page, "per_page": per_page}

        except (psycopg.Error, OSError):
            logger.exception("Failed to get dashboard conversations")
            return {"items": [], "total": 0, "page": page, "per_page": per_page}

    def get_escalations(
        self,
        date_from: date,
        date_to: date,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        if not self._has_db():
            return {"items": [], "total": 0, "page": page, "per_page": per_page}

        try:
            with get_connection() as conn:
                if conn is None:
                    return {"items": [], "total": 0, "page": page, "per_page": per_page}
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM agent_events
                        WHERE event_type = 'escalation'
                          AND created_at >= %s AND created_at < %s + INTERVAL '1 day'
                        """,
                        (date_from, date_to),
                    )
                    total = cur.fetchone()["cnt"]

                    offset = (page - 1) * per_page
                    cur.execute(
                        """
                        SELECT
                          e.id, e.conversation_id, e.actor_id, e.channel,
                          e.event_data->>'reason' AS reason,
                          e.created_at
                        FROM agent_events e
                        WHERE e.event_type = 'escalation'
                          AND e.created_at >= %s AND e.created_at < %s + INTERVAL '1 day'
                        ORDER BY e.created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (date_from, date_to, per_page, offset),
                    )
                    items = []
                    for r in cur.fetchall():
                        items.append({
                            "id": str(r["id"]),
                            "conversation_id": str(r["conversation_id"]) if r["conversation_id"] else None,
                            "actor_id": r["actor_id"],
                            "channel": r["channel"],
                            "reason": r["reason"],
                            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                        })

            return {"items": items, "total": total, "page": page, "per_page": per_page}

        except (psycopg.Error, OSError):
            logger.exception("Failed to get dashboard escalations")
            return {"items": [], "total": 0, "page": page, "per_page": per_page}

    def get_unanswered(
        self,
        date_from: date,
        date_to: date,
        limit: int = 20,
    ) -> list[dict]:
        if not self._has_db():
            return []

        try:
            with get_connection() as conn:
                if conn is None:
                    return []
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                          e.event_data->>'query' AS query,
                          COUNT(*) AS cnt,
                          MAX(e.created_at) AS last_seen
                        FROM agent_events e
                        WHERE e.event_type = 'rag_miss'
                          AND e.created_at >= %s AND e.created_at < %s + INTERVAL '1 day'
                        GROUP BY e.event_data->>'query'
                        ORDER BY cnt DESC
                        LIMIT %s
                        """,
                        (date_from, date_to, limit),
                    )
                    return [
                        {
                            "query": r["query"],
                            "count": r["cnt"],
                            "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                        }
                        for r in cur.fetchall()
                    ]

        except (psycopg.Error, OSError):
            logger.exception("Failed to get unanswered questions")
            return []

    @staticmethod
    def _empty_metrics() -> dict:
        return {
            "conversations": {"total": 0, "active": 0, "completed": 0, "escalated": 0},
            "conversion": {"total_with_payment": 0, "paid": 0, "rate_percent": 0},
            "gmv": {"total_rub": 0, "avg_check_rub": 0, "count": 0},
            "escalations": {"total": 0, "reasons": []},
            "channels": {},
            "daily": [],
        }
