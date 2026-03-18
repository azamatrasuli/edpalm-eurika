# ТЕСТ-ОРКЕСТРАТОР 9: Фронтенд UX, рендеринг и пользовательский опыт

## Твоя роль

Ты — тест-инженер проекта Эврика. Твоя задача — протестировать **фронтенд и пользовательский опыт**: как рендерятся сообщения, работают ли SSE события, отображаются ли payment cards, escalation banners, suggestion chips, сайдбар диалогов, голосовой ввод, тёмная тема, мобильная адаптация. Тестируй через API + проверку SSE-событий.

## Контекст

- **Backend:** `/Users/rslazamat/Profession /edpalm/eurika/backend/`
- **Frontend:** `/Users/rslazamat/Profession /edpalm/eurika/frontend/`
- **Запуск backend:** `cd "/Users/rslazamat/Profession /edpalm/eurika/backend" && PYTHONPATH=. .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload`

## Архитектура фронтенда

- React 19 + Vite + Tailwind 4
- HashRouter: `/` → ChatPage, `/dashboard` → DashboardPage
- SSE стриминг через кастомный парсер
- Hooks: useChat, useConversationList, useOnboarding, useDashboard
- Telegram SDK: @twa-dev/sdk (theme, haptics, BackButton)

## SSE формат

```
event: meta
data: {"conversation_id": "...", "actor_id": "...", "channel": "..."}

event: token
data: {"text": "слово"}

event: tool_call
data: {"name": "search_knowledge_base"}

event: payment_card
data: {"product_name": "Классный", "amount_rub": 80000, "payment_url": "https://..."}

event: escalation
data: {"reason": "Клиент требует возврат"}

event: suggestions
data: {"chips": [{"label": "Узнать цену", "value": "Сколько стоит?"}, ...]}

event: done
data: {"text": "полный ответ", "usage_tokens": 1234}
```

## Как создать тестовый раннер

test_runner.py в backend/ — фокус на **SSE events парсинг**: проверять наличие и корректность КАЖДОГО типа event.

## 100 сценариев тестирования

### Блок A: SSE стриминг (1-25)

1. Отправить сообщение → получить event: meta с conversation_id
2. meta.conversation_id — UUID формат
3. meta.actor_id — соответствует типу auth
4. meta.channel — portal/telegram/external
5. Tokens приходят последовательно (не пустые)
6. Токены собранные вместе = полный ответ из event: done
7. event: done содержит полный text (не обрезанный)
8. event: done.usage_tokens — число или null (не строка)
9. Нет дублированных event: done в одном потоке
10. Нет event: token после event: done
11. tool_call event приходит ДО связанных tokens
12. tool_call.name — валидное имя инструмента (search_knowledge_base, etc.)
13. Поток корректно закрывается после done
14. Пустой ответ (edge case) → event: done с пустым text? или fallback?
15. Ошибка LLM → event: error с сообщением
16. Длинный ответ (2000+ символов) → все tokens приходят, done.text полный
17. Ответ с markdown (таблица, списки, **bold**) → tokens содержат markdown
18. Ответ с кириллицей → корректная кодировка UTF-8
19. Ответ с эмодзи → корректная передача
20. Два потока от одного юзера одновременно → оба работают
21. AbortController: прервать поток → сервер не крашится
22. Таймаут SSE (90с в test_runner) → корректная обработка
23. Несколько tool_call events в одном потоке (multi-tool) → все перечислены
24. event: meta приходит ПЕРВЫМ (до token/tool_call)
25. Порядок events: meta → [tool_call]* → [token]* → [suggestions] → done

### Блок B: Payment card (26-40)

26. Спровоцировать payment → event: payment_card присутствует
27. payment_card.product_name — строка, не пустая
28. payment_card.amount_rub — число (не строка)
29. payment_card.payment_url — валидный URL (начинается с https://)
30. Фронтенд: PaymentCard показывает product_name
31. Фронтенд: PaymentCard показывает amount с форматированием (80 000 ₽)
32. Фронтенд: кнопка "Оплатить" ведёт на payment_url
33. Payment card приходит МЕЖДУ tokens (не после done)
34. Один поток может содержать 1 payment card + текст
35. Payment card без payment_url → проверить graceful handling
36. Payment card с amount=0 → проверить отображение
37. Payment card: amount_rub = 1 (Заочный) → корректно
38. Payment card: amount_rub = 250000 (Персональный) → форматирование
39. Нет payment card если пользователь не просил оплату
40. Payment card + escalation в одном потоке → оба отображаются

### Блок C: Escalation banner (41-55)

41. Спровоцировать escalation → event: escalation присутствует
42. escalation.reason — строка, не пустая
43. escalation.reason описывает причину (не generic)
44. Фронтенд: EscalationBanner показывается после escalation event
45. Фронтенд: banner жёлтый, содержит "Диалог передан менеджеру"
46. Фронтенд: banner показывает reason
47. После escalation → новые сообщения блокируются (input disabled)
48. Escalation на "хочу человека" → reason = "хочет поговорить с человеком"
49. Escalation на скидку → reason содержит "скидка"
50. Escalation на негатив → reason содержит причину негатива
51. Двойная escalation → показывается только один banner
52. Escalation + suggestions → suggestions НЕ отображаются
53. Escalation + payment_card → payment card рядом с banner?
54. force_new=true после escalation → новый диалог без banner
55. Escalation reason в логах agent_events → корректный

### Блок D: Suggestion chips (56-70)

56. Сообщение → event: suggestions с chips array
57. chips — массив объектов с label и value
58. label — короткий текст (2-5 слов)
59. value — текст для отправки (может отличаться от label)
60. 2-4 chips в массиве (не больше 4)
61. Фронтенд: SuggestionChips рендерит горизонтальные пилюли
62. Клик по chip → отправка value как сообщение
63. Chips исчезают после клика
64. Chips меняются после каждого ответа (не одни и те же)
65. Chips релевантны контексту (не generic "Привет", "Пока")
66. Chips на русском языке
67. Нет chips после escalation
68. Chips после done event (порядок: done → suggestions)
69. suggestions event приходит ПОСЛЕ done, не до
70. Пустой chips array → фронтенд не рендерит ничего

### Блок E: Conversation sidebar (71-85)

71. conversations/list → массив диалогов
72. Каждый диалог: id, title, agent_role, message_count, last_user_message, created_at
73. Сортировка: по updated_at DESC (новые сверху)
74. Пагинация: offset=0, limit=20 → первые 20
75. Пагинация: offset=20, limit=20 → следующие
76. Фильтр по agent_role → только нужная роль
77. Search: поиск по title + last_user_message
78. Archive: archived conversation не в списке (includeArchived=false)
79. Archive: с includeArchived=true → появляется
80. Rename: новый title сохраняется
81. Auto-title: первое сообщение → title = первые слова
82. Новый диалог → появляется в начале списка
83. Delete → диалог исчезает
84. Message count корректен (1 user + 1 assistant = 2)
85. last_user_message содержит текст последнего сообщения юзера

### Блок F: Голос, markdown, прочее (86-100)

86. POST /api/v1/chat/transcribe — загрузка аудио → transcript
87. POST /api/v1/chat/voice — загрузка аудио → SSE стрим ответа
88. Markdown в ответе: **bold** рендерится корректно
89. Markdown: - список рендерится
90. Markdown: | таблица | рендерится
91. Markdown: ```код``` рендерится
92. Markdown: [ссылка](url) рендерится как кликабельная
93. Длинное сообщение (3000 символов) → скролл работает
94. Быстрая отправка 3 сообщений подряд → все обрабатываются
95. Typing indicator: typing=true во время стриминга
96. Auto-scroll: новые сообщения прокручивают к низу
97. Session storage: conversation_id сохраняется при перезагрузке
98. Session storage: per-role (sales ≠ support)
99. Тёмная тема: CSS variables переключаются (data-theme="dark")
100. Mobile responsive: на ширине 375px всё влезает

## Методология

Для каждого сценария:
1. Вызови API через test_runner.py
2. Разбери SSE поток по events
3. Проверь каждый event type и его данные
4. Для фронтенд-сценариев — проверь код компонентов (прочитай файлы)
5. Для sidebar — вызови conversations/ endpoints

## Инструкции

1. Изучи: frontend/src/ (все компоненты, hooks, api/)
2. Изучи: backend/app/api/chat.py (SSE generation)
3. test_runner.py с детальным SSE парсингом (сохраняй ВСЕ events)
4. По 5 субагентов, 5с пауза
5. Баг → фикс → retest
6. Удали test_runner.py
