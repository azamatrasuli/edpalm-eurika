"""PII Proxy service — 152-ФЗ compliance.

Токенизирует ПДн перед отправкой в LLM и восстанавливает токены в ответе.
БД хранит оригинальные данные; токены существуют только в процессе LLM-вызова.

Архитектура:
  PiiMap           — двунаправленный маппинг ПДн ↔ токены (per-actor)
  PiiMapService    — загрузка/сохранение PiiMap из БД, populate из профиля/CRM
  scan_and_extend  — regex-сканер: ищет новые ПДн в тексте, расширяет карту
  StreamingPiiRestorer — буферизация токенов в SSE-стриме (per-stream instance)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("pii_proxy")

# ---------------------------------------------------------------------------
# Regex patterns для ПДн, которые могут прийти без предварительного маппинга
# ---------------------------------------------------------------------------

_PHONE_PATTERNS = [
    # +7 (924) 123-45-67 / +79241234567 / 8 924 123-45-67 / 8(924)1234567
    re.compile(r"(?:\+7|8)[\s\-\(]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"),
]
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


# ---------------------------------------------------------------------------
# Token allocators
# ---------------------------------------------------------------------------

_PERSON_TOKENS = ["[P]", "[P2]", "[P3]", "[P4]", "[P5]"]
_PHONE_TOKENS  = ["[PH]", "[PH2]", "[PH3]", "[PH4]", "[PH5]"]
_CHILD_TOKENS  = ["[C1]", "[C2]", "[C3]", "[C4]", "[C5]", "[C6]", "[C7]", "[C8]"]
_EMAIL_TOKENS  = ["[EM]", "[EM2]", "[EM3]"]
_CONTACT_TOKENS = [f"[NEW_CONTACT_{i}]" for i in range(1, 10)]


def _next_free(pool: list[str], used: set[str]) -> str | None:
    for t in pool:
        if t not in used:
            return t
    return None


# ---------------------------------------------------------------------------
# PiiMap
# ---------------------------------------------------------------------------

@dataclass
class PiiMap:
    """Двунаправленный маппинг: pii_value → token, token → pii_value."""

    # pii → token (для tokenize)
    forward: dict[str, str] = field(default_factory=dict)
    # token → pii (для restore)
    reverse: dict[str, str] = field(default_factory=dict)

    # ---- populate helpers -------------------------------------------------

    def add(self, pii_value: str, token: str) -> None:
        if not pii_value or not token:
            return
        if pii_value in self.forward:
            return  # already mapped
        self.forward[pii_value] = token
        self.reverse[token] = pii_value

    def _used_tokens(self) -> set[str]:
        return set(self.reverse.keys())

    def add_person(self, name: str) -> str | None:
        if name in self.forward:
            return self.forward[name]
        t = _next_free(_PERSON_TOKENS, self._used_tokens())
        if t:
            self.add(name, t)
        return t

    def add_phone(self, phone: str) -> str | None:
        normalized = _normalize_phone(phone)
        if normalized in self.forward:
            return self.forward[normalized]
        # Try original too
        if phone in self.forward:
            return self.forward[phone]
        t = _next_free(_PHONE_TOKENS, self._used_tokens())
        if t:
            self.add(normalized, t)
            if phone != normalized:
                self.add(phone, t)
        return t

    def add_child(self, name: str) -> str | None:
        if name in self.forward:
            return self.forward[name]
        t = _next_free(_CHILD_TOKENS, self._used_tokens())
        if t:
            self.add(name, t)
        return t

    def add_email(self, email: str) -> str | None:
        if email in self.forward:
            return self.forward[email]
        t = _next_free(_EMAIL_TOKENS, self._used_tokens())
        if t:
            self.add(email, t)
        return t

    def add_new_contact(self, value: str) -> str | None:
        if value in self.forward:
            return self.forward[value]
        t = _next_free(_CONTACT_TOKENS, self._used_tokens())
        if t:
            self.add(value, t)
        return t

    # ---- tokenize / restore -----------------------------------------------

    def tokenize(self, text: str) -> str:
        """Заменяет все ПДн в тексте токенами. Longest-match-first."""
        if not text or not self.forward:
            return text
        # Sort by length descending so "Иванов" не ломает "Иванова"
        sorted_keys = sorted(self.forward.keys(), key=len, reverse=True)
        result = text
        for key in sorted_keys:
            if key in result:
                result = result.replace(key, self.forward[key])
        return result

    def restore(self, text: str) -> str:
        """Восстанавливает токены в оригинальные ПДн."""
        if not text or not self.reverse:
            return text
        result = text
        for token, pii in self.reverse.items():
            if token in result:
                result = result.replace(token, pii)
        return result

    # ---- serialization ----------------------------------------------------

    def to_jsonb(self) -> dict[str, str]:
        """Для хранения в agent_pii_maps.token_map."""
        return dict(self.forward)

    @classmethod
    def from_jsonb(cls, data: dict[str, str]) -> "PiiMap":
        m = cls()
        for pii, token in data.items():
            m.add(pii, token)
        return m

    def is_empty(self) -> bool:
        return not self.forward


# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------

def _normalize_phone(phone: str) -> str:
    """Normalize to +7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits[0] == "7":
        return "+" + digits
    return phone  # return as-is if unrecognized


# ---------------------------------------------------------------------------
# scan_and_extend — regex scanner
# ---------------------------------------------------------------------------

def scan_and_extend(pii_map: PiiMap, text: str) -> str:
    """Find PII in text not yet in pii_map, add them, return tokenized text.

    Используется для user messages — клиент мог написать телефон/email,
    которого нет в профиле.
    """
    # Phones
    for pattern in _PHONE_PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group(0).strip()
            normalized = _normalize_phone(raw)
            if normalized not in pii_map.forward and raw not in pii_map.forward:
                pii_map.add_phone(raw)
                logger.debug("scan_and_extend: found phone %s → %s", raw, pii_map.forward.get(normalized, "?"))

    # Emails
    for m in _EMAIL_PATTERN.finditer(text):
        email = m.group(0).strip()
        if email not in pii_map.forward:
            pii_map.add_email(email)
            logger.debug("scan_and_extend: found email %s → %s", email, pii_map.forward.get(email, "?"))

    return pii_map.tokenize(text)


def tokenize_for_embedding(text: str, actor_id: str | None = None) -> str:
    """Quick PII tokenization for embedding calls.

    Loads existing PiiMap from DB (if actor_id available) + regex scan.
    If PII proxy is disabled or fails, returns text as-is.
    """
    from app.config import get_settings
    if not get_settings().pii_proxy_enabled:
        return text
    if not actor_id:
        pii_map = PiiMap()
        return scan_and_extend(pii_map, text)
    try:
        svc = PiiMapService()
        pii_map = svc.load(actor_id)
        return scan_and_extend(pii_map, text)
    except Exception:
        logger.debug("tokenize_for_embedding fallback to regex-only", exc_info=True)
        pii_map = PiiMap()
        return scan_and_extend(pii_map, text)


# ---------------------------------------------------------------------------
# PiiMapService — БД хранение и populate
# ---------------------------------------------------------------------------

class PiiMapService:
    """Loads/saves PiiMap from agent_pii_maps table.

    Falls back to empty map if DB is unavailable.
    """

    def load(self, actor_id: str) -> PiiMap:
        try:
            from app.db.pool import get_connection, has_pool
            if not has_pool():
                return PiiMap()
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT token_map FROM agent_pii_maps WHERE actor_id = %s",
                        (actor_id,),
                    )
                    row = cur.fetchone()
                    if row and row["token_map"]:
                        data = row["token_map"] if isinstance(row["token_map"], dict) else json.loads(row["token_map"])
                        return PiiMap.from_jsonb(data)
            return PiiMap()
        except Exception:
            logger.warning("PiiMapService.load failed for actor=%s", actor_id, exc_info=True)
            return PiiMap()

    def save(self, actor_id: str, pii_map: PiiMap) -> None:
        try:
            from app.db.pool import get_connection, has_pool
            from psycopg.types.json import Json
            if not has_pool():
                return
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_pii_maps (actor_id, token_map, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (actor_id) DO UPDATE
                            SET token_map  = EXCLUDED.token_map,
                                updated_at = NOW()
                        """,
                        (actor_id, Json(pii_map.to_jsonb())),
                    )
                conn.commit()
        except Exception:
            logger.warning("PiiMapService.save failed for actor=%s", actor_id, exc_info=True)

    def populate_from_profile(self, pii_map: PiiMap, actor_id: str) -> None:
        """Читает agent_user_profiles и заполняет карту ПДн."""
        try:
            from app.services.onboarding import OnboardingService
            profile = OnboardingService().check_profile(actor_id)
            if not profile:
                return
            # phone
            phone = None
            if hasattr(profile, "phone"):
                phone = profile.phone
            elif isinstance(profile, dict):
                phone = profile.get("phone")
            if phone:
                pii_map.add_phone(phone)

            # fio / display_name
            for attr in ("fio", "display_name", "name"):
                name = getattr(profile, attr, None) or (profile.get(attr) if isinstance(profile, dict) else None)
                if name:
                    pii_map.add_person(name)
                    break

            # children
            children = getattr(profile, "children", None) or (profile.get("children") if isinstance(profile, dict) else None)
            if children and isinstance(children, list):
                for child in children:
                    child_fio = None
                    if isinstance(child, dict):
                        child_fio = child.get("fio") or child.get("name")
                    elif hasattr(child, "fio"):
                        child_fio = child.fio
                    if child_fio:
                        pii_map.add_child(child_fio)
        except Exception:
            logger.warning("populate_from_profile failed for actor=%s", actor_id, exc_info=True)

    def populate_from_actor(self, pii_map: PiiMap, actor: Any) -> None:
        """Заполняет карту из ActorContext (phone, display_name)."""
        try:
            if hasattr(actor, "phone") and actor.phone:
                pii_map.add_phone(actor.phone)
            if hasattr(actor, "display_name") and actor.display_name:
                pii_map.add_person(actor.display_name)
        except Exception:
            logger.warning("populate_from_actor failed", exc_info=True)

    def populate_from_crm(self, pii_map: PiiMap, crm_data: dict | None) -> None:
        """Заполняет карту из CRM-контекста."""
        if not crm_data:
            return
        try:
            if crm_data.get("contact_name"):
                pii_map.add_person(crm_data["contact_name"])
            if crm_data.get("contact_phone"):
                pii_map.add_phone(crm_data["contact_phone"])
            if crm_data.get("telegram_id"):
                # telegram_id — числовой идентификатор, не передаём как ПДн напрямую
                pass
        except Exception:
            logger.warning("populate_from_crm failed", exc_info=True)

    def extend_from_tool_result(self, pii_map: PiiMap, tool_name: str, result_json: str) -> None:
        """Парсит JSON результат инструмента, ищет поля с ПДн, добавляет в карту."""
        try:
            data = json.loads(result_json)
        except Exception:
            return
        self._extract_pii_from_value(pii_map, data)

    def _extract_pii_from_value(self, pii_map: PiiMap, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if k in ("fio", "name", "contact_name", "full_name", "student_name", "payer_name"):
                    if isinstance(v, str) and v:
                        pii_map.add_person(v)
                elif k in ("phone", "contact_phone", "payer_phone", "mobile"):
                    if isinstance(v, str) and v:
                        pii_map.add_phone(v)
                elif k in ("email",):
                    if isinstance(v, str) and v:
                        pii_map.add_email(v)
                elif k == "students" and isinstance(v, list):
                    for s in v:
                        self._extract_pii_from_value(pii_map, s)
                elif k == "children" and isinstance(v, list):
                    for c in v:
                        self._extract_pii_from_value(pii_map, c)
                elif isinstance(v, (dict, list)):
                    self._extract_pii_from_value(pii_map, v)
        elif isinstance(value, list):
            for item in value:
                self._extract_pii_from_value(pii_map, item)

    def build_for_actor(self, actor: Any, crm_data: dict | None = None) -> PiiMap:
        """Полная инициализация карты: load + populate."""
        actor_id = actor.actor_id if hasattr(actor, "actor_id") else str(actor)
        pii_map = self.load(actor_id)
        self.populate_from_actor(pii_map, actor)
        self.populate_from_profile(pii_map, actor_id)
        if crm_data:
            self.populate_from_crm(pii_map, crm_data)
        return pii_map


# ---------------------------------------------------------------------------
# StreamingPiiRestorer — per-stream, буферизует разрезанные токены
# ---------------------------------------------------------------------------

class StreamingPiiRestorer:
    """Восстанавливает токены в стриме SSE.

    Токены приходят разрезанными по чанкам: "[P" / "]" в разных чанках.
    Буферизируем подозрительные фрагменты, восстанавливаем при завершении.

    Создавать per-stream instance, не переиспользовать между стримами.
    """

    def __init__(self, pii_map: PiiMap) -> None:
        self.pii_map = pii_map
        self._buf = ""
        self._in_bracket = False

    def feed(self, chunk: str) -> str:
        """Feed a chunk, returns output safe to yield to client."""
        if not chunk:
            return ""
        if self.pii_map.is_empty():
            return chunk

        output_parts: list[str] = []
        for char in chunk:
            if char == "[" and not self._in_bracket:
                self._in_bracket = True
                self._buf = "["
            elif self._in_bracket:
                self._buf += char
                if char == "]":
                    self._in_bracket = False
                    restored = self.pii_map.restore(self._buf)
                    output_parts.append(restored)
                    self._buf = ""
                elif len(self._buf) > 20:
                    # Too long — not a token, flush as-is
                    output_parts.append(self._buf)
                    self._buf = ""
                    self._in_bracket = False
            else:
                output_parts.append(char)

        return "".join(output_parts)

    def flush(self) -> str:
        """Call at end of stream to release any buffered content."""
        remaining = self._buf
        self._buf = ""
        self._in_bracket = False
        if remaining:
            return self.pii_map.restore(remaining)
        return ""
