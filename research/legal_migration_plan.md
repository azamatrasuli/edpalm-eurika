# План миграции на законодательно-безопасный стек

> Дата: 2026-03-24 | Версия: 1.0
> Контекст: технические решения для соответствия законодательству РФ

---

## Текущий стек → Целевой стек

| Компонент | Сейчас | Проблема | Целевой | Статус |
|-----------|--------|----------|---------|--------|
| **БД** | Supabase (AWS Сидней) | Локализация ПДн | PostgreSQL на своём сервере РФ | Решено (по словам заказчика) |
| **Бэкенд** | Render.com (США) | Обработка ПДн вне РФ | Свой сервер РФ | Решено (по словам заказчика) |
| **Фронтенд** | Vercel (США) | Хостинг вне РФ + блокировки | Российский хостинг | Решено (по словам заказчика) |
| **LLM** | OpenAI GPT-4o | Незаконная передача ПДн в США | YandexGPT 5.1 Pro | Нужна миграция |
| **STT** | OpenAI Whisper | Аудио с ПДн в США | Yandex SpeechKit STT | Нужна миграция |
| **TTS** | OpenAI TTS (nova) | Текст с ПДн в США | Yandex SpeechKit TTS | Нужна миграция |
| **Embeddings** | OpenAI text-embedding-3-small (1536d) | Запросы с ПДн в США | YandexGPT embeddings (256d) или Giga-Embeddings (2048d, self-hosted) | Нужна миграция |
| **RAG** | pgvector + custom loader | Чисто (нет ПДн в чанках) | Оставить pgvector | Без изменений |
| **CRM** | amoCRM | Серверы в РФ, ОК | amoCRM | Без изменений |
| **DMS** | proxy.hss.center | Серверы в РФ, ОК | DMS | Без изменений |

---

## Детальный план по каждому компоненту

### 1. LLM: OpenAI GPT-4o → YandexGPT 5.1 Pro

**Почему YandexGPT:**
- Серверы в РФ, сертификация УЗ-1 (152-ФЗ)
- OpenAI-совместимый API (минимальные изменения в коде)
- Function calling поддерживается (бета)
- Streaming (SSE) поддерживается
- Цена: 800 руб./1 млн токенов (~$8 — дешевле GPT-4o)
- Можно легально отправлять ПДн (при оформлении DPA)

**Что меняется в коде:**

Файл `app/config.py`:
```
# Было:
OPENAI_API_KEY, OPENAI_MODEL = "gpt-4o"

# Станет:
YANDEX_API_KEY, YANDEX_FOLDER_ID
LLM_BASE_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1"
LLM_MODEL = "yandexgpt/latest" или "yandexgpt-5/latest"
```

Файл `app/services/llm.py`:
- Замена `OpenAI(api_key=...)` → `OpenAI(api_key=yandex_key, base_url=yandex_url)`
- Формат function calling может отличаться — нужна адаптация
- Streaming формат совместим

Файл `app/services/summarizer.py`:
- Аналогичная замена клиента

Файл `app/services/memory.py`:
- Замена OpenAI embeddings → YandexGPT embeddings
- ВАЖНО: размерность 256 вместо 1536 — нужна пересоздание таблицы knowledge_chunks и memory_atoms

**Изменения для пользователя:**
- Качество ответов на русском — сопоставимое или лучше (YandexGPT оптимизирован для русского)
- Скорость ответа — сопоставимая
- Function calling может быть менее надёжным (бета) — нужно тестирование
- Пользователь не заметит разницы в интерфейсе

**Риски:**
- Function calling в YandexGPT — бета, нужно тестирование на конкретных сценариях
- Embeddings 256d — возможна потеря качества RAG-поиска (но Яндекс оптимизирован для русского)

**Альтернатива: GigaChat-2-Max**
- 128K контекст (как GPT-4o)
- Function calling (но только 1 вызов за запрос — ограничение)
- Нативный API не OpenAI-совместимый (нужен адаптер gpt2giga)
- Для EdPalm: ограничение "1 function call за раз" — проблема, т.к. агент часто вызывает несколько инструментов

**Альтернатива: Self-hosted T-pro 2.0 (32B)**
- Превосходит GPT-4o на русских бенчмарках
- Apache 2.0 лицензия, бесплатно
- НО: нет обучения на function calling — потребуется дообучение или обёртка
- Требует GPU-сервер (A100 80GB или 2× A100 40GB)

**Рекомендация:** YandexGPT 5.1 Pro как основной, GigaChat-2-Max как fallback

---

### 2. STT: OpenAI Whisper → Yandex SpeechKit

**Что меняется в коде:**

Файл `app/services/speech.py`:
```python
# Было:
response = self.client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_bytes,
    language="ru",
)

# Станет:
# Yandex SpeechKit STT (streaming или async)
import grpc
from yandex.cloud.ai.stt.v3 import stt_service_pb2_grpc, stt_pb2
# или REST API: POST https://stt.api.cloud.yandex.net/speech/v1/stt:recognize
```

**Цена:** ~0.65 руб./мин (дешевле Whisper)

**Изменения для пользователя:**
- Качество распознавания русской речи — на уровне или лучше Whisper
- Streaming распознавание — промежуточные результаты (UX-улучшение!)
- Нет изменений в интерфейсе

---

### 3. TTS: OpenAI TTS → Yandex SpeechKit

**Что меняется в коде:**

Файл `app/services/speech.py`:
```python
# Было:
response = self.client.audio.speech.create(
    model="tts-1", voice="nova", input=text
)

# Станет:
# Yandex SpeechKit TTS
# POST https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize
# voice = "alena" (женский, подходит для Эврики)
```

**Голоса:** Алёна, Филипп, Ермил, Захар и др. Алёна — наиболее близка к текущему "nova"

**Изменения для пользователя:**
- Голос изменится (другой тембр, но качественный русский)
- SSML-поддержка — лучшая интонация

---

### 4. Embeddings: OpenAI → YandexGPT embeddings

**Решение: YandexGPT embeddings (256d, облако)**
- Серверы в РФ → ФЗ-152 соблюдён
- Две модели: `text-search-doc` (индексация) и `text-search-query` (поиск) — правильная пара
- API: `POST https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding`
- Не OpenAI-совместимый формат — нужна отдельная обёртка
- Дёшево: оплата в юнитах векторизации, для 746 чанков — копейки
- 256d достаточно для структурированного русскоязычного контента (FAQ, цены, возражения)

**Self-hosted (Giga-Embeddings) — отклонено:**
- Нужен GPU-сервер: оверинжиниринг для текущего масштаба
- Экономия минимальная (единицы рублей в месяц)

**Что содержит KB (текст НЕ теряется):**
- MD-файлы на диске: `seller_staff/knowledge_base/`, `support_staff/knowledge_base/`
- Текст также в колонке `content` таблицы `knowledge_chunks`
- При миграции: берём текст из тех же источников, генерим новые векторы через Яндекс

**Миграция:**
1. `ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(256)` (и аналогично для memory_atoms, summaries)
2. Пересоздать HNSW-индекс под новую размерность
3. Перезагрузить KB: `python -m app.rag.loader --namespace sales --dir ../seller_staff/knowledge_base/` (и support, teacher)
4. Пересчитать embeddings для memory_atoms и summaries фоновым скриптом (текст уже в БД)

---

### 5. RAG: без изменений

pgvector с 746 чанками — оптимален. Не требует замены. RAGFlow / Dify / Qdrant — overkill для текущего масштаба.

Единственное изменение: при смене embedding-модели нужно пересоздать HNSW-индекс:
```sql
DROP INDEX idx_chunks_embedding;
CREATE INDEX idx_chunks_embedding ON knowledge_chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
```

---

### 6. Согласие на обработку ПДн

**Экран согласия — показывается ДО онбординга (до сбора имени/телефона):**

```
Эврика — ИИ-ассистент EdPalm. Перед началом подтвердите:

☐  Согласен на обработку персональных данных  [Политика →]   ← обязательный
☐  Согласен на принятие решений автоматически (ИИ)            ← обязательный
☐  Хочу получать персонализированные уведомления              ← опциональный

[Начать общение]  ← активна только когда первые два отмечены
```

**Несовершеннолетние (ст. 9 ч. 6 ФЗ-152):**
- Добавить вопрос возраста при первом входе (или читать из портала)
- Если < 18: особый текст "Родитель/законный представитель подтверждает..."
- До 14 лет: только родитель может принять
- 14–18 лет: оба (ребёнок + родитель)
- Реализация: при входе через портал портал знает дату рождения → передаём флаг `is_minor`

**Маркетинговое согласие (3й чекбокс):**
- Опциональный, пустой по умолчанию
- Если не поставлен → follow-up продавца НЕ отправляется, весь остальной функционал работает
- Для действующих учеников (поддержка/учитель) follow-up = сервисные уведомления, этот чекбокс не нужен

**Логирование → таблица `consent_log`:**
- `actor_id`, `channel`, `timestamp`, `pd_consent`, `ai_consent`, `marketing_consent`, `form_version`, `is_minor`

**Отзыв согласия:** команда `/stop` или кнопка в меню → запуск удаления данных (блок 9)

---

### 7. Политика конфиденциальности

> **TODO — согласование с юристом.** Документ разрабатывается отдельно.

**Минимальные требования (для юриста):**
- Наименование и адрес оператора (официальное юрлицо EdPalm)
- Перечень собираемых ПДн: ФИО, телефон, Telegram ID, сообщения, аудио, данные детей
- Цели: консультация, продажа, поддержка, обучение
- Правовые основания: согласие (ст.6 п.1), договор (ст.6 п.5)
- Получатели: Yandex Cloud (LLM/STT/TTS/Embeddings), amoCRM (CRM), DMS (учёт)
- Срок хранения: определить с юристом
- Права субъекта: доступ, исправление, удаление (30 дней), отзыв, запрет маркетинга
- Порядок обращений: email/телефон ответственного за ПДн
- Несовершеннолетние: отдельный раздел про согласие родителей

**Размещение (после согласования):**
- Футер сайта/портала
- Ссылка "Политика →" в экране согласия чат-бота
- Описание Telegram-бота

---

### 8. Маскирование ПДн в логах

**Среда:** маскирование только в `APP_ENV=production`. В dev — не маскировать (тестовые данные, нужна отладка).

**Важно про хостинг:** после миграции на российский сервер логи будут оседать локально (journald/syslog). Нельзя подключать внешние агрегаторы логов (Datadog, Papertrail и т.п.) — все они американские.

**Двухуровневое решение:**

**Уровень 1 — глобальный `MaskingFilter` в `logging_config.py`:**
- Перехватывает все log-записи во всём проекте автоматически
- Regex маскирует телефоны: `79241234567` → `7***4567`, `+7 (924) 123-45-67` → `7***4567`
- Новые логгеры в любом файле получают маскирование без дополнительных настроек
- Включается только при `APP_ENV=production`

**Уровень 2 — whitelist в `tools.py:468`:**
- Логировать только безопасные ключи arguments: `product_name`, `grade`, `amount`, `source`, `reason`, `message`
- Ключи `phone`, `contact_id`, `telegram_id`, `name` — не логируются вообще

**Точечные правки (4 места):**
- `dms.py:354` — убрать surname+name, оставить только contact_id
- `renewal.py:108,134` — убрать client_name / name из строк
- `telegram.py:48` — убрать first_name
- `api/chat.py:625` — заменить `text[:80]` на `text_len=len(text)`, убрать sender_name

---

### 9. Механизм удаления данных

**Двухфазная схема:**

**Фаза 1 — Soft delete (сразу при запросе):**
- `agent_user_profiles.deleted_at = NOW()` — данные скрыты из агента
- Агент больше не использует профиль/память/историю этого actor_id
- amoCRM: обезличить контакт (PATCH с пустым именем) или удалить если лид без оплаты
- `consent_log`: запись `consent_withdrawn`
- Сообщение клиенту: "Данные будут полностью удалены до {дата +30 дней}"

**Фаза 2 — Hard delete (через 30 дней, cron-задача):**
- `DELETE FROM chat_messages WHERE conversation_id IN (SELECT id FROM conversations WHERE actor_id = X)`
- `DELETE FROM conversations WHERE actor_id = X`
- `DELETE FROM agent_memory_atoms WHERE actor_id = X`
- `DELETE FROM agent_conversation_summaries WHERE actor_id = X`
- `DELETE FROM agent_contact_mapping WHERE actor_id = X`
- `DELETE FROM agent_deal_mapping WHERE actor_id = X`
- `DELETE FROM agent_chat_mapping WHERE actor_id = X`
- `DELETE FROM agent_manager_messages WHERE actor_id = X`
- `DELETE FROM agent_payment_orders WHERE actor_id = X` (только неоплаченные; оплаченные обезличить — НК РФ, 3 года)
- `DELETE FROM agent_followup_chain WHERE actor_id = X`
- `DELETE FROM agent_events WHERE actor_id = X` (или обезличить)
- `DELETE FROM agent_user_profiles WHERE actor_id = X`
- `audit_log`: запись "actor_id X hard-deleted at {timestamp}"

**Что СОХРАНЯЕТСЯ после удаления (законные исключения):**
- `consent_log` — доказательство для РКН
- `audit_log` — след удаления ("actor X удалён в дату Y")
- Финансовые записи оплаченных заказов — обезличенные, 3–7 лет (НК РФ)
- Обезличенная аналитика (без actor_id)

**amoCRM:**
- Контакт (ФИО, телефон) → удалить через `DELETE /api/v4/contacts/{id}`
- Сделка без оплаты (лид) → удалить
- Сделка с оплатой → обезличить контакт, сделку оставить для бухгалтерии

**Интерфейс — страница профиля в Эврике:**
- "Мои данные": что хранится (имя, телефон, дети, кол-во разговоров)
- "Скачать мои данные": JSON/PDF — data portability (требование ФЗ-152)
- "Согласия": статус чекбоксов + даты, возможность вкл/выкл уведомления
- "Удалить данные": кнопка → подтверждение → soft delete → сообщение с датой
- Альтернатива: команда `/stop` в чате (тот же flow)

---

### 10. Follow-up: маркировка рекламы

**Решение:** follow-up продавца = реклама → требует отдельного согласия (3й чекбокс в экране согласия, блок 6).
- Если клиент дал согласие на уведомления → follow-up разрешён
- Если не дал → follow-up НЕ отправляется, остальной функционал работает
- Для действующих учеников (поддержка/учитель) → follow-up = сервисные уведомления, согласие не нужно
- Сервисные уведомления (аттестация, оплата) — НЕ реклама, маркировка не нужна

### 11. Дисклеймер об ИИ

**Элемент 1 — постоянный footer над полем ввода (все экраны):**
- Серый текст, 11-12px: "Эврика — ИИ-ассистент. Ответы могут содержать неточности."
- Реализация: 1 div + CSS во фронтенде

**Элемент 2 — первое сообщение (только при первом контакте):**
- "Я — ИИ-ассистент Эврика. Помогаю с вопросами об обучении, но не заменяю менеджера. Если нужен человек — скажите."
- Реализация: проверка `is_first_conversation` в бэкенде

**Элемент 3 — описание Telegram-бота:**
- В BotFather: "ИИ-ассистент онлайн-школы EdPalm"

**Элемент 4 — подготовка к закону 2027 (не реализуем сейчас):**
- Машиночитаемый метатег `ai_generated: true` в ответах API
- Реализовать когда закон вступит в силу (~01.09.2027)

---

## Сравнение: как изменится функционал

### Для пользователя

| Функция | Сейчас | После миграции | Изменение |
|---------|--------|----------------|-----------|
| Чат с ботом | Работает | Работает | Появится экран согласия |
| Качество ответов | GPT-4o | YandexGPT 5.1 Pro | Сопоставимое на русском |
| Голосовые | Whisper + TTS nova | SpeechKit STT + TTS Алёна | Другой голос, то же качество |
| RAG-поиск | OpenAI embeddings (1536d) | YandexGPT embeddings (256d) | Сопоставимое на русском |
| Function calling | Стабильный | Бета (YandexGPT) | Может быть менее стабильным |
| Контекстное окно | 128K (GPT-4o) | 128K (YandexGPT 5.1 Pro) | Без изменений |
| Скорость ответа | ~2-4 сек | ~2-5 сек | Сопоставимая |
| Follow-up | Авто (24ч/48ч/7д) | Авто (сервисный формат) | Текст без промо |
| Удаление данных | Нет | Есть (кнопка/команда) | Новая возможность |
| Политика ПДн | Нет | Есть (ссылка в чате) | Новый элемент |

### Технически

| Компонент | Сейчас | После | Сложность миграции |
|-----------|--------|-------|-------------------|
| LLM клиент | `openai.OpenAI()` | `openai.OpenAI(base_url=yandex)` | Низкая (замена URL) |
| Function calling | OpenAI tools format | YandexGPT tools (совместимый) | Средняя (тестирование) |
| STT | `audio.transcriptions.create()` | SpeechKit REST/gRPC | Средняя (новый SDK) |
| TTS | `audio.speech.create()` | SpeechKit REST | Средняя (новый SDK) |
| Embeddings | `embeddings.create(model=...)` | YandexGPT embeddings API | Средняя (новый API + переиндексация) |
| Согласие ПДн | Нет | Новый UI + таблица consent_log | Средняя |
| Удаление данных | Нет | Новый API endpoint + каскад | Средняя |
| Логирование | Открытые ПДн | Маскирование | Низкая |
| Политика | Нет | Документ + ссылки | Низкая (юридическая работа) |

---

## Порядок миграции (фазы)

### Фаза 0: Юридическая подготовка (параллельно, с юристом)
- [ ] **TODO-юрист:** Разработать Политику конфиденциальности (включая раздел о несовершеннолетних)
- [ ] **TODO-юрист:** Подать уведомление в РКН (pd.rkn.gov.ru с УКЭП)
- [ ] **TODO-юрист:** Заключить DPA с Yandex Cloud
- [ ] Убрать WhatsApp из V2 плана (просто удалить из роадмапа)

### Фаза 1: LLM миграция — OpenAI → YandexGPT 5.1 Pro
- [ ] Получить API-ключ Yandex Cloud AI Studio
- [ ] `config.py`: YANDEX_API_KEY, YANDEX_FOLDER_ID, base_url
- [ ] `llm.py`: OpenAI(base_url=yandex_url), адаптация формата ответов
- [ ] Гибридная pre-fetch архитектура: RAG + профиль до вызова LLM
- [ ] 5 write-only tools через function calling (create_lead, payment_link, manager_task, register_decline, escalate)
- [ ] Тестирование всех 3 ролей (sales/support/teacher)
- [ ] Тестирование streaming, tool calls

### Фаза 2: STT/TTS миграция — OpenAI → Yandex SpeechKit
- [ ] `speech.py`: полная перезапись на SpeechKit REST API
- [ ] ffmpeg конвертация WebM → OGG на бэкенде
- [ ] Выбор голоса TTS (Алёна / другой)
- [ ] Тестирование голосового flow

### Фаза 3: Embeddings миграция — OpenAI → YandexGPT embeddings (256d)
- [ ] SQL миграция: `ALTER TABLE ... ALTER COLUMN embedding TYPE vector(256)` для knowledge_chunks, memory_atoms, summaries
- [ ] Пересоздание HNSW-индексов под 256d
- [ ] `rag/loader.py`: замена OpenAI → Yandex text-search-doc API
- [ ] `rag/search.py`: замена embed_query → Yandex text-search-query API
- [ ] Перезагрузка KB: `--namespace sales`, `--namespace support`
- [ ] Пересчёт embeddings для memory_atoms и summaries (фоновый скрипт)
- [ ] Тестирование RAG-качества, настройка threshold

### Фаза 4: Согласие и compliance
- [ ] SQL: таблица `consent_log` (actor_id, channel, timestamp, pd_consent, ai_consent, marketing_consent, form_version, is_minor)
- [ ] Frontend: экран согласия (3 чекбокса, до онбординга) + обработка несовершеннолетних
- [ ] Backend: API сохранения/проверки согласия
- [ ] Frontend: footer "ИИ-ассистент" над полем ввода (серый, 11-12px)
- [ ] Backend: первое сообщение с дисклеймером при первом контакте
- [ ] BotFather: описание бота с "ИИ-ассистент"

### Фаза 5: Маскирование логов
- [ ] `logging_config.py`: MaskingFilter с regex для телефонов (только APP_ENV=production)
- [ ] `tools.py:468`: whitelist безопасных ключей в args
- [ ] Точечные правки: dms.py, renewal.py, telegram.py, chat.py (4 строки)

### Фаза 6: Удаление данных + профиль
- [ ] SQL: таблица `audit_log` (запись об удалении)
- [ ] Backend: soft delete по actor_id (12 таблиц, пометка deleted_at)
- [ ] Backend: cron-задача hard delete через 30 дней
- [ ] Backend: amoCRM — удаление/обезличивание контакта через API
- [ ] Frontend: страница профиля (мои данные, согласия, скачать, удалить)
- [ ] Backend: API экспорта данных (JSON)

### Фаза 7: Тестирование и запуск
- [ ] Полный регресс всех ролей (sales/support/teacher)
- [ ] Тестирование consent flow + deletion flow
- [ ] Юридическая проверка документов (с юристом)
- [ ] Публикация Политики конфиденциальности
- [ ] Деплой на российский сервер

---

## Стоимость целевого стека (оценка)

| Сервис | Цена | Примечание |
|--------|------|-----------|
| YandexGPT 5.1 Pro | ~800 руб./1М токенов | При текущем объёме ~1-3К руб./мес |
| Yandex SpeechKit STT | ~0.65 руб./мин | При текущем объёме ~100-300 руб./мес |
| Yandex SpeechKit TTS | ~1342 руб./1М символов | При текущем объёме ~200-500 руб./мес |
| YandexGPT embeddings | ~10 руб./1М токенов | Облако, серверы РФ |
| pgvector | Бесплатно (PostgreSQL) | На своём сервере |
| amoCRM | Текущая подписка | Без изменений |

**Итого:** ~2-5 тыс. руб./мес (значительно дешевле OpenAI)
