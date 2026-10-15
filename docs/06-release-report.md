# Release QA Summary — build 0.1.0

**Дата:** 15 октября 2026. **Scope:** Stage 0 + Stage 1 reference baseline. **Автор решения:** реализация/локальная верификация; это не внешний signoff ADLabs.

## Результат

**Go для локальной демонстрации Stage 1. No-Go для полного R-1.4 и публичного production.** Критический бизнес-путь проходит; Stage 2–4 ещё не реализованы, а восстановление после process crash не гарантировано.

| Проверка | Результат | Evidence |
|---|---|---|
| API/SQL/domain/concurrency на Windows, Python 3.14 | 49 passed | `reports/pytest.xml` |
| Тот же suite в Docker Linux, Python 3.12 + PostgreSQL 16 | 49 passed | `reports/pytest-docker.xml` |
| Playwright Chromium: сквозной UI, mobile, observer | 3 passed | `reports/playwright.xml` |
| TypeScript + Vite production build | Passed | Запускаемая команда `npm run build` |
| Ruff | Passed | `ruff check services scripts tests` |
| Миграция и отсутствие schema drift | Passed | `alembic ... upgrade head`, `alembic ... check` |
| Traceability | 33 cases, все ссылки на существующие tests | `docs/tests/traceability.csv`, `scripts/check_traceability.py` |
| Docker Compose app/db readiness | Healthy | `docker compose ps`, `/api/v1/ready` |
| Реальные demo-примеры | 5 состояний, включая COMPLETED с 2 подписями | `reports/demo-evidence.json` (HTTP/audit/SQL counts) |
| Fresh public clone + новая БД | Passed: Docker configuration, ready, login, create/persist | `reports/fresh-clone-verification.json` |
| GitHub Actions Docker regression/E2E | 49 + 3 passed | `reports/ci/verification.json` |
| npm dependency audit | 0 известных уязвимостей на момент локальной проверки | `npm audit` |

Первый удалённый [GitHub Actions прогон](https://github.com/topchik77/adlabs-govflow-qa/actions/runs/38739137150) прошёл PostgreSQL regression и выявил UI race. Дефект [BUG-UI-001](defects/BUG-UI-001.md) воспроизведён детерминированным сценарием и исправлен; локальный повторный прогон: 3 passed. Повторный [CI-прогон 38740643670](https://github.com/topchik77/adlabs-govflow-qa/actions/runs/38740643670) завершился успешно на commit `0cab5b5`: 49 backend checks и 3 browser scenarios. [Raw JUnit и source manifest](../reports/ci/verification.json) сохранены из GitHub artifact; timestamp и source commit проверены. Отчёт backend выгружается до пересоздания контейнера, чтобы не подменять его локальным примером. Локальные результаты и результаты CI учитываются отдельно.

## Покрытые критические риски

Другой tenant и другой владелец не получают карточку, audit, проверки или файл. JWT expiry/algorithm/role подмена отклоняются. Роли разделены: applicant не принимает review, reviewer не подписывает решение. Одновременно отправленные 10 одинаковых submit дают одно событие SUBMITTED и одну проверку; повторный ответ совпадает с сохранённым snapshot. Из пяти конкурентных PATCH проходит один. Stale version, недопустимый transition, неправильный хеш и повреждённый HMAC не меняют состояние. В каждом успешном переходе аудит и outbox коммитятся вместе; controlled exception откатывает всё. Терминальные статусы неизменяемы.

## Не проверено / release blockers полного продукта

- Независимый HTTP Registry, RabbitMQ, outbox dispatcher/inbox, retry/backoff/DLQ и recovery после падения отсутствуют. BackgroundTasks может оставить SUBMITTED при остановке процесса.
- Внешние уведомления отсутствуют; есть только уникальная запись LOCAL_INBOX.
- Нет mutants/Fault Engine; 5 баг-репортов и mutation effectiveness не заявляются. Отдельно задокументирован один реальный UI-дефект BUG-UI-001, обнаруженный в CI и воспроизведённый на исходной сборке.
- WorkLab lab API, grader, изоляция learner runs, Markdown LMS и виртуальное SLA не реализованы.
- Нет нагрузочного benchmark, антивируса файлов, полноценного security audit или сертификата доступности.
- В подписи используется учебный HMAC. Свойства юридической ЭЦП не заявляются.

Известное предупреждение test stack: Starlette использует deprecated AnyIO BlockingPortal alias; оно не влияет на текущие 49 asserts. Обновление framework stack требует отдельного совместимого regression run.

Следующий release gate: реализовать Stage 2 и подтвердить 503→retry→success, exhaustion→DLQ, duplicate/out-of-order delivery и crash recovery на baseline до внедрения учебных mutants.
