# ТЕСТ-ОРКЕСТРАТОР 5: Интеграции, инфраструктура и надёжность

## Твоя роль

Ты — тест-инженер проекта Эврика. Твоя задача — **досконально протестировать** все интеграции (amoCRM, DMS, Supabase, Telegram), инфраструктурную надёжность, обработку ошибок, производительность и целостность данных. Ты оркестратор — запускаешь субагентов батчами по 5, проверяешь БД, логи, API ответы.

## Контекст проекта

**Эврика** — ИИ-агент EdPalm. Backend на FastAPI + Supabase + OpenAI + amoCRM + DMS.

- **Backend:** `/Users/rslazamat/Profession /edpalm/eurika/backend/`
- **Запуск:** `cd "/Users/rslazamat/Profession /edpalm/eurika/backend" && PYTHONPATH=. .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload`
- **БД:** Supabase `vlywxexthbxehtmopird` (есть MCP инструмент `mcp__supabase__execute_sql`)
- **amoCRM:** `azamatrasuli`, Sales `10689842`, Service `10689990`
- **DMS:** `https://proxy.hss.center` (verify=False, SHA-256 auth)
- **Логи:** `/tmp/eurika_backend.log`

## Ключевые файлы

- `backend/app/integrations/amocrm.py` — amoCRM REST v4
- `backend/app/integrations/amocrm_chat.py` — amoCRM Chat (imBox)
- `backend/app/integrations/dms.py` — DMS (Go backend)
- `backend/app/services/imbox.py` — ImBox сервис
- `backend/app/services/payment.py` — платежи
- `backend/app/services/followup.py` — follow-up цепочки
- `backend/app/services/memory.py` — conversational memory
- `backend/app/db/pool.py` — connection pool
- `backend/app/db/repository.py` — все CRUD операции
- `backend/app/db/events.py` — event tracking
- `backend/app/db/dashboard.py` — dashboard queries
- `backend/app/api/dashboard.py` — dashboard API (Bearer auth)
- `backend/app/config.py` — все настройки

## Как создать тестовый раннер

Создай `test_runner.py` в backend/:
1. Генерация токенов (external + portal JWT)
2. HTTP-вызовы через httpx
3. SSE парсинг
4. **SQL-запросы через Supabase MCP** для проверки данных в БД
5. Проверка логов бэкенда

## 100 сценариев тестирования

### Блок A: amoCRM интеграция (1-25)
1. Отправить сообщение с role=sales → проверить что в логах есть imBox forward
2. Проверить что `amocrm_tokens` в БД валидны (expires_at в будущем)
3. Отправить сообщение, получить ответ → проверить `agent_events` в БД (event_type=tool_called)
4. Спровоцировать escalate_to_manager → проверить что в логах есть Telegram notification
5. Создать лида (имя + телефон в чате) → проверить `agent_contact_mapping` в БД
6. Создать лида → проверить `agent_deal_mapping` в БД
7. Обновить сделку → проверить что status_id изменился
8. Два разных юзера создают лидов → два разных contact_id
9. Один юзер, два диалога → один contact_mapping
10. Проверить что amoCRM rate limiting работает (150ms между запросами)
11. sales-сценарий с get_amocrm_contact → проверить логи (поиск по телефону)
12. support-сценарий с create_amocrm_ticket → проверить `agent_events` (event_type=tool_called, name=create_amocrm_ticket)
13. Escalation → проверить `agent_events` (event_type=escalation)
14. Проверить что Custom Fields заполняются: Telegram ID (1404988), Product (1404990), Amount (1404992)
15. ImBox: user message → проверить в логах `[forward_user]` success
16. ImBox: agent response → проверить `[forward_agent]` (после фикса sender/receiver)
17. ImBox: новый юзер → автоматическое создание chat в amojo
18. Проверить `agent_chat_mapping` после первого сообщения
19. amoCRM token refresh: проверить что auto-refresh работает (если expiry < 5 min)
20. Два одновременных запроса к amoCRM → rate limiter не ломается
21. Тест с несуществующим телефоном → get_amocrm_contact возвращает null, не крэш
22. Создание контакта с кириллическим именем → корректно
23. Создание контакта с длинным именем (100 символов) → корректно
24. Pipeline routing: sales сценарий → pipeline 10689842
25. Pipeline routing: support сценарий → pipeline 10689990

### Блок B: DMS интеграция (26-40)
26. get_client_profile с реальным телефоном из DMS → профиль найден
27. get_client_profile с несуществующим телефоном → not_found, не крэш
28. get_client_profile с телефоном в формате +7... → нормализация
29. get_client_profile с телефоном в формате 8(XXX)... → нормализация
30. get_client_profile с телефоном без + → нормализация
31. DMS auth → проверить что токен получен (SHA-256 hash)
32. DMS auto-refresh при 401 → проверить в логах
33. DMS SSL verify=False → не ломается на просроченном сертификате
34. generate_payment_link → проверить что URL возвращается
35. generate_payment_link с несуществующим продуктом → graceful error
36. DMS products catalog → проверить что продукты загружаются
37. DMS search с разными форматами телефона → найти контакт
38. DMS студенты: contact_id → список учеников с grade, product, state
39. DMS: проверить что camelCase ответы корректно парсятся (accessToken, moodleId)
40. DMS timeout → graceful fallback, не крэш бэкенда

### Блок C: База данных и целостность (41-60)
41. Новый диалог → запись в `conversations` с правильным actor_id, channel, agent_role
42. Сообщение → запись в `chat_messages` с правильным role, content
43. 10 сообщений → все 10 в `chat_messages`, порядок по created_at
44. Архивирование → status='archived' в `conversations`
45. Удаление → conversation + messages удалены (CASCADE)
46. `knowledge_chunks`: все 145 чанков на месте (101 sales + 44 support)
47. `knowledge_chunks`: все embeddings 1536 dims, 0 NULL
48. `knowledge_chunks`: 0 дубликатов
49. `knowledge_chunks`: HNSW индекс существует
50. `agent_user_profiles`: verify → профиль создан с dms_verified=true
51. `agent_user_profiles`: повторный verify → update, не дубликат
52. `agent_events`: после диалога с tool calls → events записаны
53. `agent_events`: event_type корректный (tool_called, rag_miss, escalation)
54. `agent_conversation_summaries`: проверить что summarizer работает
55. `agent_memory_atoms`: проверить что факты сохраняются
56. Пагинация conversations/list: offset=0 limit=5 → 5 записей
57. Пагинация: offset=5 limit=5 → следующие 5
58. Search conversations: по тексту → находит
59. Rename conversation → title обновлён
60. Connection pool: min=2, max=10, проверить через pg_stat_activity

### Блок D: API endpoints и error handling (61-80)
61. GET /health → 200
62. POST /api/v1/conversations/start без auth → 401
63. POST /api/v1/chat/stream без auth → 401
64. POST /api/v1/conversations/start с невалидным JSON → 422
65. POST /api/v1/chat/stream с пустым message → graceful handling
66. POST /api/v1/dashboard/metrics без API key → 401/403
67. POST /api/v1/dashboard/metrics с правильным key → 200 + данные
68. GET /api/v1/dashboard/conversations с date_from/date_to → фильтрация
69. GET /api/v1/dashboard/escalations → список эскалаций
70. GET /api/v1/dashboard/unanswered → RAG misses
71. POST /api/v1/profile/check для нового юзера → has_profile=false
72. POST /api/v1/onboarding/verify с валидным телефоном → found
73. POST /api/v1/onboarding/verify с невалидным → not_found
74. POST /api/v1/conversations/{id}/archive → archived
75. POST /api/v1/conversations/{id}/delete → deleted
76. POST несуществующего conversation → 404
77. SSE stream: проверить формат (event: type\ndata: json\n\n)
78. SSE stream: event types: meta, token, tool_call, payment_card, escalation, suggestions, done
79. SSE stream: прерывание (disconnect) → сервер не крэшится
80. Request ID в каждом ответе (middleware) → уникальный

### Блок E: Производительность и нагрузка (81-90)
81. Время ответа /health → <100ms
82. Время ответа /conversations/start → <2s
83. Время ответа /chat/stream (первый token) → <5s
84. 3 одновременных stream запроса → все отвечают
85. 5 одновременных stream запросов → проверить rate limit handling
86. Диалог с 20 сообщениями → history не ломается
87. Диалог с 50 сообщениями → проверить обрезку истории (limit 50)
88. 10 диалогов подряд force_new=true → все создаются
89. Conversation list с 50+ записями → пагинация работает
90. RAG search latency: замерить время от запроса до ответа

### Блок F: Suggestion chips и memory (91-100)
91. Отправить сообщение → проверить что в SSE есть event: suggestions
92. Suggestions содержат chips array с label + value
93. Suggestions: 2-3 чипа, релевантные контексту
94. Suggestions: не повторяют вопрос пользователя
95. Memory: отправить "Меня зовут Алексей" → в следующем сообщении обращается по имени
96. Memory: сказать класс → в следующем ответе не переспрашивает
97. Memory: назвать телефон → get_client_profile вызывается автоматически
98. Memory summary: после 30 мин idle → summarizer создаёт summary
99. Memory atoms: факт "ребёнок в 5 классе" → сохранён в agent_memory_atoms
100. Cross-role memory: факт из sales доступен в support (preferences shared)

## Инструменты проверки

### SQL через Supabase MCP:
```sql
-- Проверить события
SELECT event_type, COUNT(*) FROM agent_events GROUP BY event_type;
-- Проверить маппинги
SELECT * FROM agent_contact_mapping ORDER BY created_at DESC LIMIT 5;
-- Проверить чанки KB
SELECT namespace, COUNT(*) FROM knowledge_chunks GROUP BY namespace;
```

### Логи бэкенда:
```bash
grep "tool_called\|escalation\|forward_user\|forward_agent\|Rate limit" /tmp/eurika_backend.log
```

## Критерии качества

### Надёжность:
- 0 крэшей бэкенда при любых входных данных
- Graceful degradation при недоступности DMS/amoCRM/OpenAI
- Retry при 429 (до 3 попыток)
- Fire-and-forget для imBox (не блокирует чат)

### Целостность данных:
- Все сообщения сохранены в БД
- Events трекаются для каждого tool call
- Contact/deal mappings корректны
- KB chunks: 0 дубликатов, 0 NULL embeddings

### Производительность:
- Healthcheck <100ms
- Первый token <5s
- SSE stream не обрывается

## Инструкции

1. Изучи ВСЕ файлы интеграций и db/
2. Создай test_runner.py с SQL-проверками
3. Запускай по 5, пауза 5с
4. После каждого батча проверяй БД через MCP SQL
5. Проверяй логи после каждого теста
6. Баг → фикс → retest
7. Итог: PASS/FAIL + баги + performance metrics
8. Удали test_runner.py
