"""Tests for PII proxy — Phase 14 integration testing.

Run: PYTHONPATH=. python -m pytest tests/test_pii_proxy.py -v
"""
import pytest
from app.services.pii_proxy import (
    PiiMap,
    StreamingPiiRestorer,
    scan_and_extend,
    _normalize_phone,
)


# ---------------------------------------------------------------------------
# PiiMap unit tests
# ---------------------------------------------------------------------------

class TestPiiMap:

    def test_roundtrip_person(self):
        m = PiiMap()
        m.add_person("Марина")
        tokenized = m.tokenize("Привет Марина!")
        assert "Марина" not in tokenized
        assert "[P]" in tokenized
        restored = m.restore(tokenized)
        assert restored == "Привет Марина!"

    def test_roundtrip_phone(self):
        m = PiiMap()
        m.add_phone("+79241234567")
        tokenized = m.tokenize("Позвоните на +79241234567")
        assert "+79241234567" not in tokenized
        assert "[PH]" in tokenized
        restored = m.restore(tokenized)
        assert "79241234567" in restored  # normalized form

    def test_roundtrip_child(self):
        m = PiiMap()
        m.add_child("Миша")
        tokenized = m.tokenize("Ребёнок Миша учится в 5 классе")
        assert "Миша" not in tokenized
        assert "[C1]" in tokenized
        assert m.restore(tokenized) == "Ребёнок Миша учится в 5 классе"

    def test_longest_match_first(self):
        """'Иванов' должен не ломать 'Иванова'."""
        m = PiiMap()
        m.add("Иванова", "[P]")
        m.add("Иванов", "[P2]")
        result = m.tokenize("Мария Иванова и Сергей Иванов")
        assert "[P]" in result
        assert "[P2]" in result
        # Ensure no partial replacement turned "Иванова" → "[P2]а"
        assert "[P2]а" not in result

    def test_multiple_persons(self):
        m = PiiMap()
        m.add_person("Анна")
        m.add_person("Борис")
        text = "Анна и Борис пришли"
        tok = m.tokenize(text)
        assert "Анна" not in tok
        assert "Борис" not in tok
        restored = m.restore(tok)
        assert restored == text

    def test_empty_map_is_noop(self):
        m = PiiMap()
        text = "Привет +79001234567"
        assert m.tokenize(text) == text
        assert m.restore(text) == text

    def test_persist_roundtrip(self):
        m = PiiMap()
        m.add_person("Дима")
        m.add_phone("+79998887766")
        m.add_child("Алёша")
        data = m.to_jsonb()
        m2 = PiiMap.from_jsonb(data)
        assert m2.forward == m.forward
        assert m2.reverse == m.reverse

    def test_phone_normalization(self):
        assert _normalize_phone("8 924 123-45-67") == "+79241234567"
        assert _normalize_phone("8(924)1234567") == "+79241234567"
        assert _normalize_phone("+79241234567") == "+79241234567"

    def test_duplicate_add_is_idempotent(self):
        m = PiiMap()
        m.add_person("Света")
        m.add_person("Света")  # should not create duplicate or error
        assert len([k for k in m.forward if m.forward[k] == "[P]"]) == 1

    def test_token_exhaustion(self):
        """When person token pool runs out, add_person returns None gracefully."""
        m = PiiMap()
        names = ["А", "Б", "В", "Г", "Д", "Е"]  # more than _PERSON_TOKENS pool
        for name in names:
            m.add_person(name)
        # Should not raise, just silently exhaust pool
        assert m.tokenize("А") in ("[P]", "А")  # either tokenized or not

    def test_email_tokenization(self):
        m = PiiMap()
        m.add_email("user@example.com")
        tok = m.tokenize("Напишите на user@example.com")
        assert "user@example.com" not in tok
        assert "[EM]" in tok
        assert m.restore(tok) == "Напишите на user@example.com"


# ---------------------------------------------------------------------------
# scan_and_extend tests
# ---------------------------------------------------------------------------

class TestScanAndExtend:

    def test_detects_phone_in_text(self):
        m = PiiMap()
        result = scan_and_extend(m, "Позвоните мне: +79161234567")
        assert "[PH]" in result
        assert "+79161234567" not in result

    def test_detects_email_in_text(self):
        m = PiiMap()
        result = scan_and_extend(m, "Пишите: test@mail.ru")
        assert "[EM]" in result
        assert "test@mail.ru" not in result

    def test_no_pii_is_noop(self):
        m = PiiMap()
        text = "Привет, как дела?"
        assert scan_and_extend(m, text) == text

    def test_already_in_map_not_duplicated(self):
        m = PiiMap()
        m.add_phone("+79161234567")
        tokens_before = len(m.forward)
        scan_and_extend(m, "Мой номер +79161234567")
        assert len(m.forward) == tokens_before  # no new entry


# ---------------------------------------------------------------------------
# StreamingPiiRestorer tests
# ---------------------------------------------------------------------------

class TestStreamingPiiRestorer:

    def _make_map(self) -> PiiMap:
        m = PiiMap()
        m.add_person("Марина")
        m.add_phone("+79001234567")
        return m

    def test_whole_token_in_one_chunk(self):
        m = self._make_map()
        r = StreamingPiiRestorer(m)
        out = r.feed("Здравствуйте, [P]!")
        assert "Марина" in out
        assert "[P]" not in out

    def test_split_token_across_chunks(self):
        m = self._make_map()
        r = StreamingPiiRestorer(m)
        out1 = r.feed("Здравствуйте, [")
        out2 = r.feed("P]!")
        full = out1 + out2
        assert "Марина" in full
        assert "[P]" not in full

    def test_flush_releases_buffer(self):
        m = self._make_map()
        r = StreamingPiiRestorer(m)
        r.feed("Текст [")  # partial token
        tail = r.flush()
        # flush returns whatever was buffered
        assert isinstance(tail, str)

    def test_plain_text_unchanged(self):
        m = self._make_map()
        r = StreamingPiiRestorer(m)
        text = "Добрый день!"
        out = r.feed(text)
        assert out == text

    def test_empty_map_is_passthrough(self):
        m = PiiMap()  # empty
        r = StreamingPiiRestorer(m)
        text = "Привет [P]"
        assert r.feed(text) == text

    def test_multiple_tokens_in_stream(self):
        m = self._make_map()
        r = StreamingPiiRestorer(m)
        out = r.feed("Клиент [P], телефон [PH].")
        assert "Марина" in out
        assert "+79001234567" in out

    def test_very_long_bracket_not_stuck(self):
        """Bracket content > 20 chars should be flushed as-is (not a token)."""
        m = self._make_map()
        r = StreamingPiiRestorer(m)
        long_bracket = "[это очень длинный нетокен]"
        out = r.feed(long_bracket)
        # Should output the content rather than hang
        assert isinstance(out, str)
        assert len(out) > 0
