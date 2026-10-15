# Контракт Stage 1

## Матрица ролей

| Операция | applicant | reviewer | officer | tenant_admin | qa_observer |
|---|---|---|---|---|---|
| Создание, редактирование, вложение, подпись, submit, cancel | Только владелец | — | — | — | — |
| Чтение заявления | Только владелец | Свой tenant | Свой tenant | Свой tenant | Только обезличенный монитор |
| Review | — | Свой tenant | — | — | — |
| Подпись решения | — | — | Свой tenant, другой пользователь | — | — |
| Аудит | Своё, без actor ID | Свой tenant | Свой tenant | Свой tenant | Через обезличенный монитор |

Запрет по умолчанию. Чужой tenant, неизвестный UUID и чужой владелец для applicant → 404. Неподходящая роль → 403; стадия/версия → 409. Массовое присваивание запрещено схемами extra=forbid. Сортировка и фильтрация применяются после tenant/owner-фильтра, до LIMIT/OFFSET.

## State machine

| Из | В | Кто/условие |
|---|---|---|
| DRAFT | AWAITING_APPLICANT_SIGNATURE | Владелец, обязательные поля + файл |
| AWAITING_APPLICANT_SIGNATURE | SUBMITTED | Владелец, актуальная валидная подпись |
| SUBMITTED | VALIDATING | Локальный системный обработчик Stage 1 |
| VALIDATING | UNDER_REVIEW | Только успешная синтетическая проверка |
| UNDER_REVIEW | NEEDS_CORRECTION / APPROVED / REJECTED | Reviewer, причина обязательна |
| NEEDS_CORRECTION | AWAITING_APPLICANT_SIGNATURE | Владелец, новая документная ревизия |
| APPROVED | AWAITING_OFFICER_SIGNATURE | Система готовит решение |
| AWAITING_OFFICER_SIGNATURE | COMPLETED | Officer, подпись решения |
| DRAFT / NEEDS_CORRECTION | CANCELLED | Владелец |

Редактирование и добавление вложений разрешены в DRAFT, NEEDS_CORRECTION и AWAITING_APPLICANT_SIGNATURE. В последнем состоянии прежняя подпись перестаёт авторизовать отправку: документная ревизия растёт, статус сохраняется. Историческая запись подписи остаётся evidence старой версии. Это явное уточнение таблицы исходного ТЗ: повторное подписание обязательно. В остальных состояниях документ неизменяем. Терминальные состояния неизменяемы.

application.version растёт при каждой существенной команде/переходе, audit содержит ровно одну запись на версию. document_version растёт только при изменении формы/вложений; HMAC привязан к document_version, хешу байтов файлов, канонической форме и signer_id. Повторная отправка использует новый Idempotency-Key после исправления.

## 10 критических acceptance criteria

| ID | Требования | Проверка |
|---|---|---|
| AC-01 | INV-01, FR-SIGN-04 | E2E завершается только после подписей applicant и отдельного officer |
| AC-02 | INV-03, FR-AUTH-04 | Чужой tenant/владелец: 404 во всех object endpoints и отсутствие в списке |
| AC-03 | FR-AUTH-01/02 | Неверный, истёкший JWT, выключенный user/tenant: 401; роль не повышается из payload |
| AC-04 | FR-APP-05/06 | Старая expected_version: 409 VERSION_CONFLICT, без изменений |
| AC-05 | INV-07 | Edit меняет revision/hash, старая подпись не позволяет submit |
| AC-06 | INV-02 | Одинаковый key/payload возвращает исходный 202; другой payload: 409; конкурентные submit дают один эффект |
| AC-07 | FR-REV-01/02 | Review только после проверки; причина непустая; одно актуальное решение на цикл |
| AC-08 | FR-APP-03 | PDF/PNG ≤5 MiB, magic bytes проверяются, опасный filename отклоняется |
| AC-09 | INV-04/05, FR-AUDIT-01 | Непрерывный аудит, версии монотонны, терминальная запись неизменяема |
| AC-10 | INV-09, FR-EXT-03 | Ошибки с correlation_id без секретов; временная ошибка не является отказом в услуге |

AC-10 в Stage 1 проверяет модель/состояния; настоящий 503/retry/DLQ требует Stage 2. Это ограничение выпуска.
