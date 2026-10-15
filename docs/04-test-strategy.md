# Тестовая стратегия Stage 1

**Scope:** auth/RBAC/tenant, агрегат заявления, файлы, ревизии, HMAC, идемпотентность, review, завершение, аудит и PostgreSQL-транзакции. Stage 2 integration faults, broker recovery, SLA, mutants и LMS — не проверены.

**Приоритет:** P0 — tenant isolation/повышение прав; P1 — потеря/дублирование бизнес-результата, подписи, гонки; P2 — валидация и UI. Останавливать релиз при утечке tenant, обходе подписи, неконсистентной транзакции или невоспроизводимом critical regression.

**Уровни:** доменные проверки запрещённых переходов; API/SQL на настоящей PostgreSQL; конкурентные 10 submit и 5 PATCH; OpenAPI контракт; три Playwright сценария на собранном Docker UI. SQLite не используется. Каждый pytest case получает очищенные бизнес-таблицы и новый FastAPI app. Suite мигрирует отдельную временную БД и удаляет её по завершении.

**Данные:** UUID5 от seed=42 для tenants/users, синтетические строки, PDF fixtures. Пользователи tenant A/B и два applicant в tenant A. Секреты тестов независимы от demo `.env`. Крупным fixtures назначены короткие test IDs, чтобы не превышать лимит environment variables Windows.

**Методы:** state transition coverage, boundary values, equivalence classes для MIME/JWT/ролей, optimistic concurrency, atomic rollback, повторная доставка local task. Параллельные запросы запускаются ThreadPoolExecutor; фиксированных sleep для API нет. Browser suite ожидает фактический UI-state.

**Evidence:** JUnit XML с именами тестов, результатами и длительностью; demo JSON с request outcome, audit, SQL counts и correlation; браузерные screenshot. HTTP-токены, proof и пароли в evidence не записываются. Автоматический trace с Authorization отключён. В CI сохраняются отчёты даже при сбое.

**Entry:** PostgreSQL доступен, миграция head применяется на чистой БД. **Exit Stage 1:** все critical checks и E2E проходят, локальный Docker ready, artefacts доступны. Это не exit criteria полного R-1.4.

**Расписание:** pytest + Ruff на каждый PR; сборка UI, audit и Playwright в CI; exploratory перед показом (потеря сети, повтор клика, клавиатура, пустой список, фильтры). Автоматизация защищает инварианты; неоднозначную бизнес-политику меняют через ADR.

**Ограничения:** magic bytes не являются полноценной антивирусной/структурной проверкой PDF/PNG. Нагрузочная ёмкость, длительные гонки между процессами, token revocation по jti, доступность уровня WCAG и process-crash recovery требуют отдельных работ. Login throttle локальный процессный, не распределённый. Тесты не обращаются к государственным API.
