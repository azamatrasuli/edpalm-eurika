# Миграция Эврики на собственные серверы

## Текущая архитектура

| Компонент | Где сейчас | Куда переносим |
|---|---|---|
| Эврика бэкенд | Render (srv-d6urv7a4d50c73fbocd0) | Свой сервер |
| Эврика фронтенд | Vercel | Свой сервер (или оставить Vercel) |
| PostgreSQL | Supabase (vlywxexthbxehtmopird, ap-southeast-2) | Свой PostgreSQL |
| Портал | my-dev.space | Свой сервер (уже там) |

---

## Оценка работ

### 1. PostgreSQL — миграция БД (2–3 часа)

**Что нужно:**
- PostgreSQL 14+ на вашем сервере
- 3 расширения: `pgvector`, `pgcrypto`, `pg_trgm`
- Минимум 50 GB SSD, 4 GB RAM для БД

**Шаги:**
```bash
# 1. Установить расширения на новом сервере
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

# 2. Дамп из Supabase
pg_dump "postgresql://postgres.vlywxexthbxehtmopird:PASSWORD@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres" \
  --no-owner --no-acl > eureka_dump.sql

# 3. Залить на новый сервер
psql "postgresql://user:pass@your-server:5432/eureka" < eureka_dump.sql
```

**26 таблиц**, 25 миграций, pgvector индексы (HNSW).

**Supabase-специфичных фич НЕТ** — ни RLS, ни Edge Functions, ни Realtime, ни Storage. Чистый PostgreSQL через psycopg.

---

### 2. Бэкенд — перенос приложения (1–2 часа)

**Требования к серверу:**
- Python 3.9+
- 4 vCPU, 4–8 GB RAM (минимум)
- 8 vCPU, 16 GB RAM (рекомендация для прода)
- Исходящий HTTPS (OpenAI, amoCRM, DMS, Telegram)

**Шаги:**
```bash
# 1. Клонировать репо
git clone https://github.com/azamatrasuli/edplam-eurika.git
cd edplam-eurika/backend

# 2. Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Скопировать .env с Render (все ~80 переменных)
# Главное изменение: DATABASE_URL → новый PostgreSQL

# 4. Запуск
uvicorn app.main:app --host 0.0.0.0 --port 8009 --workers 4

# 5. Проверка
curl http://localhost:8009/health
```

**Процесс-менеджер (рекомендация):** systemd или supervisor для автоперезапуска.

---

### 3. Переменные окружения (~80 штук)

**Критичные для смены:**

| Переменная | Что менять |
|---|---|
| `DATABASE_URL` | Новый PostgreSQL URI |
| `BACKEND_URL` | Новый URL бэкенда (вместо Render) |
| `FRONTEND_URL` | Если переносим фронтенд — новый URL |
| `APP_CORS_ORIGINS` | Добавить домен нового фронтенда |
| `PORTAL_API_URL` | URL портала (https://my-dev.space) |

**Не менять** (остаются как есть):
- `OPENAI_API_KEY` — тот же ключ
- `AMOCRM_*` — все CRM настройки
- `DMS_*` — DMS credentials
- `TELEGRAM_BOT_TOKEN` — тот же бот
- `PORTAL_JWT_SECRET` — общий с порталом
- `PORTAL_INTERNAL_API_KEY` — общий с порталом
- Все `MEMORY_*`, `RAG_*`, `PII_*` параметры

---

### 4. Фронтенд Эврики (30 мин)

**Два варианта:**

**А) Оставить на Vercel** (проще):
- Ничего не делать
- Поменять `VITE_API_BASE_URL` в Vercel на новый URL бэкенда
- Редеплой

**Б) Перенести на свой сервер:**
```bash
cd eurika/frontend
npm install && npm run build
# Результат в dist/ — статика, отдать через nginx
```
- Настроить nginx для SPA (fallback на index.html)
- SSL сертификат (Let's Encrypt)

---

### 5. Telegram webhook (15 мин)

После переноса бэкенда — обновить webhook URL:
```bash
curl "https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://NEW-BACKEND-URL/api/telegram/webhook"
```

---

### 6. amoCRM callback URL (15 мин)

В настройках amoCRM интеграции поменять redirect URI на новый домен бэкенда. Обновить токен.

---

### 7. RAG база знаний (15 мин)

После миграции БД проверить что чанки на месте:
```sql
SELECT namespace, COUNT(*) FROM knowledge_chunks GROUP BY namespace;
-- Ожидаем: sales ~100, support ~94
```

Если пусто — перезагрузить:
```bash
PYTHONPATH=. python -m app.rag.loader --namespace sales --dir ../seller_staff/knowledge_base/
PYTHONPATH=. python -m app.rag.loader --namespace support --dir ../support_staff/knowledge_base/
```

---

### 8. DNS и SSL (30 мин)

- Выделить поддомен (например `eureka-api.my-dev.space`)
- SSL через Let's Encrypt или ваш провайдер
- nginx reverse proxy → uvicorn :8009

---

## Итоговая оценка

| Этап | Время | Сложность |
|---|---|---|
| PostgreSQL миграция | 2–3 ч | Средняя (pgvector, дамп, проверка) |
| Бэкенд деплой | 1–2 ч | Низкая (pip install, env vars, systemd) |
| ENV переменные | 30 мин | Низкая (скопировать с Render) |
| Фронтенд | 30 мин | Низкая (Vercel redirect или nginx) |
| Telegram webhook | 15 мин | Низкая |
| amoCRM redirect | 15 мин | Низкая |
| RAG проверка | 15 мин | Низкая |
| DNS + SSL + nginx | 30 мин | Средняя |
| **Тестирование** | **2–3 ч** | **Критично** |
| **ИТОГО** | **~8 часов** | — |

---

## Чеклист после миграции

- [ ] `curl https://NEW-URL/health` → 200
- [ ] Чат работает (SSE стриминг, ответы от GPT-4o)
- [ ] Онбординг (DMS верификация по телефону)
- [ ] amoCRM синхронизация (контакты, сделки)
- [ ] Telegram Mini App (webhook + авторизация)
- [ ] Портал → виджет Эврики (JWT, children, grade)
- [ ] RAG поиск по базе знаний
- [ ] PII прокси (ФИО не утекают в OpenAI)
- [ ] Consent (ФЗ-152, GDPR)
- [ ] Дашборд (метрики, эскалации)
- [ ] Фоновые задачи (платежи, follow-up, уведомления)
- [ ] Логи без ПДн в production mode

---

## Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| pgvector не установлен | Средняя | Проверить `SELECT extversion FROM pg_extension WHERE extname='vector'` |
| Потеря данных при дампе | Низкая | Сделать дамп + проверить count по всем таблицам |
| OpenAI latency выше | Низкая | Сервер ближе к eu-west (OpenAI в US/EU) |
| amoCRM токен протух | Средняя | Обновить OAuth после смены redirect URI |
| Telegram webhook не доходит | Низкая | Проверить SSL + открытый 443 порт |
