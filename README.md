# Etagi Dashboard

FastAPI, PostgreSQL, Alembic и отдельный Wordstat worker. Фронтенд в этот репозиторий не входит.

## Запуск

```bash
cp app/.env.example app/.env
docker compose --env-file app/.env up -d --build
docker compose --env-file app/.env exec api python -m app.scripts.create_admin
```

Перед запуском заполните в `app/.env` пароль БД, `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` и `AUTH_ALLOWED_ORIGINS`.
API: http://127.0.0.1:8000/docs. API и БД публикуются только на loopback.
Для HTTP-разработки задайте `AUTH_COOKIE_SECURE=false`, для production оставьте `true` и настройте HTTPS reverse proxy.
Frontend и API должны использовать одинаковый hostname; не смешивайте localhost и 127.0.0.1.
CORS с credentials разрешён только для заданных origins. Мутации и login требуют разрешённый заголовок `Origin`.
Администратор создаётся интерактивно: пароль не передаётся через аргументы командной строки.

## Обновление

Сначала сделайте backup БД. Volume `postgres_data`, образ PostgreSQL 17 и `DB_PORT` сохранены.
Не выполняйте `down -v`: эта команда удалит данные.
Контейнер `migrate` выполняется до API и worker; при ошибке миграции они не стартуют.
Старые задания без региона завершаются с ошибкой и должны быть созданы заново.
Health: `/api/health`, readiness БД: `/api/ready`.
Worker один: PostgreSQL advisory lock запрещает параллельный запуск второго процесса.
Сбор запускается через API; автоматическое ежедневное расписание пока не добавлено.

## Города

`GET /api/cities` возвращает `yandex_region_id`. Миграция задаёт Саратову `194`, Энгельсу `11147`.
Для нового города задайте регион через `POST /api/cities` или `PATCH /api/cities/{id}`.
`region_id` можно переопределить в запросе сбора и статистики; без региона сбор запрещён.
Город выбирает каталог фраз, а регион ограничивает географию Wordstat — это разные фильтры.

## Сбор и сравнение

`POST /api/collections`:

```json
{"city_id":"saratov","method":"dynamics"}
```

По умолчанию запрашиваются вчера и позавчера в `REPORTING_TIMEZONE` (Europe/Saratov).
Можно передать `date_from`, `date_to`, `category_id`, `region_id`.
API принимает завершённые дни в пределах последних 59 дней.
Для Wordstat календарные даты кодируются как начало дня UTC.
`method: "topRequests"` сохраняет семантику частоты за последние 30 дней, а не за сутки.
Одинаковые активные задания отклоняются с 409; временные сетевые/429/5xx ошибки ограниченно повторяются.
401/403 и 429 после повторов останавливают запуск; ошибка отдельной фразы не блокирует остальные.

`GET /api/statistics/daily?city_id=saratov` сравнивает вчера с позавчера.
`metric_date=YYYY-MM-DD` выбирает основной день; предыдущий на один день раньше.
Ответ: `current_count`, `previous_count`, `delta`, `delta_percent`, `trend`, даты, регион,
`comparison_status`, пагинированные `items`, агрегаты `categories` по всему фильтру, а не только странице.
Бэкенд считает динамику; фронтенд показывает готовые значения и стрелки.
Пропуски — `null`, не ноль; при росте от нуля процент не вычисляется.
Изменение текста фразы, категории, города или региона исключает несовместимые точки из сравнения.
Сумма частот пересекающихся фраз не является числом уникальных поисков.
Статусы `partial` и `no_data` нужно показывать явно, а не как падение спроса.
Доступность реальных дней зависит от поставщика; без ответа Wordstat данные не подставляются.

`GET /api/collections/{id}/results` принимает `limit`, `offset`, `include_raw`.
Без `include_raw` тяжёлый JSON не загружается из БД.
`/api/dashboard/categories` не смешивает регионы и старые нерегиональные сборы.

## Проверки

```bash
pip install -r requirements-dev.txt
ruff check app tests migrations
python -m pytest -q
```

Интеграционные тесты удаляют данные каталога и сборов. Запускайте их только в отдельной тестовой БД:

```bash
alembic upgrade head
RUN_DB_TESTS=1 python -m pytest -q
alembic check
```

На опубликованной ветке локально проверены 31 тест (включая 6 интеграционных), lint,
`upgrade head → downgrade base → upgrade head`, отсутствие schema drift и `docker compose config`.
Полная сборка и запуск контейнеров в этой среде не проверены: Docker daemon недоступен.
Реальный Wordstat в тестах заменён HTTP mock; проверка боевого ключа и наличия данных не выполнялась.
GitHub Actions дополнительно выполняет `docker build`; перед деплоем проверьте результаты CI.
