# ТЕСТ-ОРКЕСТРАТОР 1: Аутентификация, идентификация и сессии

## Твоя роль

Ты — тест-инженер проекта Эврика (ИИ-агент EdPalm). Твоя задача — **досконально протестировать** систему аутентификации, идентификации пользователей, управление сессиями и онбординг. Ты оркестратор — запускаешь субагентов батчами по 5, анализируешь результаты, фиксишь баги, перетестируешь.

## Контекст проекта

**Эврика** — ИИ-агент (GPT-4o) онлайн-школы EdPalm. Три роли: Продавец (sales), Поддержка (support), Учитель (teacher). Работает как ChatGPT — чат-интерфейс.

- **Backend:** Python FastAPI, порт 8009, директория `/Users/rslazamat/Profession /edpalm/eurika/backend/`
- **Frontend:** React 19 + Vite, порт 5177, директория `/Users/rslazamat/Profession /edpalm/eurika/frontend/`
- **БД:** Supabase PostgreSQL (project: `vlywxexthbxehtmopird`)
- **LLM:** OpenAI GPT-4o
- **Запуск бэкенда:** `cd "/Users/rslazamat/Profession /edpalm/eurika/backend" && PYTHONPATH=. .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload`

## Три режима аутентификации

### 1. Portal (JWT)
- PHP-портал выдаёт JWT с `user_id`, `phone`, `name` → `?token=...`
- Бэкенд верифицирует по `PORTAL_JWT_SECRET` (HS256)
- TTL 15 минут
- `channel=portal`, `actor_id=portal:{user_id}`

### 2. Telegram Mini App
- `initData` от @twa-dev/sdk, HMAC-SHA256 с BOT_TOKEN
- Валидация `auth_date` (не старше 24ч)
- `channel=telegram`, `actor_id=telegram:{tg_id}`

### 3. External Link
- Формат: `lead_id:expires_ts:signature` (HMAC-SHA256 с EXTERNAL_LINK_SECRET)
- TTL 48 часов
- `channel=external`, `actor_id=external:{lead_hash}`

## Ключевые файлы

- `backend/app/auth/service.py` — диспетчер аутентификации
- `backend/app/auth/portal.py` — JWT верификация
- `backend/app/auth/telegram.py` — Telegram HMAC
- `backend/app/auth/external.py` — подписанные ссылки
- `backend/app/services/onboarding.py` — онбординг/верификация профиля
- `backend/app/api/chat.py` — эндпоинты (start, stream)
- `backend/app/db/repository.py` — save/get user profiles
- `frontend/src/lib/authContext.js` — фронтенд auth логика

## API эндпоинты для тестов

```
POST /api/v1/conversations/start  — начало диалога (auth + role)
POST /api/v1/chat/stream           — отправка сообщения (SSE)
POST /api/v1/profile/check         — проверка профиля
POST /api/v1/onboarding/verify     — верификация через DMS
POST /api/v1/conversations/list    — список диалогов
GET  /health                       — healthcheck
```

## Как создать тестовый раннер

Первым делом создай файл `test_runner.py` в backend/ директории. Он должен:
1. Генерировать external-токены через HMAC-SHA256 (секрет из `app.config.get_settings().external_link_secret`)
2. Вызывать API через httpx
3. Парсить SSE-ответы (формат: `event: type\ndata: json`)
4. Возвращать JSON с результатами

Для portal-токенов генерируй JWT через PyJWT с секретом из `get_settings().portal_jwt_secret`.

## 100 сценариев тестирования

### Блок A: External Link Auth (сценарии 1-25)
1. Валидный external token → успешный старт диалога
2. Просроченный external token (expires_ts в прошлом) → ошибка 401
3. Невалидная подпись (изменён 1 символ) → ошибка 401
4. Пустой токен → ошибка 401/422
5. Токен без двоеточий (неправильный формат) → ошибка
6. Токен с пустым lead_id → проверить поведение
7. Два диалога с одним external token → один actor_id
8. Два разных external token → два разных actor_id
9. External token + role=sales → sales greeting
10. External token + role=support → support greeting
11. Переключение ролей: сначала sales, потом support с тем же токеном
12. force_new=true → новый диалог даже при существующем
13. force_new=false → возобновление существующего
14. Отправка сообщения без conversation_id → автосоздание
15. Отправка сообщения с чужим conversation_id → ошибка или новый
16. Одновременно два диалога с одним actor_id (sales + support)
17. 100 символов в lead_id → работает
18. Спецсимволы в lead_id (кириллица, пробелы, эмодзи)
19. Токен с expires_ts = 0 → ошибка
20. Токен с expires_ts через 1 секунду → проверить гонку
21. Последовательно 10 сообщений в одном диалоге → история сохраняется
22. Получение списка диалогов по actor_id
23. Архивирование диалога → не появляется в списке
24. Удаление диалога → сообщения тоже удалены
25. Переименование диалога → новое название в списке

### Блок B: Portal JWT Auth (сценарии 26-50)
26. Валидный JWT с user_id, name, phone → успешный старт
27. JWT с истёкшим exp → ошибка 401
28. JWT с неправильным секретом → ошибка 401
29. JWT без user_id → ошибка
30. JWT с user_id но без phone → работает (phone=None)
31. JWT с user_id и phone → автоверификация в DMS (silent onboarding)
32. Проверить что portal-юзер с phone получает профиль из DMS
33. Два JWT от одного user_id → один actor_id
34. JWT от разных user_id → разные actor_id
35. Portal auth + profile/check → has_profile=true (если был verify)
36. Portal auth + переключение sales→support → сохранение контекста
37. JWT с дополнительными claims (grade, tariff) → не ломает auth
38. JWT с алгоритмом RS256 вместо HS256 → ошибка
39. Очень длинный JWT (100+ claims) → не ломает
40. JWT с exp через 1 секунду → race condition
41. Portal-юзер: onboarding/verify с телефоном → DMS поиск
42. Portal-юзер: onboarding/verify с несуществующим телефоном → not_found
43. Portal-юзер: повторный verify → обновление профиля
44. Portal-юзер: conversations/list с фильтром по role
45. Portal-юзер: conversations/search по тексту
46. Portal-юзер: 5 диалогов sales + 3 support → list фильтрует корректно
47. Portal-юзер: пагинация (offset=0, limit=3, потом offset=3)
48. Portal-юзер: голосовое сообщение (POST /chat/voice) с auth
49. Portal-юзер: transcribe (POST /chat/transcribe) с auth
50. Portal-юзер: архив + поиск → архивные не в результатах

### Блок C: Telegram Auth (сценарии 51-70)
51. Валидный initData с user_id → успешный старт
52. initData с протухшим auth_date (>24ч) → ошибка
53. initData с неправильным hash → ошибка
54. initData без user → ошибка
55. Telegram-юзер: actor_id = telegram:{id}
56. Telegram-юзер: display_name из first_name + last_name
57. Telegram-юзер: username извлекается
58. Telegram-юзер + sales → приветствие с именем
59. Telegram-юзер + support → другое приветствие
60. Telegram-юзер: history сохраняется между сообщениями
61. initData с пустым user object → graceful error
62. initData вообще не URL-encoded → ошибка
63. Повторный запрос с тем же initData → работает (идемпотентность)
64. Telegram + Portal один и тот же человек → разные actor_id (правильно)
65. Telegram-юзер: profile/check → no profile (не проходил onboarding)
66. Telegram-юзер: назвал телефон в чате → агент вызывает get_client_profile
67. Telegram-юзер: чат в реальном времени (3 сообщения подряд)
68. Telegram-юзер: два параллельных диалога (sales + support)
69. Мок initData с кириллическим именем → корректная обработка
70. Telegram-юзер: conversation list пуст для нового юзера

### Блок D: Смешанные и граничные (сценарии 71-90)
71. Запрос без любой авторизации → 401
72. Запрос с двумя типами auth одновременно (portal + external) → ошибка
73. Запрос с тремя типами auth → ошибка
74. Health endpoint без auth → 200
75. Неизвестный agent_role (role=teacher) → поведение
76. Пустой agent_role → default (sales)
77. SQL-инъекция в token → безопасная обработка
78. XSS в display_name → экранирование
79. Очень длинное сообщение (10000 символов) → обработка
80. Пустое сообщение → graceful handling
81. Только пробелы в сообщении → поведение
82. Unicode эмодзи в сообщении → корректная обработка
83. Бинарные данные в message → ошибка, не крэш
84. Одновременно 5 stream-запросов от одного юзера → все отвечают
85. Conversation start → stream без conversation_id → авто-связка
86. Два start подряд с force_new=false → один conversation
87. Delete несуществующего conversation → 404 или graceful
88. Archive уже архивного → идемпотентность
89. Rename с пустым title → поведение
90. Rename с title длиной 1000 символов → обрезка или ошибка

### Блок E: Onboarding & Профили (сценарии 91-100)
91. verify с client_type=existing, phone существует в DMS → found
92. verify с client_type=existing, phone не в DMS → not_found
93. verify с client_type=new → новый лид
94. verify с невалидным форматом телефона → обработка
95. profile/check для нового юзера → has_profile=false
96. profile/check после verify → has_profile=true, данные совпадают
97. verify дважды с одним телефоном → обновление, не дубликат
98. verify с phone в формате +7... → нормализация
99. verify с phone в формате 8(XXX)... → DMS формат
100. Профиль сохраняется в agent_user_profiles → проверка через SQL

## Инструкции по работе

1. **Изучи код** — прочитай все файлы auth/, onboarding, chat endpoints
2. **Создай test_runner.py** — утилита для генерации токенов и вызова API
3. **Запускай батчами по 5 субагентов** — каждый агент тестирует 5-10 сценариев
4. **Между батчами пауза 5 секунд** — чтобы не перегружать OpenAI API (лимит 30K TPM)
5. **Каждый сценарий = PASS/FAIL** с полным объяснением
6. **Найдёшь баг → фикси → перетестируй** субагентом
7. **В конце дай сводку**: сколько PASS/FAIL, какие баги найдены и пофикшены
8. **Удали test_runner.py** после завершения

## Критерии качества

- 0 крэшей бэкенда на любом вводе
- Невалидные токены ВСЕГДА возвращают 401, никогда не дают доступ
- Один юзер = один actor_id независимо от количества сессий
- История сообщений сохраняется и восстанавливается корректно
- Onboarding не создаёт дубликатов профилей
- SQL-инъекции и XSS не проходят
