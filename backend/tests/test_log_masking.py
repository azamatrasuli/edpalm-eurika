"""Tests for log masking (MaskingFilter) — Phase 14."""
import logging
import os
import re


class TestMaskingFilter:

    def _get_filter(self):
        from app.logging_config import MaskingFilter
        return MaskingFilter()

    def test_masks_phone_in_log_record(self):
        f = self._get_filter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Client phone +79241234567 called", args=(), exc_info=None,
        )
        f.filter(record)
        assert "+79241234567" not in record.getMessage()
        assert "***" in record.getMessage() or "7***" in record.getMessage()

    def test_masks_email_in_log_record(self):
        f = self._get_filter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="User email user@example.com found", args=(), exc_info=None,
        )
        f.filter(record)
        assert "user@example.com" not in record.getMessage()

    def test_passes_record_without_pii(self):
        f = self._get_filter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Query completed in 5ms", args=(), exc_info=None,
        )
        original_msg = record.msg
        f.filter(record)
        assert record.msg == original_msg
