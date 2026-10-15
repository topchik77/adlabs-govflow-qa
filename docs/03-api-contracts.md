# API draft v1

OpenAPI генерируется из Pydantic-моделей и сохраняется командой `python scripts/export_openapi.py` в `docs/openapi.json`. UI Swagger: `/docs`.

Все операции: `/api/v1`, Bearer JWT; JSON UTF-8. Ответ ошибки: `{code,message,correlation_id,details}`. X-Correlation-ID возвращается в каждом ответе. Валидация не отражает введённые секреты.

| Метод | Путь | Тело / назначение |
|---|---|---|
| POST | /auth/login | username, password → access_token, user |
| GET | /auth/me | Текущая идентичность |
| GET/POST | /applications | Фильтр status, limit, offset, sort; создание type, title, description |
| GET/PATCH | /applications/{id} | Карточка / expected_version + форма |
| POST | /applications/{id}/attachments | multipart file + expected_version |
| GET | /applications/{id}/attachments/{attachment_id} | Авторизованное скачивание |
| POST | /applications/{id}/prepare-signature | expected_version |
| POST | /applications/{id}/sign | expected_version, document_hash |
| POST | /applications/{id}/submit | expected_version; обязательный Idempotency-Key → 202 |
| POST | /applications/{id}/review | expected_version, decision: APPROVED/REJECTED/NEEDS_CORRECTION, reason |
| POST | /applications/{id}/sign-decision | expected_version, document_hash решения |
| POST | /applications/{id}/cancel | expected_version |
| GET | /applications/{id}/audit | История переходов |
| GET | /applications/{id}/integrations | Технические проверки |
| GET | /monitor | Обезличенные показатели своего tenant; QA/reviewer/officer/admin |
| GET | /health, /ready | Liveness / реальная готовность PostgreSQL |

Документ решения возвращается в карточке как decision_document + decision_hash. 404 скрывает чужие объекты, 403 означает запрет роли, 409 — конфликт состояния/версии/ключа, 422 — валидация/подпись, 413/415 — файл.
