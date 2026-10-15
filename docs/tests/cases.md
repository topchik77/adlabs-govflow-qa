# Тест-кейсы Stage 1

Общее окружение: PostgreSQL 16, Alembic head, baseline build 0.1.0, seed=42. Tenants A/B, роли из role matrix; данные исключительно синтетические. API setup/cleanup реализован fixtures в `tests/conftest.py`: отдельная БД suite, очистка бизнес-таблиц перед кейсом. API evidence — `reports/pytest.xml`, HTTP/SQL asserts в соответствующем test; UI evidence — `reports/playwright.xml` и screenshots. Имена автопроверок и требования связаны в `traceability.csv`. Severity найденного дефекта оценивается отдельно от priority кейса. BUG-ID не присваивается без воспроизведения дефекта на контролируемом mutant.

| TC-ID | REQ / INV | Приоритет / тип | Предусловия и данные | Шаги | Expected / evidence | Cleanup |
|---|---|---|---|---|---|---|
| TC-001 | INV-03 | P0 API/security | A создал заявку, B знает UUID | GET карточка/audit/integrations/download как applicant/reviewer/officer/admin B и applicant2 A | 404 без данных; list.total=0 | fixture |
| TC-002 | INV-02 | P1 concurrency/SQL | Актуальная подписанная заявка | 10 параллельных POST submit, один key/payload | Все 202 с одинаковым snapshot; SQL 1 SUBMITTED, 1 check | fixture |
| TC-003 | INV-02 | P1 API | Сохранённый submit key | Повторить key с другой expected_version | 409 IDEMPOTENCY_CONFLICT | fixture |
| TC-004 | INV-07 | P1 integrity | Подпись на revision N | PATCH форму, submit, sign со старым hash | N+1; подпись не текущая; SIGNATURE_INVALID / HASH_MISMATCH | fixture |
| TC-005 | FR-AUTH-04 | P0 API/security | UNDER_REVIEW в A | Review от reviewer B | 404, version без изменений в SQL | fixture |
| TC-006 | FR-APP-06 | P1 API/SQL | Черновик v1 | PATCH v1, второй PATCH v1 с другим title | 409 VERSION_CONFLICT, 2 ревизии, title первого PATCH | fixture |
| TC-007 | FR-APP-05 | P1 concurrency | Черновик v1 | 5 параллельных PATCH expected v1 | Один 200, четыре 409 | fixture |
| TC-008 | FR-SIGN-05 | P1 integrity/SQL | Подготовлен документ | sign с 64 нулями вместо hash | 422 DOCUMENT_HASH_MISMATCH, 0 signatures | fixture |
| TC-009 | INV-01 | P1 E2E/API/SQL | Чистая БД, PDF fixture | Create→attach→sign→submit→review→officer sign | COMPLETED, 2 signer UUID, 1 notification, непрерывный audit | fixture |
| TC-010 | INV-05 | P1 state machine | Завершённое/отменённое/отклонённое | Cancel и PATCH каждого terminal | 409; status/version не меняются | fixture |
| TC-011 | FR-APP-03 | P2 validation/SQL | Черновик | Upload HTML с text/html | 415 UNSUPPORTED_MEDIA_TYPE, 0 attachments | fixture |
| TC-012 | FR-APP-03 | P1 security/SQL | Черновик | Upload fake.pdf с произвольными байтами | 415 CONTENT_TYPE_MISMATCH, 0 attachments | fixture |
| TC-013 | FR-APP-03 | P1 security/SQL | Черновик | Upload ../escape.pdf | 422 UNSAFE_FILENAME, 0 attachments | fixture |
| TC-014 | FR-APP-03 | P2 boundary/SQL | Черновик | Upload PDF 5 MiB+5 bytes | 413 ATTACHMENT_TOO_LARGE, версия та же | fixture |
| TC-015 | FR-AUTH-02 | P0 JWT | Активный applicant | GET list без токена/invalid/expired/HS384/no jti/role spoof | 401 для всех классов | fixture |
| TC-016 | FR-AUTH-03 | P0 security | Валидный выданный JWT | Отключить user или tenant, GET me | 401 для ранее выданного JWT | fixture |
| TC-017 | FR-AUTH-05 | P1 auth | Seed с Argon2 password_hash | Login неверный/верный пароль | 401 без отражения секрета; 200 JWT с sub/tenant/role/exp/jti | fixture |
| TC-018 | FR-APP-02 | P0 mass assignment | Активный applicant | POST с чужим tenant_id и COMPLETED | 422, list.total=0 | fixture |
| TC-019 | FR-AUTH-03 | P1 RBAC | Reviewer/officer/admin/QA | Create заявление каждой служебной ролью | 403 | fixture |
| TC-020 | FR-SIGN-01 | P1 integrity | Подготовленная заявка без подписи | Submit | 422 SIGNATURE_INVALID, no check/no version change | fixture |
| TC-021 | FR-SIGN-02 | P1 integrity | Сохранена HMAC signature | Изменить proof в test DB, submit | 422 SIGNATURE_INVALID | fixture |
| TC-022 | FR-APP-01 | P0 pagination/SQL | B + 3 DRAFT A | List A limit1 offset1 oldest status DRAFT | Только второй элемент A, total=3 | fixture |
| TC-023 | FR-REV-02 | P1 business/RBAC | DRAFT, затем UNDER_REVIEW | Review до проверки; пустая причина; officer review | 409, 422, 403 соответственно | fixture |
| TC-024 | FR-SIGN-04 | P1 RBAC/integrity | Одобренное решение | Sign-decision reviewer/applicant/officer с hash заявления | 403/403/422 | fixture |
| TC-025 | FR-APP-04 | P1 business | UNDER_REVIEW | Correction→edit→prepare→sign→submit новым ключом | Новая revision, обязательная подпись, снова UNDER_REVIEW; история review сохранена | fixture |
| TC-026 | FR-AUTH-01 | P0 privacy | Одна проверенная заявка | QA GET list/card/monitor | 403/403/200; monitor без UUID и title | fixture |
| TC-027 | INV-04 | P1 event ordering | AWAITING_OFFICER_SIGNATURE | Повторить local_process с прежним application UUID | State/version те же; SQL check count=1 | fixture |
| TC-028 | FR-EXT-06 | P1 transaction | Черновик и 1 audit/outbox | Transition в транзакции, controlled exception перед commit | Откат статуса, audit/outbox count=1 | fixture |
| TC-029 | FR-APP-05 | P1 state machine | Все 11 статусов | Для каждого статуса вызвать все запрещённые переходы | Каждый INVALID_TRANSITION | fixture |
| TC-030 | FR-AUDIT-01 | P1 contract | API reference | OpenAPI submit schema, X-Correlation-ID, ready | Typed ApplicationView, required Idempotency-Key, 202; correlation возвращён; DB ready | fixture |
| TC-031 | FR-UI-02 | P1 UI/E2E | Запущенный demo, три роли A | Через UI создать, upload, sign, submit; первый GET=snapshot SUBMITTED, затем автоматический UNDER_REVIEW; review, sign decision, audit | COMPLETED, 10 audit событий, screenshot; регрессия BUG-UI-001 | Синтетическое заявление остаётся; reset локально |
| TC-032 | FR-UI-05 | P2 responsive/UI | Applicant B, viewport390×844 | Поиск несуществующего названия | Пустое состояние; scrollWidth≤viewport | Сброс поиска |
| TC-033 | FR-UI-04 | P1 UI/privacy | QA observer A | Войти, открыть монитор | Реальные данные local-reference; list/review nav disabled | Logout |

Дополнительные pytest asserts: стабильные seed UUID, отсутствие секретов в monitor/validation errors, валидация длины полей. Настоящие registry 503, retry exhaustion, DLQ, lost notification delivery и mutant effectiveness не покрыты этой версией.
