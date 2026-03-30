# Промпты для оркестраторов — PII Proxy + Legal Compliance

> Мастер-план: `/Users/rslazamat/.claude/plans/mellow-yawning-milner.md`
> Каждый промпт — для отдельного чата Claude Code в Cursor.
> После выполнения — отчёт мастер-оркестратору.

---

## Волна 1 — Параллельно (3 чата)

---

### Промпт #1: Фаза 7 — Отключение STT/TTS + клиентская озвучка

```
Ты — оркестратор Фазы 7 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Проект: онлайн-школа EdPalm, ИИ-агент Эврика (3 роли: продавец, поддержка, учитель).
Стек: Python 3.12 + FastAPI (backend), React 19 + Vite (frontend).
Проблема: аудио клиентов отправляется в OpenAI Whisper (STT) и текст ответов — в OpenAI TTS. Это нарушает 152-ФЗ (трансграничная передача ПДн).
Решение: отключить серверные STT/TTS, заменить озвучку на браузерный Web Speech API.

## Задача
1. Добавить config-флаги `STT_ENABLED=false` и `TTS_ENABLED=false` в backend
2. В `speech.py` — early return None когда disabled
3. В API эндпоинтах voice/TTS — возвращать 503 когда disabled
4. В frontend `useTTS.js` — заменить серверный TTS на `window.speechSynthesis` с `lang='ru-RU'`
5. В frontend `VoiceRecorder.jsx` — скрыть/disable кнопку записи голоса

## Файлы для изучения и изменения

**Backend:**
- `eurika/backend/app/config.py` — добавить stt_enabled, tts_enabled (default=False)
- `eurika/backend/app/services/speech.py` — `transcribe()` (строка ~29) и `synthesize()` (строка ~62): early return если disabled
- `eurika/backend/app/api/chat.py` — найти эндпоинты для voice и TTS, добавить 503

**Frontend:**
- `eurika/frontend/src/hooks/useTTS.js` — заменить вызов серверного API на window.speechSynthesis
- `eurika/frontend/src/components/VoiceRecorder.jsx` — disable/скрыть когда STT недоступен
- `eurika/frontend/src/api/client.js` — проверить вызовы synthesizeSpeech

## Важные ограничения
- НЕ удаляй код STT/TTS — только отключай через config. В будущем может быть подключен российский провайдер.
- Озвучка через Web Speech API должна работать для ВСЕХ сообщений ассистента (кнопка "озвучить" рядом с сообщением)
- Если `window.speechSynthesis` недоступен — скрыть кнопку озвучки полностью
- Голос: русский (`ru-RU`), скорость 1.0

## Проверка
1. Установить `STT_ENABLED=false`, `TTS_ENABLED=false` в .env
2. Кнопка записи голоса скрыта/disabled в UI
3. Кнопка озвучки ответа работает через браузер (русский голос)
4. POST на voice/TTS эндпоинты → 503
5. Обычный текстовый чат работает без изменений

## Отчёт
После выполнения напиши отчёт:
- Какие файлы изменены (с номерами строк)
- Что именно изменилось в каждом файле
- Результаты проверки
- Проблемы/решения если были
```

---

### Промпт #2: Фаза 8 — Consent flow

```
Ты — оркестратор Фазы 8 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Проект: онлайн-школа EdPalm, ИИ-агент Эврика.
Стек: Python 3.12 + FastAPI (backend), React 19 + Vite (frontend), PostgreSQL (Supabase).
Проблема: Consent screen нарушает 152-ФЗ:
1. БАГ: опциональные чекбоксы по умолчанию включены (должны быть выключены)
2. Нет согласия на "автоматизированные решения ИИ" (ст. 16 ФЗ-152 — обязательно)
3. Нет обработки несовершеннолетних (ст. 9 ч. 6 ФЗ-152)
4. Нет ссылки на Политику конфиденциальности

## Задача

### 1. Исправить баг дефолтов (ConsentScreen.jsx)
Найти строку где optional consents инициализируются как `true`. Исправить: required → true, optional → false.

### 2. Добавить consent purpose "automated_decisions"
- Создать SQL миграцию `backend/sql/022_consent_v2.sql`:
  - INSERT в `agent_consent_purposes`: id='automated_decisions', required=TRUE
  - UPDATE `crm_sync` SET required=TRUE (передача данных менеджерам — часть core функции)
- Добавить в frontend список purposes

### 3. Итоговая структура согласий:
**Обязательные (3):**
- `data_processing` — "Обработка персональных данных" (уже есть)
- `automated_decisions` — "Автоматизированные решения ИИ" (НОВОЕ) — текст: "Согласие на принятие решений на основе автоматизированной обработки данных ИИ-ассистентом (ст. 16 ФЗ-152). Вы имеете право на информацию о логике принятия решений и на обжалование."
- `crm_sync` — "Передача данных специалистам" (сделать required)

**Опциональные (2, дефолт OFF):**
- `ai_memory` — "Запоминание контекста разговоров"
- `notifications` — "Персонализированные уведомления"

### 4. Обработка несовершеннолетних
- Если из auth контекста (JWT портала) приходит `is_minor: true`:
  - < 14 лет: показать текст "Законный представитель (родитель/опекун) даёт согласие на обработку персональных данных ребёнка"
  - 14-18 лет: показать текст "Подтверждение требуется от ученика И законного представителя"
- Сохранять `is_minor` в consent record

### 5. Ссылка на Политику
- Добавить `<a href="/privacy-policy" target="_blank">Политика конфиденциальности</a>` в consent screen
- Пока URL заглушка — документ будет позже

## Файлы для изучения и изменения

**Frontend:**
- `eurika/frontend/src/components/ConsentScreen.jsx` — основные изменения: дефолты, purposes, minors, ссылка
- `eurika/frontend/src/hooks/useConsent.js` — проверить как consent state передаётся

**Backend:**
- `eurika/backend/sql/017_consent.sql` — ПРОЧИТАТЬ для понимания текущей схемы
- `eurika/backend/sql/022_consent_v2.sql` — СОЗДАТЬ новую миграцию
- `eurika/backend/app/db/consent_repository.py` — проверить, возможно нужно расширить

## Проверка
1. Открыть consent screen как новый пользователь → опциональные чекбоксы OFF
2. Кнопка "Принять" неактивна без data_processing И automated_decisions
3. Появился новый purpose "Автоматизированные решения ИИ"
4. Ссылка "Политика конфиденциальности" видна и кликабельна
5. Для minor-пользователя — специальный текст

## Отчёт
После выполнения напиши отчёт:
- Какие файлы изменены/созданы
- Текст SQL миграции
- Скриншоты/описание UI до и после (если возможно)
- Проблемы/решения
```

---

### Промпт #3: Фаза 9 + Фаза 11 — Маскирование логов + AI-дисклеймер

```
Ты — оркестратор Фаз 9 и 11 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Проект: онлайн-школа EdPalm, ИИ-агент Эврика.
Стек: Python 3.12 + FastAPI (backend), React 19 + Vite (frontend).

**Фаза 9:** ПДн (телефоны, email, имена) попадают в production-логи. Нарушение ст. 19 ФЗ-152.
**Фаза 11:** Нет уведомления пользователя что он общается с ИИ. Требование Кодекса этики ИИ (добровольно сейчас, обязательно с ~2027).

## Задача — Фаза 9: Маскирование логов

### 1. Создать MaskingFilter (logging_config.py)
Добавить в `eurika/backend/app/logging_config.py` класс `MaskingFilter(logging.Filter)`:
- Regex для телефонов: `79241234567` → `7***4567`, `+7 (924) 123-45-67` → `7***4567`, `89241234567` → `8***4567`
- Regex для email: `user@example.com` → `***@***`
- Активен ТОЛЬКО при `APP_ENV=production` (проверить env var)
- Применяется ко ВСЕМ handlers глобально
- Маскирует и `record.msg`, и `record.args` (кортеж аргументов)

### 2. Whitelist tool args (tools.py)
В `eurika/backend/app/agent/tools.py` найти строку где логируется `args` при выполнении инструмента (~строка 560).
Заменить на whitelist:
```python
SAFE_ARG_KEYS = {"query", "product_name", "grade", "amount", "reason", "rating", "tags", "issue", "lead_id", "status_id"}
safe_args = {k: v for k, v in arguments.items() if k in SAFE_ARG_KEYS}
logger.info("Executing tool: %s args=%s", tool_name, safe_args)
```

### 3. Точечные правки (4 места)
- `integrations/dms.py` — найти лог с surname+name при поиске контакта, оставить только contact_id
- `api/chat.py` — найти лог с `text[:80]` или похожий, заменить на `text_len=len(text)`
- Проверить `services/followup.py` и `auth/telegram.py` на логирование ПДн

## Задача — Фаза 11: AI-дисклеймер

### 1. Footer в ChatWindow (frontend)
Добавить серый текст НАД полем ввода сообщения:
```
Эврика — ИИ-ассистент. Ответы могут содержать неточности.
```
Стиль: серый (#6d7487), 11-12px, text-align: center, padding 4px 8px.
Файл: `eurika/frontend/src/components/ChatWindow.jsx` — добавить div перед MessageInput.

### 2. Первое сообщение — дисклеймер (backend)
В `eurika/backend/app/services/chat.py` в функции `generate_greeting()` (~строка 78):
- Проверить: это ПЕРВЫЙ РАЗГОВОР этого actor_id? (query: SELECT COUNT(*) FROM conversations WHERE actor_id = X)
- Если первый → добавить в greeting текст: "Я — ИИ-ассистент Эврика. Помогаю с вопросами об обучении, но не заменяю специалиста. Если нужен человек — скажите."
- Если НЕ первый → обычное приветствие без дисклеймера

### 3. Telegram BotFather (документация)
Задокументировать в отчёте что нужно вручную изменить описание бота:
"ИИ-ассистент онлайн-школы EdPalm. Помогает с вопросами о программах, оплате и учёбе."

## Файлы для изучения и изменения

**Фаза 9 (логи):**
- `eurika/backend/app/logging_config.py` — добавить MaskingFilter
- `eurika/backend/app/agent/tools.py` (~строка 560) — whitelist args
- `eurika/backend/app/integrations/dms.py` — убрать ПДн из логов
- `eurika/backend/app/api/chat.py` — убрать text excerpt из логов
- `eurika/backend/app/config.py` — проверить APP_ENV

**Фаза 11 (дисклеймер):**
- `eurika/frontend/src/components/ChatWindow.jsx` — footer
- `eurika/frontend/src/components/MessageInput.jsx` — возможно footer лучше тут
- `eurika/backend/app/services/chat.py` — greeting с дисклеймером
- `eurika/backend/app/db/repository.py` — метод подсчёта conversations по actor_id

## Проверка

**Фаза 9:**
1. `APP_ENV=production` → запустить бэкенд → выполнить onboarding с телефоном → grep логов на паттерн телефона → 0 совпадений
2. `APP_ENV=development` → логи без маскирования
3. Tool execution log показывает только safe keys

**Фаза 11:**
1. Footer виден на всех экранах чата (mobile и desktop viewport)
2. Первый разговор нового пользователя → дисклеймер в первом сообщении
3. Второй разговор того же пользователя → дисклеймер НЕ повторяется
4. Footer не перекрывает поле ввода на мобильном

## Отчёт
После выполнения напиши отчёт по каждой фазе отдельно:
- Файлы изменены/созданы
- Regex паттерны для маскирования (точные)
- Результаты grep-проверки логов
- Описание UI изменений
- Проблемы/решения
```

---

## Волна 2 — Фундамент

---

### Промпт #4: Фаза 1 — PiiMap core

```
Ты — оркестратор Фазы 1 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Проект: онлайн-школа EdPalm, ИИ-агент Эврика (3 роли: продавец, поддержка, учитель).
Стек: Python 3.12 + FastAPI, PostgreSQL (Supabase).

Мы строим PII-прокси: все персональные данные (имена, телефоны, email, данные детей) заменяются токенами перед отправкой в зарубежный LLM (OpenAI). LLM никогда не видит реальных данных. Бэкенд восстанавливает токены перед показом клиенту.

Эта фаза — ФУНДАМЕНТ. Все остальные фазы PII proxy (2-6) зависят от неё.

## Задача

Создать сервис `PiiMap` — per-actor маппинг реальных ПДн ↔ токены.

### 1. Создать `backend/app/services/pii_proxy.py`

**Класс PiiMap:**
```python
@dataclass
class PiiMap:
    actor_id: str
    tokens: dict[str, str]      # real_value -> token: {"Азамат": "[P]", "+79241234567": "[PH]"}
    reverse: dict[str, str]     # token -> real_value: {"[P]": "Азамат", "[PH]": "+79241234567"}
    _counter: dict[str, int]    # счётчик для автогенерации: {"C": 2, "PH": 1}

    def add(self, real_value: str, token: str) -> None:
        """Добавить маппинг. Если значение уже есть — пропустить."""

    def auto_add(self, real_value: str, token_prefix: str) -> str:
        """Автоматически назначить токен с инкрементом: [C1], [C2], [PH2]..."""

    def tokenize(self, text: str) -> str:
        """Заменить все известные ПДн на токены. Longest-match-first!"""

    def restore(self, text: str) -> str:
        """Заменить все токены на реальные значения."""
```

**Класс PiiMapService:**
```python
class PiiMapService:
    def __init__(self, pool):
        self.pool = pool  # asyncpg connection pool

    async def load_or_create(self, actor_id: str) -> PiiMap:
        """Загрузить из БД или создать пустой."""

    async def persist(self, pii_map: PiiMap) -> None:
        """Сохранить в БД (UPSERT)."""

    async def populate_from_profile(self, pii_map: PiiMap, actor_id: str) -> None:
        """Прочитать agent_user_profiles и добавить все ПДн в карту."""
        # phone -> [PH]
        # fio -> [P]
        # children[0].fio -> [C1], children[0].grade -> [C1_GRADE]
        # children[1].fio -> [C2], children[1].grade -> [C2_GRADE]
        # dms_data.contact.email -> [EMAIL]

    def populate_from_crm(self, pii_map: PiiMap, crm_context: dict) -> None:
        """Добавить CRM-данные: contact_name, contact_id."""
        # contact_name -> [CONTACT_NAME]
        # contact_id -> [CONTACT_ID] (числовой, но всё равно маскируем)

    def extend_from_tool_result(self, pii_map: PiiMap, tool_name: str, result_json: str) -> None:
        """Парсить JSON результат tool call, найти новые ПДн, добавить в карту."""
        # Искать ключи: "fio", "name", "surname", "patronymic", "phone", "email", "telegram_id"
        # Для каждого нового значения — auto_add с подходящим prefix
```

**Функция scan_and_extend (regex):**
```python
def scan_and_extend(pii_map: PiiMap, text: str) -> str:
    """Regex-сканер для ПДн НЕ в карте. Находит телефоны и email, добавляет в карту, возвращает токенизированный текст."""
    # Телефон: +7.../8... в различных форматах
    # Email: стандартный паттерн
    # НЕ ловит имена (NER для русского 65-75%, много false positives)
```

### Требования к tokenize():
- Longest-match-first: сортировать ключи по длине (desc) перед заменой
  - Иначе "Иванов" может быть частично заменён если есть "Иван" → "[P]ов"
- Case-sensitive (русские имена регистрозависимы)
- Не заменять внутри уже вставленных токенов (токены в квадратных скобках)

### Требования к restore():
- Простая замена token → real_value
- Тот же longest-match-first для токенов (на случай [C1] vs [C1_GRADE])

### 2. Создать SQL миграцию `backend/sql/022_pii_maps.sql` (021 занят consent из Фазы 8)

```sql
CREATE TABLE IF NOT EXISTS agent_pii_maps (
    actor_id TEXT PRIMARY KEY,
    token_map JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pii_maps_updated ON agent_pii_maps (updated_at);
```

### 3. Добавить config в `backend/app/config.py`

```python
pii_proxy_enabled: bool = Field(default=False, alias="PII_PROXY_ENABLED")
```

## Файлы для изучения (НЕ изменять, только читать для контекста)
- `eurika/backend/app/db/repository.py` — понять паттерн работы с БД (asyncpg pool)
- `eurika/backend/app/db/pool.py` — как получить pool
- `eurika/backend/app/services/onboarding.py` — как хранится профиль (phone, fio, children, dms_data)
- `eurika/backend/app/models/onboarding.py` — модели данных профиля
- `eurika/backend/app/integrations/dms.py` — формат DMSContact, DMSStudent (что приходит от DMS)
- `eurika/backend/app/integrations/amocrm.py` — формат AmoCRMContact (что приходит от CRM)

## Проверка
1. Unit-тест: `PiiMap.add()` + `tokenize()` + `restore()` = roundtrip
2. Unit-тест: longest-match-first ("Иванов" и "Иван" в одной карте)
3. Unit-тест: `scan_and_extend()` ловит телефоны (+79241234567, 8 924 123-45-67, 8(924)1234567, 89241234567)
4. Unit-тест: `scan_and_extend()` ловит email
5. Unit-тест: `extend_from_tool_result()` парсит JSON и добавляет новые ПДн
6. Unit-тест: `populate_from_profile()` корректно маппит phone, fio, children
7. Integration-тест: persist → load_or_create → проверить что state сохранён
8. Benchmark: tokenize текста 5000 символов с 15 ПДн < 5мс

## Отчёт
После выполнения напиши отчёт:
- Полный код pii_proxy.py (или summary ключевых методов)
- SQL миграция
- Результаты тестов
- Edge cases которые обнаружил и как решил
- Производительность (benchmark)
```

---

## Волна 3 — PII Proxy pipeline

---

### Промпт #5: Фазы 2 + 3 — System prompt + User message токенизация

```
Ты — оркестратор Фаз 2 и 3 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Стек: Python 3.12 + FastAPI, OpenAI GPT-4o, PostgreSQL.

**ЗАВИСИМОСТЬ:** Фаза 1 (PiiMap core) уже реализована. В проекте есть:
- `backend/app/services/pii_proxy.py` — классы PiiMap, PiiMapService, scan_and_extend()
- `backend/sql/022_pii_maps.sql` — таблица agent_pii_maps
- `backend/app/config.py` — `PII_PROXY_ENABLED` env var

## Задача — Фаза 2: Токенизация system prompt

LLM получает 6 блоков контекста с ПДн. Нужно токенизировать каждый.

### Точки перехвата

**1. Identity context** — `llm.py:_identity_context()` (~строка 115-144)
Возвращает строку с name, phone, channel. Применить `pii_map.tokenize()` к результату.

**2. CRM context** — `llm.py:_crm_context()` (~строка 146-161)
Содержит contact_name, contact_id, deal info. Токенизировать.

**3. Profile context** — `onboarding.py:get_profile_context_for_llm()` (~строка 151-186)
Содержит phone, FIO, children [{fio, grade}], DMS data. Токенизировать.

**4. Memory context** — `memory.py:get_memory_context()` (~строка 142-241)
Содержит memory atoms (subject/predicate/object с именами), summaries. Токенизировать.

**5. Running summary** — `chat.py:_get_running_summary()` (~строка 384-455)
Строит диалог из старых сообщений, отправляет в GPT-4o-mini для суммаризации.
Токенизировать диалог ПЕРЕД отправкой. Результат суммаризации тоже токенизировать (он пойдёт в основной LLM-вызов).

**6. History messages** — `llm.py:_build_history_messages()` (~строка 69-111)
До 50 сообщений с полным текстом. На строках 91-101 к assistant-сообщениям добавляются tool call summaries.
Токенизировать content каждого сообщения.

### Реализация

В `chat.py:stream_answer()` (~строка 530, перед вызовом llm.stream_answer()):
```python
from app.config import get_settings
settings = get_settings()
pii_map = None
if settings.pii_proxy_enabled:
    from app.services.pii_proxy import PiiMapService
    pii_svc = PiiMapService(self.repo.pool)
    pii_map = await pii_svc.load_or_create(actor.actor_id)
    await pii_svc.populate_from_profile(pii_map, actor.actor_id)
    if crm_context:
        pii_svc.populate_from_crm(pii_map, crm_context)
    await pii_svc.persist(pii_map)
```

В `llm.py:stream_answer()` — добавить параметр `pii_map: PiiMap | None = None`.
Если pii_map передан → tokenize каждый system message и history message.

### Принцип: БД хранит ОРИГИНАЛ
- `chat_messages` — оригинальные тексты (не токенизированные)
- Токенизация только для копии messages[], отправляемой в OpenAI API

## Задача — Фаза 3: Токенизация user message

В `llm.py:stream_answer()` (~строка 241), где user_text добавляется в messages:
```python
if pii_map:
    from app.services.pii_proxy import scan_and_extend
    user_text_for_llm = scan_and_extend(pii_map, user_text)
else:
    user_text_for_llm = user_text
messages.append({"role": "user", "content": user_text_for_llm})
```

Regex сканер ищет новые телефоны/email в тексте клиента, добавляет в карту, возвращает токенизированный текст.

В БД сохраняется ОРИГИНАЛЬНЫЙ user_text (это происходит раньше, в chat.py).

## Файлы для изменения
- `eurika/backend/app/services/llm.py` — основные изменения: pii_map параметр, tokenize messages
- `eurika/backend/app/services/chat.py` — загрузка PiiMap, передача в llm
- `eurika/backend/app/services/pii_proxy.py` — возможно мелкие доработки

## Файлы для чтения (контекст)
- `eurika/backend/app/services/memory.py` — как строится memory context
- `eurika/backend/app/services/onboarding.py` — как строится profile context
- `eurika/backend/app/agent/prompt.py` — system prompt (роли)

## Проверка
1. `PII_PROXY_ENABLED=true` в .env
2. Начать чат с известным профилем (phone, name, children в БД)
3. Добавить ВРЕМЕННЫЙ debug-лог перед вызовом OpenAI API: `logger.debug("LLM messages: %s", json.dumps(messages, ensure_ascii=False, indent=2))`
4. Проверить что ВСЕ system messages содержат токены вместо реальных данных
5. Отправить сообщение с телефоном → в debug-логе user message содержит токен
6. LLM отвечает связно, используя токены (может сказать "[P], для [C1] подойдёт...")
7. `PII_PROXY_ENABLED=false` → поведение не меняется (backward compatible)
8. УДАЛИТЬ debug-лог после проверки!

## Отчёт
- Какие файлы изменены, какие строки
- Пример токенизированного messages[] (debug output)
- Ответ LLM с токенами (скриншот/текст)
- Backward compatibility подтверждена
```

---

### Промпт #6: Фаза 4 — Tool calls interception

```
Ты — оркестратор Фазы 4 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Стек: Python 3.12 + FastAPI, OpenAI GPT-4o, PostgreSQL.

**ЗАВИСИМОСТИ:** Фазы 1-3 реализованы. PiiMap загружается и передаётся в llm.stream_answer(). System prompt и user messages уже токенизированы.

Теперь LLM "думает" токенами: видит [P], [PH], [C1]. Когда LLM вызывает инструмент — он может передать токены в аргументах: `check_client_history(phone=[PH])`. А результаты инструментов содержат реальные ПДн из CRM/DMS.

## Задача

Двунаправленный PII-прокси для tool execution loop.

### Tool Call Args (LLM → Backend)
LLM передаёт: `{"phone": "[PH]", "telegram_id": "[TG_ID]"}`
Бэкенд ПЕРЕД выполнением: `pii_map.restore()` на всех string-значениях args.
Инструмент получает реальные данные для вызова CRM/DMS API.

### Tool Results (Backend → LLM)
Инструмент возвращает: `{"contact": {"name": "Азамат Расулов", "phone": "+79241234567"}, "students": [{"fio": "Миша Расулов", "grade": 5}]}`
Бэкенд ПОСЛЕ выполнения:
1. `pii_svc.extend_from_tool_result(pii_map, tool_name, result_str)` — парсит JSON, находит новые ПДн (имена учеников, телефоны), добавляет в карту
2. `pii_map.tokenize(result_str)` — заменяет все ПДн на токены
3. Токенизированный результат возвращается в LLM

### Точка перехвата: `llm.py` (~строки 333-360, tool execution loop)

Примерная структура:
```python
# Строка ~336: парсинг аргументов
args = json.loads(tc["arguments"]) if tc["arguments"] else {}

# НОВОЕ: restore токенов в args
if pii_map:
    args = _restore_tool_args(pii_map, args)

# Строка ~340: выполнение
result = tool_executor.execute(tc["name"], args)

# НОВОЕ: extend + tokenize результата
if pii_map:
    pii_svc.extend_from_tool_result(pii_map, tc["name"], result.result)
    tokenized_result = pii_map.tokenize(result.result)
else:
    tokenized_result = result.result

# Строка ~356: добавление в messages
messages.append({
    "role": "tool",
    "tool_call_id": tc["id"],
    "content": tokenized_result,  # Токенизированный для LLM
})

# Строка ~341-344: сохранение для metadata (ОРИГИНАЛ, не токенизированный!)
all_tool_calls_made.append({
    "name": tc["name"],
    "args": args,  # args УЖЕ restored (реальные данные) — ОК для БД
    "result": result.result[:2000],  # Оригинальный результат — ОК для БД
})
```

### Функция _restore_tool_args:
```python
def _restore_tool_args(pii_map: PiiMap, args: dict) -> dict:
    """Рекурсивно заменить токены на реальные значения в аргументах."""
    restored = {}
    for k, v in args.items():
        if isinstance(v, str):
            restored[k] = pii_map.restore(v)
        elif isinstance(v, dict):
            restored[k] = _restore_tool_args(pii_map, v)
        elif isinstance(v, list):
            restored[k] = [pii_map.restore(item) if isinstance(item, str) else item for item in v]
        else:
            restored[k] = v
    return restored
```

### Инструменты с ПДн (19+ штук, ключевые):

| Tool | PII в args | PII в results |
|------|-----------|---------------|
| check_client_history | phone, telegram_id | contact.name, phone, students[].fio |
| get_amocrm_contact | phone, telegram_id | name, phone, telegram_id |
| create_amocrm_lead | name, phone, telegram_id | — |
| get_client_profile | phone | ФИО, email, students[].fio |
| generate_payment_link | student_name, payer_phone | — |
| create_manager_task | client_name, phone, children_details | — |
| create_amocrm_ticket | name, phone, telegram_id | — |
| save_user_name | name | — |

### ВАЖНО: persist PiiMap после extend
После обработки tool results с новыми ПДн — persist обновлённый PiiMap:
```python
if pii_map:
    await pii_svc.persist(pii_map)
```

## Файлы для изменения
- `eurika/backend/app/services/llm.py` (~строки 330-370) — перехват tool args/results
- `eurika/backend/app/services/pii_proxy.py` — возможно доработка extend_from_tool_result

## Файлы для чтения (контекст)
- `eurika/backend/app/agent/tools.py` — все tool definitions и ToolExecutor.execute()
- `eurika/backend/app/integrations/amocrm.py` — формат CRM ответов
- `eurika/backend/app/integrations/dms.py` — формат DMS ответов

## Проверка
1. Начать чат → спросить "расскажи о программах для 5 класса" → агент вызывает search_knowledge_base (без ПДн) → работает без изменений
2. Начать чат с верифицированным профилем → агент вызывает check_client_history(phone=[PH]) → в логе tool executor — реальный телефон → в LLM messages — токенизированный результат
3. get_client_profile возвращает нового ребёнка → PiiMap автоматически расширена → ребёнок виден как [C2]
4. create_amocrm_lead с args [P], [PH] → в CRM создаётся контакт с РЕАЛЬНЫМИ данными
5. В `chat_messages.metadata.tool_calls` — ОРИГИНАЛЬНЫЕ данные (не токенизированные)

## Отчёт
- Изменения в llm.py (diff или описание)
- Пример: tool call args до/после restore
- Пример: tool result до/после tokenize
- Новые ПДн добавленные через extend_from_tool_result
- Edge cases
```

---

### Промпт #7: Фаза 5 — StreamingPiiRestorer

```
Ты — оркестратор Фазы 5 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Стек: Python 3.12 + FastAPI, OpenAI GPT-4o (streaming SSE), React 19.

**ЗАВИСИМОСТИ:** Фазы 1-4 реализованы. LLM получает токенизированный контекст и отвечает с токенами: "Здравствуйте, [P]! Для [C1] в [C1_GRADE] классе подойдёт Экстернат Классный."

Теперь нужно восстановить токены в стриме ответа ПЕРЕД отправкой клиенту через SSE.

## Проблема
LLM стримит ответ по чанкам. Токен `[P]` может быть разрезан:
- Чанк 1: `"Здравствуйте, ["`
- Чанк 2: `"P]! Для "`

Простой string.replace на каждом чанке НЕ сработает — `[` в чанке 1 не является полным токеном.

## Задача

### 1. Создать класс StreamingPiiRestorer в pii_proxy.py

```python
class StreamingPiiRestorer:
    """Буферизированное восстановление PII токенов в стриме. Per-stream instance!"""

    def __init__(self, pii_map: PiiMap):
        self.pii_map = pii_map
        self.buffer = ""
        self.known_tokens = set(pii_map.reverse.keys())
        self.max_token_len = max((len(t) for t in self.known_tokens), default=0)

    def feed(self, chunk: str) -> str:
        """Принять чанк, вернуть текст безопасный для отправки клиенту."""
        # Логика:
        # 1. Добавить chunk в buffer
        # 2. Искать '[' в buffer
        # 3. Если найден — всё ДО '[' безопасно, можно emit
        # 4. Остаток после '[' — проверить:
        #    а) Если полный токен найден ([P], [C1], etc.) → restore, emit
        #    б) Если может быть началом токена (длина < max_token_len) → оставить в буфере
        #    в) Если точно не токен (длина > max_token_len или нет ']') → emit '[' как литерал
        # 5. Если нет '[' — emit всё кроме последних max_token_len-1 символов (на случай что '[' придёт в след. чанке)

    def flush(self) -> str:
        """Вызвать в конце стрима. Сбросить буфер, restore оставшиеся токены."""
        result = self.pii_map.restore(self.buffer)
        self.buffer = ""
        return result
```

### 2. Интегрировать в llm.py streaming

В `llm.py:stream_answer()` (~строки 267-315, streaming секция):

```python
# Инициализация (перед циклом):
if pii_map:
    from app.services.pii_proxy import StreamingPiiRestorer
    pii_restorer = StreamingPiiRestorer(pii_map)
else:
    pii_restorer = None

# В цикле (~строка 283-284):
if delta and delta.content:
    raw_chunk = delta.content
    if pii_restorer:
        restored_chunk = pii_restorer.feed(raw_chunk)
        full_text.append(restored_chunk)  # БД получит ВОССТАНОВЛЕННЫЙ текст
        if restored_chunk:
            yield LLMChunk(token=restored_chunk)
    else:
        full_text.append(raw_chunk)
        yield LLMChunk(token=raw_chunk)

# После цикла (конец стрима, ~строка 307-315):
if pii_restorer:
    remaining = pii_restorer.flush()
    if remaining:
        full_text.append(remaining)
        yield LLMChunk(token=remaining)
```

### 3. Обработать все return paths
В llm.py есть несколько мест где стрим завершается:
- Нормальное завершение (после цикла)
- Tool call завершение (строка ~367-372)
- Ошибка (строка ~374-382)
В каждом случае — вызвать `pii_restorer.flush()` если restorer существует.

## КРИТИЧНО: full_text должен содержать ВОССТАНОВЛЕННЫЙ текст
`full_text` собирается для сохранения в БД как assistant message. БД в РФ → должна содержать реальные данные, не токены. Поэтому `full_text.append(restored_chunk)`, не `raw_chunk`.

## Файлы для изменения
- `eurika/backend/app/services/pii_proxy.py` — добавить StreamingPiiRestorer
- `eurika/backend/app/services/llm.py` — интегрировать в streaming loop

## Проверка
1. Отправить сообщение → LLM отвечает с [P] → клиент видит реальное имя в реальном времени
2. Проверить что стрим не "заикается" (буферизация не создаёт видимых задержек)
3. Edge case: отправить длинное сообщение чтобы LLM упомянул [P], [C1], [C1_GRADE] в одном ответе → все восстановлены
4. Edge case: симулировать разрезанный токен (mock LLM response с чанками "[", "P]") → корректная буферизация
5. В БД (`chat_messages`) — сохранён ВОССТАНОВЛЕННЫЙ текст с реальными именами
6. Performance: стрим не медленнее чем без PII proxy

## Отчёт
- Полный код StreamingPiiRestorer
- Изменения в llm.py
- Результаты edge-case тестов (особенно разрезанные токены)
- Латентность стрима (субъективно: заметна ли задержка?)
```

---

## Волна 4 — Фоновые задачи

---

### Промпт #8: Фаза 6 — Summarizer + Memory embedding

```
Ты — оркестратор Фазы 6 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Стек: Python 3.12 + FastAPI, OpenAI GPT-4o, pgvector, PostgreSQL.

**ЗАВИСИМОСТИ:** Фазы 1-5 реализованы. PII proxy работает для чата. Но есть 3 фоновых процесса которые тоже отправляют ПДн в OpenAI:

1. **Summarizer** — после завершения разговора отправляет ПОЛНЫЙ ДИАЛОГ в GPT-4o для извлечения фактов и саммари. Явно извлекает ПДн: "entity: имя клиента, имя ребёнка, телефон, класс".
2. **Running summary** — в ходе длинного разговора отправляет старые сообщения в GPT-4o-mini.
3. **Memory embeddings** — текст фактов и саммари отправляется в OpenAI Embeddings API.

## Задача

### 1. Summarizer (`summarizer.py`)

В `summarize_conversation()` (~строка 117):
- Загрузить PiiMap для actor_id
- В `_call_summarize_llm()` (~строка 82): токенизировать formatted messages ПЕРЕД отправкой в GPT-4o
- Ответ LLM будет содержать факты с токенами: `{"subject": "[P]", "predicate": "имеет ребёнка", "object": "[C1]"}`
- ВОССТАНОВИТЬ токены в summary_text и facts ПЕРЕД сохранением в БД (БД хранит реальные данные)

### 2. Running summary (`chat.py:_get_running_summary()`)
Уже частично покрыто Фазой 2 (токенизация диалога перед GPT-4o-mini).
Проверить что running summary, возвращённый из GPT-4o-mini, тоже restore-ится перед кешированием в conversation metadata.

### 3. Memory embeddings

**summarizer.py: `_embed_batch()`** (~строка 63-79):
- Текст фактов/саммари → OpenAI Embeddings API
- Токенизировать текст ПЕРЕД embedding
- НО: в БД вектор сохраняется с метаданными. Текст факта в БД — РЕАЛЬНЫЙ (restored).
- Только embedding-вектор создаётся из токенизированного текста.

**memory.py: `_embed_query()`** (~строка 54-75):
- User query → OpenAI Embeddings API (для semantic search по памяти)
- Токенизировать query ПЕРЕД embedding
- Это обеспечивает consistency: если факты эмбеддились с токенами, поиск тоже должен быть с токенами

**rag/search.py: `_embed_query()`** (~строка 32-57):
- RAG query → OpenAI Embeddings API (для поиска по базе знаний)
- База знаний НЕ содержит ПДн (продукты, цены, FAQ) → токенизация необязательна
- НО user query может содержать ПДн ("расскажи про тариф для Миши") → токенизировать

## ВАЖНЫЙ НЮАНС: Переходный период
Существующие memory atoms (~582 шт) были эмбеддированы с РЕАЛЬНЫМИ ПДн. Новые будут эмбеддироваться с ТОКЕНАМИ. Semantic search может не найти старые факты по токенизированному запросу.

**Решение для этой фазы:** Добавить одноразовый скрипт `backend/scripts/reembed_memory.py`:
1. Для каждого actor_id с memory atoms:
   a. Загрузить PiiMap
   b. Для каждого atom: tokenize текст → create embedding → update vector in DB
2. Аналогично для summaries
3. Запускать ОДИН РАЗ после включения PII proxy

## Файлы для изменения
- `eurika/backend/app/services/summarizer.py` — tokenize dialog, restore facts
- `eurika/backend/app/services/chat.py` — verify running summary restore
- `eurika/backend/app/services/memory.py` — tokenize query before embedding
- `eurika/backend/app/rag/search.py` — tokenize query before embedding

## Файлы для создания
- `eurika/backend/scripts/reembed_memory.py` — одноразовый скрипт переэмбеддинга

## Проверка
1. Завершить разговор → триггер суммаризации → debug-лог показывает токенизированный диалог
2. В `agent_conversation_summaries` — реальные имена (не токены)
3. В `agent_memory_atoms` — реальные значения в subject/predicate/object
4. Semantic search по памяти находит факты (проверить `get_memory_context()`)
5. RAG search по KB работает без изменений

## Отчёт
- Изменения в каждом файле
- Пример: до/после токенизации в summarizer
- Результат semantic search (находит ли факты?)
- Скрипт reembed_memory.py (полный код)
```

---

## Волна 5 — Завершение

---

### Промпт #9: Фаза 10 + Фаза 12 — Data deletion + Ad labeling

```
Ты — оркестратор Фаз 10 и 12 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Стек: Python 3.12 + FastAPI, PostgreSQL, amoCRM.

Часть функционала уже реализована: `data_lifecycle.py`, `018_data_requests.sql`, `followup.py`.
Задача — проверить, дополнить, исправить.

## Задача — Фаза 10: Data Deletion + Export

### 1. Grace period: 14 → 30 дней
В `data_lifecycle.py` найти `DELETION_GRACE_DAYS` или аналог → изменить на 30.

### 2. Добавить agent_pii_maps в каскад удаления
В списке таблиц для hard delete добавить `agent_pii_maps`.

### 3. amoCRM обезличивание
После hard delete — PATCH amoCRM contact с пустым именем (если контакт существует и сделка оплачена). Если сделка не оплачена — DELETE contact. Best-effort (не блокирует удаление).

### 4. Проверить scheduler
В `scheduler.py` — есть ли задача `execute_pending_deletions()`? Если нет — добавить (ежедневно в 00:00 UTC).

### 5. Расширить export
В `_build_export()` добавить:
- PII map data (из agent_pii_maps)
- Payment orders (из agent_payment_orders)
- Events (из agent_events, обезличить actor_id)

## Задача — Фаза 12: Follow-up Ad Labeling

### 1. Consent gate
В функции отправки follow-up (в `followup.py`):
- Проверить: есть ли у actor_id consent `notifications`?
- Если нет → НЕ отправлять follow-up, логировать "Follow-up skipped: no marketing consent"
- Если да → продолжить

### 2. Ad labeling для sales role
Для follow-up с role=seller:
- Добавить prefix "Реклама: " к тексту сообщения
- Или добавить в metadata `{"is_ad": true}` чтобы фронтенд показал маркировку

### 3. Service notifications — НЕ реклама
Для support/teacher follow-up и сервисных уведомлений (оплата, аттестация):
- НЕ добавлять "Реклама:"
- Не требуют marketing consent

## Файлы для изменения
- `eurika/backend/app/services/data_lifecycle.py` — grace period, cascade, amoCRM, export
- `eurika/backend/app/services/scheduler.py` — проверить deletion job
- `eurika/backend/app/services/followup.py` — consent check, ad labeling
- `eurika/backend/app/db/consent_repository.py` — метод check_consent()

## Проверка
Фаза 10:
1. Request export → JSON содержит все категории включая PII map и payment orders
2. Request deletion → 30 дней → hard delete → все таблицы очищены (включая agent_pii_maps)
3. consent_log и audit_log сохранены после удаления

Фаза 12:
1. User БЕЗ notifications consent → follow-up НЕ отправлен
2. User С consent, role=seller → follow-up с "Реклама: "
3. Support notification → без "Реклама:", без проверки consent

## Отчёт
- Изменения в каждом файле
- SQL запросы для проверки каскадного удаления
- Пример follow-up с маркировкой
```

---

### Промпт #10: Фаза 13 — Шифрование + HMAC audit log

```
Ты — оркестратор Фазы 13 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
Стек: Python 3.12 + FastAPI, PostgreSQL (Supabase).

Даже при PII proxy, в БД хранятся реальные ПДн (имена, телефоны, данные детей). При утечке бэкапа — все данные в открытом виде. По ст. 19 ФЗ-152 нужны технические меры защиты.

## Задача

### 1. Создать `backend/app/services/crypto.py`

**AES-256-GCM шифрование:**
```python
def encrypt_field(plaintext: str, key: bytes) -> str:
    """Зашифровать строку. Возвращает base64(nonce + ciphertext + tag)."""

def decrypt_field(encrypted: str, key: bytes) -> str:
    """Расшифровать строку."""

def encrypt_json(data: dict | list, key: bytes) -> str:
    """Зашифровать JSON. Сериализует → шифрует."""

def decrypt_json(encrypted: str, key: bytes) -> dict | list:
    """Расшифровать JSON."""
```

**HMAC-SHA256:**
```python
def hmac_sign(data: str, key: bytes) -> str:
    """HMAC-SHA256 подпись для audit log."""

def hmac_verify(data: str, signature: str, key: bytes) -> bool:
    """Проверить подпись."""
```

### 2. SQL миграция `backend/sql/023_encryption_audit.sql`

```sql
CREATE TABLE IF NOT EXISTS agent_llm_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model TEXT NOT NULL,
    request_hash TEXT NOT NULL,       -- HMAC-SHA256 of messages sent
    response_hash TEXT NOT NULL,      -- HMAC-SHA256 of response
    token_count_prompt INT,
    token_count_completion INT,
    tools_used TEXT[],
    pii_proxy_enabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_llm_audit_actor ON agent_llm_audit_log (actor_id, timestamp DESC);
```

### 3. Шифрование ПДн-полей в repository.py

В `save_user_profile()` (~строка 969-1010): зашифровать перед INSERT:
- phone → encrypt_field()
- fio → encrypt_field()
- children → encrypt_json()
- dms_data → encrypt_json()

В `get_user_profile()` (~строка 1020-1044): расшифровать после SELECT.

В save/load для `agent_pii_maps.token_map` → encrypt_json/decrypt_json.

### 4. HMAC audit log в llm.py

После завершения LLM вызова (успешного или с ошибкой) — записать в `agent_llm_audit_log`:
- actor_id
- model (gpt-4o, etc.)
- request_hash: HMAC-SHA256 от сериализованного messages[]
- response_hash: HMAC-SHA256 от полного текста ответа
- token_count (из usage)
- tools_used: список инструментов
- pii_proxy_enabled: bool

### 5. Config
- `PII_ENCRYPTION_KEY` — base64-encoded 32-byte key для AES-256
- `LLM_AUDIT_HMAC_KEY` — base64-encoded key для HMAC

## Файлы для создания
- `backend/app/services/crypto.py`
- `backend/sql/023_encryption_audit.sql`

## Файлы для изменения
- `backend/app/config.py` — pii_encryption_key, llm_audit_hmac_key
- `backend/app/db/repository.py` — encrypt/decrypt в profile methods
- `backend/app/services/llm.py` — audit log write

## Проверка
1. Сохранить профиль → прямой SQL SELECT → phone и fio зашифрованы (base64 blob)
2. Загрузить профиль через API → расшифрованные значения корректны
3. Сделать LLM вызов → запись в audit_log с HMAC
4. Изменить request_hash вручную → hmac_verify() возвращает False
5. Без PII_ENCRYPTION_KEY → приложение отказывается стартовать (или работает без шифрования с warning)

## Отчёт
- crypto.py (полный код)
- SQL миграция
- Пример зашифрованной записи в БД
- Пример audit log записи
- Результаты проверки HMAC
```

---

## Волна 6 — Финал

---

### Промпт #11: Фаза 14 — Интеграционное тестирование

```
Ты — оркестратор Фазы 14 проекта "PII Proxy + Legal Compliance" для ИИ-агента Эврика (EdPalm).

## Контекст
ВСЕ предыдущие фазы (1-13) реализованы. Нужно провести полное интеграционное тестирование.

## Задача

### 1. PII Proxy E2E тест
С `PII_PROXY_ENABLED=true`:
- Создать тестового пользователя с полным профилем (phone, fio, 2 ребёнка)
- Начать чат → отправить сообщение → агент вызывает tools → стрим ответа
- **Проверить:** В OpenAI API (debug log) — 0 реальных ПДн. Только токены.
- **Проверить:** Клиент видит реальные имена в ответе (StreamingPiiRestorer)
- **Проверить:** В БД — реальные данные (не токены)
- **Проверить:** Суммаризация работает с токенизацией
- **Проверить:** Memory search находит факты

### 2. Toggle тест
- С `PII_PROXY_ENABLED=false` — точно такой же сценарий
- Поведение идентично старому (до PII proxy)
- Никаких ошибок

### 3. Consent flow тест
- Новый пользователь → consent screen → опциональные OFF → обязательные → принять
- Revoke marketing consent → follow-up не отправляется
- Revoke ai_memory → memory atoms удаляются

### 4. Data lifecycle тест
- Export → JSON со всеми категориями
- Request deletion → 30 дней → hard delete → все таблицы чисты

### 5. Voice тест
- STT disabled → кнопка скрыта
- TTS → браузерная озвучка работает

### 6. Log masking тест
- APP_ENV=production → grep логов → 0 телефонов/email

### 7. Encryption тест
- Прямой SELECT → encrypted fields
- Через API → decrypted

### 8. Регресс всех 3 ролей
- **Sales:** новый лид → квалификация → подбор → payment link → follow-up
- **Support:** верификация → чек-лист → FAQ → NPS
- **Teacher:** вопрос по предмету → RAG → ответ

## Создать тесты
- `backend/tests/test_pii_proxy.py` — unit + integration
- `backend/tests/test_consent_flow.py`
- `backend/tests/test_log_masking.py`

## Скрипт переэмбеддинга
Запустить `scripts/reembed_memory.py` для переэмбеддинга memory atoms с токенизированным текстом.

## Отчёт
- Результаты каждого тест-сценария (pass/fail)
- Обнаруженные баги и фиксы
- Performance (задержка стрима с PII proxy vs без)
- Рекомендации для production deployment
```
