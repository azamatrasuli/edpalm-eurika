"""Tests for Sprint 5: EventTracker, Dashboard API, Dashboard auth."""

from __future__ import annotations

import os

# Force test secrets before any app imports
os.environ["EXTERNAL_LINK_SECRET"] = "test_secret"
os.environ["PORTAL_JWT_SECRET"] = "test_portal"
os.environ["SESSION_SIGNING_SECRET"] = "test_session"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_tg_token"
os.environ["DASHBOARD_API_KEY"] = "test_dashboard_key"
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("AMOCRM_CLIENT_ID", "test_id")
os.environ.setdefault("AMOCRM_CLIENT_SECRET", "test_secret")

from app.config import get_settings
get_settings.cache_clear()

from unittest.mock import MagicMock, patch
from datetime import date

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

AUTH_HEADER = {"Authorization": "Bearer test_dashboard_key"}


# ---- EventTracker unit tests ----

class TestEventTracker:
    def test_event_tracker_no_db(self):
        """EventTracker gracefully does nothing without DB."""
        from app.db.events import EventTracker
        tracker = EventTracker()
        # Should not raise
        tracker.track("test_event", actor_id="test")

    def test_track_tool_call(self):
        from app.db.events import EventTracker
        tracker = EventTracker()
        # Should not raise without DB
        tracker.track_tool_call(
            "conv-1", "actor-1", "search_knowledge_base",
            {"query": "test"}, "some result", True,
        )

    def test_track_rag_miss(self):
        from app.db.events import EventTracker
        tracker = EventTracker()
        tracker.track_rag_miss("conv-1", "actor-1", "some query", "sales")

    def test_track_escalation(self):
        from app.db.events import EventTracker
        tracker = EventTracker()
        tracker.track_escalation("conv-1", "actor-1", "client angry")

    def test_track_payment(self):
        from app.db.events import EventTracker
        tracker = EventTracker()
        tracker.track_payment(
            "payment_generated", "conv-1", "actor-1",
            "order-uuid", 150000, "Экстернат",
        )

    def test_track_followup(self):
        from app.db.events import EventTracker
        tracker = EventTracker()
        tracker.track_followup("conv-1", "actor-1", 1, "order-id")


# ---- Dashboard API auth tests ----

class TestDashboardAuth:
    def test_no_auth_returns_403(self):
        r = client.get("/api/v1/dashboard/metrics")
        assert r.status_code == 403

    def test_wrong_key_returns_401(self):
        r = client.get(
            "/api/v1/dashboard/metrics",
            headers={"Authorization": "Bearer wrong_key"},
        )
        assert r.status_code == 401

    def test_valid_key_accepted(self):
        r = client.get("/api/v1/dashboard/metrics", headers=AUTH_HEADER)
        assert r.status_code == 200


# ---- Dashboard metrics tests (no DB) ----

class TestDashboardMetricsNoDB:
    def test_metrics_returns_empty_without_db(self):
        r = client.get("/api/v1/dashboard/metrics", headers=AUTH_HEADER)
        assert r.status_code == 200
        data = r.json()
        assert data["conversations"]["total"] == 0
        assert data["gmv"]["total_rub"] == 0
        assert data["conversion"]["rate_percent"] == 0
        assert data["daily"] == []

    def test_metrics_with_date_filter(self):
        r = client.get(
            "/api/v1/dashboard/metrics",
            params={"date_from": "2026-04-01", "date_to": "2026-04-20"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200

    def test_metrics_with_channel_filter(self):
        r = client.get(
            "/api/v1/dashboard/metrics",
            params={"channel": "telegram"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200


class TestDashboardConversationsNoDB:
    def test_conversations_returns_empty(self):
        r = client.get("/api/v1/dashboard/conversations", headers=AUTH_HEADER)
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_conversations_pagination_params(self):
        r = client.get(
            "/api/v1/dashboard/conversations",
            params={"page": 2, "per_page": 10},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200
        assert r.json()["page"] == 2
        assert r.json()["per_page"] == 10


class TestDashboardEscalationsNoDB:
    def test_escalations_returns_empty(self):
        r = client.get("/api/v1/dashboard/escalations", headers=AUTH_HEADER)
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestDashboardUnansweredNoDB:
    def test_unanswered_returns_empty(self):
        r = client.get("/api/v1/dashboard/unanswered", headers=AUTH_HEADER)
        assert r.status_code == 200
        assert r.json() == []


# ---- Dashboard repository unit tests ----

class TestDashboardRepository:
    def test_empty_metrics_structure(self):
        from app.db.dashboard import DashboardRepository
        repo = DashboardRepository()
        metrics = repo._empty_metrics()
        assert "conversations" in metrics
        assert "conversion" in metrics
        assert "gmv" in metrics
        assert "escalations" in metrics
        assert "channels" in metrics
        assert "daily" in metrics

    def test_get_metrics_no_db(self):
        from app.db.dashboard import DashboardRepository
        repo = DashboardRepository()
        result = repo.get_metrics(date(2026, 4, 1), date(2026, 4, 20))
        assert result["conversations"]["total"] == 0

    def test_get_conversations_no_db(self):
        from app.db.dashboard import DashboardRepository
        repo = DashboardRepository()
        result = repo.get_conversations(date(2026, 4, 1), date(2026, 4, 20))
        assert result["items"] == []

    def test_get_escalations_no_db(self):
        from app.db.dashboard import DashboardRepository
        repo = DashboardRepository()
        result = repo.get_escalations(date(2026, 4, 1), date(2026, 4, 20))
        assert result["items"] == []

    def test_get_unanswered_no_db(self):
        from app.db.dashboard import DashboardRepository
        repo = DashboardRepository()
        result = repo.get_unanswered(date(2026, 4, 1), date(2026, 4, 20))
        assert result == []


# ---- Dashboard models tests ----

class TestDashboardModels:
    def test_dashboard_metrics_model(self):
        from app.models.dashboard import DashboardMetrics
        m = DashboardMetrics(
            conversations={"total": 10, "active": 3, "completed": 5, "escalated": 2},
            conversion={"total_with_payment": 5, "paid": 3, "rate_percent": 30.0},
            gmv={"total_rub": 15000, "avg_check_rub": 5000, "count": 3},
            escalations={"total": 2, "reasons": [{"reason": "test", "count": 2}]},
        )
        assert m.conversations.total == 10
        assert m.gmv.total_rub == 15000

    def test_paginated_conversations_model(self):
        from app.models.dashboard import PaginatedConversations
        p = PaginatedConversations(total=0, page=1, per_page=20)
        assert p.items == []

    def test_unanswered_question_model(self):
        from app.models.dashboard import UnansweredQuestion
        q = UnansweredQuestion(query="test query", count=5)
        assert q.query == "test query"


# ---- Config test ----

class TestDashboardConfig:
    def test_dashboard_api_key_in_settings(self):
        settings = get_settings()
        assert hasattr(settings, "dashboard_api_key")
        assert settings.dashboard_api_key == "test_dashboard_key"


# ---- Tools event tracking integration ----

class TestToolsEventTracking:
    def test_tool_executor_has_events(self):
        from app.agent.tools import ToolExecutor
        executor = ToolExecutor(actor_id="test", conversation_id="conv-1")
        assert hasattr(executor, "events")
        assert executor.events is not None
