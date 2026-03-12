"""Sprint 4 tests: payments, follow-up, product catalog, scheduler, renewal, prompts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("AMOCRM_CLIENT_ID", "test_id")
os.environ.setdefault("AMOCRM_CLIENT_SECRET", "test_secret")
os.environ.setdefault("AMOCRM_SUBDOMAIN", "test")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("EXTERNAL_LINK_SECRET", "test")
os.environ.setdefault("PORTAL_JWT_SECRET", "test")
os.environ.setdefault("SESSION_SIGNING_SECRET", "test")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")

from app.agent.prompt import SALES_SYSTEM_PROMPT, get_system_prompt
from app.agent.tools import (
    SALES_TOOL_DEFINITIONS,
    SUPPORT_TOOL_DEFINITIONS,
    ToolExecutor,
    ToolResult,
    get_tool_definitions,
)
from app.integrations.dms import (
    DMSContact,
    DMSOrder,
    DMSProduct,
    DMSSearchResult,
    DMSStudent,
    MockDMSService,
    ProductCatalog,
)
from app.services.followup import (
    FOLLOWUP_DELAYS,
    FOLLOWUP_TEMPLATES,
    create_followup_chain,
)
from app.services.llm import ToolCallEvent
from app.services.payment import PaymentService


# ===========================================================================
# ProductCatalog
# ===========================================================================

class TestProductCatalog:
    def setup_method(self):
        self.mock_dms = MockDMSService()
        self.catalog = ProductCatalog(self.mock_dms)

    def test_find_exact_match(self):
        """Find product by exact tariff + grade."""
        p = self.catalog.find_product("Экстернат Классный 5 класс", 5)
        assert p is not None
        assert p.grade == 5
        assert "классный" in p.name.lower()

    def test_find_by_tariff_keyword(self):
        """Tariff keyword 'базовый' + grade should match."""
        p = self.catalog.find_product("Базовый 5 класс", 5)
        assert p is not None
        assert "базовый" in p.name.lower()

    def test_wrong_grade_returns_none(self):
        """If no product for this grade, return None."""
        p = self.catalog.find_product("Экстернат Классный 11 класс", 11)
        # Mock has only grade 5 and 7
        assert p is None

    def test_cache_reuse(self):
        """Second call should use cache, not call DMS again."""
        with patch.object(self.mock_dms, "get_products", wraps=self.mock_dms.get_products) as spy:
            self.catalog.find_product("Экстернат Базовый 5 класс", 5)
            self.catalog.find_product("Экстернат Классный 7 класс", 7)
            assert spy.call_count == 1  # only first call fetches

    def test_cache_expires(self):
        """After TTL, cache refreshes."""
        with patch.object(self.mock_dms, "get_products", wraps=self.mock_dms.get_products) as spy:
            self.catalog.find_product("Экстернат Базовый 5 класс", 5)
            # Simulate cache expiry
            self.catalog._cache_time -= self.catalog.CACHE_TTL + 1
            self.catalog.find_product("Экстернат Базовый 5 класс", 5)
            assert spy.call_count == 2


# ===========================================================================
# MockDMSService — payment methods
# ===========================================================================

class TestMockDMSPayments:
    def setup_method(self):
        self.dms = MockDMSService()

    def test_get_products_returns_list(self):
        products = self.dms.get_products()
        assert len(products) >= 3
        assert all(isinstance(p, DMSProduct) for p in products)
        assert all(p.price_kopecks > 0 for p in products)

    def test_create_order_returns_order(self):
        order = self.dms.create_order(1001, [{"product_uuid": "x", "amount": 5000000}])
        assert order is not None
        assert isinstance(order, DMSOrder)
        assert order.order_uuid
        assert order.amount_kopecks == 5000000

    def test_get_payment_link_returns_url(self):
        url = self.dms.get_payment_link("some-uuid")
        assert url is not None
        assert "some-uuid" in url

    def test_get_order_status_returns_draft(self):
        status = self.dms.get_order_status("any-uuid")
        assert status == 0  # mock always returns draft


# ===========================================================================
# PaymentService
# ===========================================================================

class TestPaymentService:
    def setup_method(self):
        self.dms = MockDMSService()
        self.repo = MagicMock()
        self.repo.save_payment_order.return_value = "test-order-id"
        self.repo.save_followup.return_value = None
        self.crm = MagicMock()
        self.svc = PaymentService(dms=self.dms, repo=self.repo, crm=self.crm)

    def test_create_payment_success(self):
        result = self.svc.create_payment(
            actor_id="test-actor",
            conversation_id="test-conv",
            product_name="Экстернат Классный 5 класс",
            grade=5,
            payer_phone="79991234567",
        )
        assert result["success"] is True
        assert result["payment_url"]
        assert result["amount_rub"] > 0
        assert result["product_name"]
        assert result["order_uuid"]
        # Verify DB save was called
        self.repo.save_payment_order.assert_called_once()

    def test_create_payment_product_not_found(self):
        result = self.svc.create_payment(
            actor_id="test-actor",
            conversation_id="test-conv",
            product_name="Несуществующий продукт",
            grade=99,
            payer_phone="79991234567",
        )
        assert result["success"] is False
        assert "не найден" in result["error"]

    def test_create_payment_contact_not_found(self):
        result = self.svc.create_payment(
            actor_id="test-actor",
            conversation_id="test-conv",
            product_name="Экстернат Классный 5 класс",
            grade=5,
            payer_phone="70000000000",  # nonexistent in mock
        )
        assert result["success"] is False
        assert "не найден" in result["error"]

    def test_create_payment_triggers_followup(self):
        """Follow-up chain should be created after successful payment."""
        self.svc.create_payment(
            actor_id="test-actor",
            conversation_id="test-conv",
            product_name="Экстернат Классный 5 класс",
            grade=5,
            payer_phone="79991234567",
        )
        # Follow-up creates 3 steps
        assert self.repo.save_followup.call_count == 3

    def test_create_payment_order_failure(self):
        """If DMS create_order fails, return error."""
        with patch.object(self.dms, "create_order", return_value=None):
            result = self.svc.create_payment(
                actor_id="test-actor",
                conversation_id="test-conv",
                product_name="Экстернат Классный 5 класс",
                grade=5,
                payer_phone="79991234567",
            )
            assert result["success"] is False
            assert "заказ" in result["error"].lower()

    def test_create_payment_link_failure(self):
        """If DMS get_payment_link fails, return error."""
        with patch.object(self.dms, "get_payment_link", return_value=None):
            result = self.svc.create_payment(
                actor_id="test-actor",
                conversation_id="test-conv",
                product_name="Экстернат Классный 5 класс",
                grade=5,
                payer_phone="79991234567",
            )
            assert result["success"] is False
            assert "ссылку" in result["error"].lower()


# ===========================================================================
# ToolResult & ToolCallEvent — payment_data field
# ===========================================================================

class TestPaymentDataField:
    def test_tool_result_has_payment_data(self):
        r = ToolResult(name="test", result="ok", payment_data={"url": "http://pay"})
        assert r.payment_data == {"url": "http://pay"}

    def test_tool_result_payment_data_default_none(self):
        r = ToolResult(name="test", result="ok")
        assert r.payment_data is None

    def test_tool_call_event_has_payment_data(self):
        e = ToolCallEvent(name="test", result="ok", payment_data={"x": 1})
        assert e.payment_data == {"x": 1}

    def test_tool_call_event_payment_data_default_none(self):
        e = ToolCallEvent(name="test", result="ok")
        assert e.payment_data is None


# ===========================================================================
# generate_payment_link tool
# ===========================================================================

class TestGeneratePaymentLinkTool:
    def test_tool_definition_exists(self):
        names = [t["function"]["name"] for t in SALES_TOOL_DEFINITIONS]
        assert "generate_payment_link" in names

    def test_tool_not_in_support(self):
        names = [t["function"]["name"] for t in SUPPORT_TOOL_DEFINITIONS]
        assert "generate_payment_link" not in names

    def test_tool_required_params(self):
        tool = next(t for t in SALES_TOOL_DEFINITIONS if t["function"]["name"] == "generate_payment_link")
        required = tool["function"]["parameters"]["required"]
        assert "product_name" in required
        assert "grade" in required
        assert "payer_phone" in required

    @patch("app.agent.tools.get_dms_service")
    def test_execute_returns_payment_data_on_success(self, mock_get_dms):
        mock_dms = MockDMSService()
        mock_get_dms.return_value = mock_dms

        executor = ToolExecutor(
            actor_id="test-actor",
            conversation_id="test-conv",
        )
        # Override dms and repo
        executor.dms = mock_dms
        executor.repo = MagicMock()
        executor.repo.save_payment_order.return_value = "order-123"
        executor.repo.save_followup.return_value = None

        result = executor.execute("generate_payment_link", {
            "product_name": "Экстернат Классный 5 класс",
            "grade": 5,
            "payer_phone": "79991234567",
        })
        assert result.payment_data is not None
        assert result.payment_data["payment_url"]
        assert result.payment_data["amount_rub"] > 0
        assert result.payment_data["product_name"]
        data = json.loads(result.result)
        assert data["success"] is True

    @patch("app.agent.tools.get_dms_service")
    def test_execute_returns_no_payment_data_on_failure(self, mock_get_dms):
        mock_dms = MockDMSService()
        mock_get_dms.return_value = mock_dms

        executor = ToolExecutor(
            actor_id="test-actor",
            conversation_id="test-conv",
        )
        executor.dms = mock_dms
        executor.repo = MagicMock()

        result = executor.execute("generate_payment_link", {
            "product_name": "Несуществующий",
            "grade": 99,
            "payer_phone": "79991234567",
        })
        assert result.payment_data is None
        data = json.loads(result.result)
        assert data["success"] is False


# ===========================================================================
# Follow-up chain
# ===========================================================================

class TestFollowupChain:
    def test_followup_delays_has_3_steps(self):
        assert len(FOLLOWUP_DELAYS) == 3
        assert 1 in FOLLOWUP_DELAYS
        assert 2 in FOLLOWUP_DELAYS
        assert 3 in FOLLOWUP_DELAYS

    def test_followup_templates_has_3_steps(self):
        assert len(FOLLOWUP_TEMPLATES) == 3
        for step in (1, 2, 3):
            assert "{name}" in FOLLOWUP_TEMPLATES[step]
        # Steps 1 and 3 mention product, step 2 is generic
        assert "{product}" in FOLLOWUP_TEMPLATES[1]
        assert "{product}" in FOLLOWUP_TEMPLATES[3]

    def test_create_followup_chain_saves_3_steps(self):
        repo = MagicMock()
        create_followup_chain(
            repo=repo,
            conversation_id="conv-1",
            actor_id="actor-1",
            payment_order_id="order-1",
        )
        assert repo.save_followup.call_count == 3
        # Verify steps are 1, 2, 3
        steps = [call.kwargs["step"] for call in repo.save_followup.call_args_list]
        assert steps == [1, 2, 3]

    def test_followup_fire_times_increasing(self):
        repo = MagicMock()
        create_followup_chain(
            repo=repo,
            conversation_id="conv-1",
            actor_id="actor-1",
            payment_order_id="order-1",
        )
        fire_times = [call.kwargs["next_fire_at"] for call in repo.save_followup.call_args_list]
        assert fire_times[0] < fire_times[1] < fire_times[2]

    def test_followup_template_formatting(self):
        text = FOLLOWUP_TEMPLATES[1].format(name="Анна", product="Экстернат Классный")
        assert "Анна" in text
        assert "Экстернат Классный" in text


# ===========================================================================
# check_pending_payments
# ===========================================================================

class TestCheckPendingPayments:
    @patch("app.services.payment.AmoCRMClient")
    @patch("app.integrations.dms.get_dms_service")
    @patch("app.services.payment.ConversationRepository")
    def test_paid_order_updates_status(self, MockRepo, mock_get_dms, MockCRM):
        repo = MockRepo.return_value
        repo.get_pending_payments.return_value = [
            {
                "id": "order-1",
                "dms_order_uuid": "uuid-1",
                "conversation_id": "conv-1",
                "amocrm_lead_id": 500,
                "product_name": "Экстернат",
                "amount_kopecks": 5000000,
            }
        ]
        dms = MagicMock()
        dms.get_order_status.return_value = 2  # paid
        mock_get_dms.return_value = dms

        crm = MockCRM.return_value

        from app.services.payment import check_pending_payments
        check_pending_payments()

        repo.update_payment_status.assert_called_once()
        args = repo.update_payment_status.call_args
        assert args[0][1] == "paid"
        # Follow-ups cancelled
        repo.cancel_followups_for_conversation.assert_called_once_with("conv-1")
        # CRM updated
        crm.update_lead.assert_called_once()
        # Confirmation message saved
        repo.save_message.assert_called_once()

    @patch("app.services.payment.AmoCRMClient")
    @patch("app.integrations.dms.get_dms_service")
    @patch("app.services.payment.ConversationRepository")
    def test_unpaid_order_not_updated(self, MockRepo, mock_get_dms, MockCRM):
        repo = MockRepo.return_value
        repo.get_pending_payments.return_value = [
            {
                "id": "order-1",
                "dms_order_uuid": "uuid-1",
                "conversation_id": "conv-1",
            }
        ]
        dms = MagicMock()
        dms.get_order_status.return_value = 0  # still draft
        mock_get_dms.return_value = dms

        from app.services.payment import check_pending_payments
        check_pending_payments()

        repo.update_payment_status.assert_not_called()

    @patch("app.services.payment.AmoCRMClient")
    @patch("app.integrations.dms.get_dms_service")
    @patch("app.services.payment.ConversationRepository")
    def test_no_pending_returns_early(self, MockRepo, mock_get_dms, MockCRM):
        repo = MockRepo.return_value
        repo.get_pending_payments.return_value = []

        from app.services.payment import check_pending_payments
        check_pending_payments()

        mock_get_dms.assert_not_called()  # DMS not even initialized


# ===========================================================================
# process_pending_followups
# ===========================================================================

class TestProcessFollowups:
    @patch("app.services.followup._send_telegram_notification")
    @patch("app.services.followup._escalate_after_followup")
    @patch("app.services.followup.ConversationRepository")
    def test_sends_followup_message(self, MockRepo, mock_escalate, mock_tg):
        repo = MockRepo.return_value
        repo.get_pending_followups.return_value = [
            {
                "id": "f-1",
                "conversation_id": "conv-1",
                "actor_id": "actor-1",
                "step": 1,
                "actor_name": "Анна",
                "product_name": "Экстернат Классный",
                "payment_status": "pending",
            }
        ]
        from app.services.followup import process_pending_followups
        process_pending_followups()

        repo.save_message.assert_called_once()
        msg_text = repo.save_message.call_args.kwargs.get("content") or repo.save_message.call_args[0][2]
        assert "Анна" in msg_text
        repo.update_followup_status.assert_called_once()

    @patch("app.services.followup._send_telegram_notification")
    @patch("app.services.followup._escalate_after_followup")
    @patch("app.services.followup.ConversationRepository")
    def test_skips_paid_followup(self, MockRepo, mock_escalate, mock_tg):
        repo = MockRepo.return_value
        repo.get_pending_followups.return_value = [
            {
                "id": "f-1",
                "conversation_id": "conv-1",
                "actor_id": "actor-1",
                "step": 1,
                "payment_status": "paid",
            }
        ]
        from app.services.followup import process_pending_followups
        process_pending_followups()

        repo.save_message.assert_not_called()
        repo.update_followup_status.assert_called_once_with("f-1", "cancelled")

    @patch("app.services.followup._send_telegram_notification")
    @patch("app.services.followup._escalate_after_followup")
    @patch("app.services.followup.ConversationRepository")
    def test_step3_escalates(self, MockRepo, mock_escalate, mock_tg):
        repo = MockRepo.return_value
        repo.get_pending_followups.return_value = [
            {
                "id": "f-3",
                "conversation_id": "conv-1",
                "actor_id": "actor-1",
                "step": 3,
                "actor_name": "Иван",
                "product_name": "Экстернат",
                "payment_status": "pending",
            }
        ]
        from app.services.followup import process_pending_followups
        process_pending_followups()

        mock_escalate.assert_called_once()


# ===========================================================================
# Scheduler
# ===========================================================================

class TestScheduler:
    def test_scheduler_imports(self):
        from app.services.scheduler import scheduler, start_scheduler, stop_scheduler
        assert scheduler is not None
        assert callable(start_scheduler)
        assert callable(stop_scheduler)

    @patch("app.services.scheduler.scheduler")
    def test_start_adds_two_jobs(self, mock_sched):
        mock_sched.running = False
        from app.services.scheduler import start_scheduler
        start_scheduler()
        assert mock_sched.add_job.call_count == 2
        job_ids = [call.kwargs.get("id") for call in mock_sched.add_job.call_args_list]
        assert "check_payments" in job_ids
        assert "process_followups" in job_ids
        mock_sched.start.assert_called_once()


# ===========================================================================
# Prompt — Sprint 4 sections
# ===========================================================================

class TestSprint4Prompt:
    def test_payment_section_exists(self):
        assert "# ОПЛАТА" in SALES_SYSTEM_PROMPT
        assert "generate_payment_link" in SALES_SYSTEM_PROMPT

    def test_renewal_section_exists(self):
        assert "# ПРОЛОНГАЦИЯ" in SALES_SYSTEM_PROMPT
        assert "NPS" in SALES_SYSTEM_PROMPT

    def test_crosssell_section_exists(self):
        assert "# КРОСС-СЕЙЛ" in SALES_SYSTEM_PROMPT
        assert "Ключи Познания" in SALES_SYSTEM_PROMPT

    def test_followup_section_exists(self):
        assert "# FOLLOW-UP" in SALES_SYSTEM_PROMPT
        assert "24ч" in SALES_SYSTEM_PROMPT

    def test_personal_tariff_no_payment(self):
        """Prompt should say no payment link for Персональный."""
        assert "Персональный" in SALES_SYSTEM_PROMPT
        # Both old and new rules
        assert "менеджер" in SALES_SYSTEM_PROMPT.lower()

    def test_support_prompt_no_payment_tool(self):
        """Support prompt should NOT mention payment tool."""
        from app.agent.prompt import SUPPORT_SYSTEM_PROMPT
        assert "generate_payment_link" not in SUPPORT_SYSTEM_PROMPT

    def test_get_system_prompt_returns_correct_role(self):
        sales = get_system_prompt("sales")
        support = get_system_prompt("support")
        assert "продаж" in sales.lower()
        assert "поддержки" in support.lower()


# ===========================================================================
# Tool definitions — completeness
# ===========================================================================

class TestToolDefinitionsCompleteness:
    def test_sales_tools_count(self):
        """Sprint 4 adds generate_payment_link → total 8."""
        assert len(SALES_TOOL_DEFINITIONS) == 8

    def test_support_tools_count(self):
        """Support should still have 4 tools."""
        assert len(SUPPORT_TOOL_DEFINITIONS) == 4

    def test_get_tool_definitions_dispatches(self):
        assert get_tool_definitions("sales") is SALES_TOOL_DEFINITIONS
        assert get_tool_definitions("support") is SUPPORT_TOOL_DEFINITIONS
        assert get_tool_definitions("unknown") is SALES_TOOL_DEFINITIONS

    def test_all_sales_tools_have_required_fields(self):
        for tool in SALES_TOOL_DEFINITIONS:
            assert "type" in tool
            assert "function" in tool
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func


# ===========================================================================
# Renewal endpoint — model validation
# ===========================================================================

class TestRenewalModel:
    def test_renewal_request_model(self):
        from app.api.renewal import RenewalRequest
        req = RenewalRequest(phone="+79991234567")
        assert req.phone == "+79991234567"
        assert req.actor_id is None

    def test_renewal_response_model(self):
        from app.api.renewal import RenewalResponse
        resp = RenewalResponse(success=True, conversation_id="abc", greeting="Hi")
        assert resp.success is True
        assert resp.conversation_id == "abc"


# ===========================================================================
# Integration: DMS phone normalization (regression)
# ===========================================================================

class TestPhoneNormalization:
    def test_normalize_8_to_7(self):
        from app.integrations.dms import _normalize_phone
        assert _normalize_phone("89991234567") == "79991234567"

    def test_normalize_plus7(self):
        from app.integrations.dms import _normalize_phone
        assert _normalize_phone("+79991234567") == "79991234567"

    def test_format_dms(self):
        from app.integrations.dms import _format_phone_dms
        assert _format_phone_dms("79246724447") == "8 (924) 672-44-47"
