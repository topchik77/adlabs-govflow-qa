# Ручная проверка API

Импортировать `govflow.postman_collection.json`. В collection variables задать `password` из локального `.env`. В upload request выбрать `synthetic.png` рядом с коллекцией; Postman не разрешает автоматически читать произвольные файлы хоста. Последовательно выполнить запросы; после submit карточка должна перейти в UNDER_REVIEW перед review. Если обработчик ещё занят, повторить GET latest version.

Коллекция обновляет token/application_id/version/hash локально в Postman. Не экспортировать заполненные переменные с токеном или паролем в репозиторий. Последний шаг проверяет 404 для tenant B. В Swagger Bearer-токен вводится через Authorize; login принимает JSON.

Регенерация без секретов: `python scripts/export_postman.py` из корня проекта. Эта коллекция предназначена для ручного исследования; фактические автоматические результаты находятся в pytest/Playwright reports.
