# ADR-001: контракт ядра и границы Stage 1

**Status:** Accepted (решение реализации в рамках поручения)
**Date:** 2026-10-15
**Deciders:** исполнитель проекта; изменение бизнес-политик — владелец ADLabs

## Context

Нужно сначала доказать один процесс без дополнительных сервисов. ТЗ требует разрешить неоднозначности reviewer/officer, версии подписи и 503 до frontend.

## Decision

1. Reviewer и officer — разные роли/учётные записи. Reviewer фиксирует решение; только officer завершает услугу. Applicant никогда не может подписать решение своего заявления.
2. Счётчик application.version защищает все команды, отдельный document_version защищает подписанные байты. Вложение/редактирование инвалидирует подпись даже на стадии ожидания подписи. Сохранённая HMAC проверяется заново на submit.
3. Временный сбой интеграции оставляет VALIDATING и отдельный RETRYING/FAILED_PERMANENTLY; не REJECTED. В Stage 1 внешней сети нет: прозрачный local-reference adapter возвращает VALID. Запуск после submit через FastAPI BackgroundTasks; это не надёжная очередь. Перезапуск между commit и background task может оставить SUBMITTED. Диагностируется монитором; исправление доставкой outbox — Stage 2.
4. PostgreSQL SELECT FOR UPDATE + expected_version сериализуют команды на агрегате. Идемпотентность submit: user + application + key, hash полного payload, сохранённый ответ. Проверка повтора после блокировки, до проверки версии. Аудит, события outbox и бизнес-изменение коммитятся вместе. Outbox пока не публикуется.
5. Один reviewer может принять решение: блокировка агрегата + версия дают первому commit право на текущий цикл; отдельного долгоживущего claim нет.

## Options considered

| Выбор | Сложность | Стоимость | Масштабирование | Освоенность |
|---|---|---|---|---|
| FastAPI + PostgreSQL + local adapter | Низкая | Локальный Docker | Один процесс | Простая проверка SQL/HTTP |
| Сразу RabbitMQ + Registry + worker | Средняя | Ещё 3 процесса | Надёжная доставка | Требует отдельной failure suite |
| SQLite как основная БД | Низкая | Минимальная | Нет row-level locks | Недостаточно для конкурентных гарантий |

## Trade-off analysis

Первый вариант даёт проверяемые границы auth/version/signature; второй выбран для Stage 2 после reference baseline. SQLite не используется как доказательство PostgreSQL-конкурентности.

## Consequences

Процесс воспроизводим локально. Нельзя заявлять retries, DLQ, recovery, независимый Registry или готовую интеграцию WorkLab. Контракт ошибок, аудит и outbox обеспечивают точку расширения.

## Action items

1. [x] Зафиксировать state machine, role matrix и критерии.
2. [x] Реализовать и проверить baseline на PostgreSQL: 49 backend checks + 3 browser scenarios.
3. [ ] Stage 2: RabbitMQ, отдельный Registry, outbox dispatcher, inbox, retries/DLQ.
