"""Pydantic models for dashboard API responses."""

from __future__ import annotations

from pydantic import BaseModel


class ConversationMetrics(BaseModel):
    total: int = 0
    active: int = 0
    completed: int = 0
    escalated: int = 0


class ConversionMetrics(BaseModel):
    total_with_payment: int = 0
    paid: int = 0
    rate_percent: float = 0


class GmvMetrics(BaseModel):
    total_rub: float = 0
    avg_check_rub: float = 0
    count: int = 0


class EscalationReason(BaseModel):
    reason: str
    count: int


class EscalationMetrics(BaseModel):
    total: int = 0
    reasons: list[EscalationReason] = []


class DailyEntry(BaseModel):
    date: str
    conversations: int = 0
    gmv_rub: float = 0


class DashboardMetrics(BaseModel):
    conversations: ConversationMetrics
    conversion: ConversionMetrics
    gmv: GmvMetrics
    escalations: EscalationMetrics
    channels: dict[str, int] = {}
    daily: list[DailyEntry] = []


class ConversationSummary(BaseModel):
    id: str
    actor_id: str
    channel: str | None = None
    agent_role: str = "sales"
    status: str | None = None
    display_name: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    message_count: int = 0
    has_payment: bool = False
    payment_status: str | None = None


class PaginatedConversations(BaseModel):
    items: list[ConversationSummary] = []
    total: int = 0
    page: int = 1
    per_page: int = 20


class EscalationEntry(BaseModel):
    id: str
    conversation_id: str | None = None
    actor_id: str
    channel: str | None = None
    reason: str | None = None
    created_at: str | None = None


class PaginatedEscalations(BaseModel):
    items: list[EscalationEntry] = []
    total: int = 0
    page: int = 1
    per_page: int = 20


class UnansweredQuestion(BaseModel):
    query: str
    count: int
    last_seen: str | None = None
