# Venue Map — конструктор карт мероприятий

FastAPI + SQLAlchemy 2 + Pydantic 2. Организатор загружает фото плана, выравнивает его, рисует зоны и точки,
описывает их гибкими полями, привязывает активности и публикует карту. Участники открывают лёгкий вьюер по ссылке/QR
и получают изменения почти мгновенно.

## Запуск
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export VENUE_SECRET_KEY="$(openssl rand -hex 32)"   # обязательно в проде
uvicorn app.main:app --reload
```
- Редактор: http://localhost:8000/app (регистрация создаёт организацию и набор стартовых типов объектов)
- Вьюер: http://localhost:8000/v/{slug}, для своих: `?t=<staff_token>`, «вы здесь»: `?at=<place_id>` (QR-наклейки)
- Документация API: http://localhost:8000/docs
- По умолчанию SQLite (`venue.db`); Postgres: `VENUE_DATABASE_URL=postgresql+psycopg://user:pass@host/db`
- Тесты: `pytest`

## Архитектура классов
```
app/domain/geometry.py   Point | Polygon | Line (Pydantic, discriminated union), координаты 0..1 по подложке
app/domain/fields.py     FieldBase -> Text/LongText/Phone/Email/Url/Number/Bool/Select/MultiSelect/DateTime/
                         TimeRange/Contact; у каждого coerce(); validate_props(), visible_props() (public|staff)
app/models.py            Organization, User | Venue -> Floor -> Place | PlaceType (схема полей)
                         Event -> Activity, Contact, Notice, Revision (снимки) | ChangeLog (аудит)
app/schemas.py           Pydantic-схемы API и Snapshot (то, что получает вьюер)
app/services/            images (ImageStore, выравнивание 4 углов, WebP), snapshot, publisher, bus (SSE)
app/api/                 auth, venues (площадки/этажи/типы/места), events (мероприятия/активности/публикация), public
```
Ключевые идеи: площадка (Venue) отделена от мероприятия (Event); место (Place) отделено от активности (Activity),
поэтому «станция переехала» = смена `place_id` (`POST /api/activities/{id}/move` — сразу публикует и шлёт уведомление);
схему метаданных задаёт пользователь через `PlaceType.fields` и `Event.activity_fields`.

## Поток обновления
`publish` собирает неизменяемый снимок → `Revision` → `head_rev` растёт → SSE `rev` → вьюер читает `/v/{slug}/head`
(кэш 5 с) и `/v/{slug}/snapshots/{rev}.json` (кэш навсегда). За CDN отдавайте `/v/*` и `/media/*`.

## Что не вошло
Автоопределение углов листа и OCR, маршруты между точками и коннекторы этажей, PWA/Service Worker, миграции Alembic,
редактирование вершин готовой геометрии, UI для `activity_fields` и отката ревизий (API есть), Redis вместо in-process шины
(интерфейс `EventBus` тот же), rate limiting и загрузка в S3 (интерфейс `ImageStore`).
