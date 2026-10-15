# Риски Stage 1

| Риск | Impact / вероятность | Контроль / evidence | Остаток |
|---|---|---|---|
| BOLA / tenant leak | Критический / средняя | Object access + SQL tenant before pagination; параметризованные тесты | Будущие endpoints проходят ту же policy |
| Подмена роли/JWT | Критический / средняя | HS256 allow-list, exp/iss/jti, сверка user/tenant/role в БД | JTI revocation и distributed auth — далее |
| Дубликат submit | Высокий / высокая | Row lock, key/payload hash, response snapshot, 10 threads | Несколько процессов проверяются в Stage 2 |
| Stale signature | Высокий / высокая | Отдельная revision, invalidate, verify HMAC | Не квалифицированная ЭЦП |
| Partial commit | Высокий / средняя | State/audit/outbox одна транзакция, controlled rollback test | Публикация брокера пока отсутствует |
| Падение после submit | Высокий / средняя | QA Monitor выявляет SUBMITTED/VALIDATING | Нет durable worker; блокирует production |
| Неверный review actor | Высокий / средняя | Role + tenant + version + successful check | Долгоживущий review claim вне Stage 1 |
| Небезопасный upload | Средний / средняя | 5 MiB, MIME/magic, filename, DB storage | Нет антивируса/полного парсера |
| Публикация lab наружу | Высокий / низкая локально | Bind 127.0.0.1, random secrets, local-only README | Перед hosting нужен отдельный security review |
