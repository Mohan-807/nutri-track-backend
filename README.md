# Nutri Tracker Backend

Independent Python/FastAPI backend for the Nutri Tracker app — shares no code with `../frontend`.
Implements auth, profile (BMI/BMR/TDEE/daily targets), a food catalog, and nutrition log entries.
AI/chat endpoints are intentionally not part of this backend yet.

## Stack

FastAPI · SQLAlchemy 2.0 · PostgreSQL (via `psycopg`) · Alembic · JWT (PyJWT) · argon2 password hashing · `uv`

## Setup

1. Install dependencies:
   ```
   uv sync
   ```
2. Configure `.env` (already created with placeholder values — **edit `DATABASE_URL` with your real
   PostgreSQL credentials** before running the live server or migrations):
   ```
   DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/nutri_tracker
   SECRET_KEY=<a real secret — see below>
   ```
   Generate a secret key:
   ```
   uv run python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. Create the database schema (requires your Postgres server to be running and reachable via
   `DATABASE_URL`):
   ```
   uv run alembic upgrade head
   ```
4. Seed the starter food catalog (idempotent — safe to re-run):
   ```
   uv run seed-foods
   ```
5. Run the dev server:
   ```
   uv run uvicorn app.main:app --reload
   ```
   Interactive API docs: http://localhost:8000/docs

## Tests

The test suite never touches Postgres or Alembic — it runs against a throwaway in-memory SQLite
database created directly from the SQLAlchemy models (`Base.metadata.create_all()`), so it works
even before you've configured real Postgres credentials:
```
uv run pytest
uv run ruff check .
```

## Migrations

`alembic/env.py` always reads `DATABASE_URL` from `.env` (via `app.config.Settings`) — never edit
`alembic.ini`'s connection string directly. To create a new migration after changing a model:
```
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

The very first migration (`alembic/versions/..._initial_schema.py`) was generated against a
temporary local SQLite file (no Postgres was available in the environment that built this
backend) and hand-verified — every column uses a portable SQLAlchemy type (no Postgres-only
`ARRAY`/`ENUM`), so it applies identically to real Postgres. All migrations after this one should
be generated directly against your real Postgres dev database.

## API overview

All routes except `/auth/signup` and `/auth/login` require `Authorization: Bearer <token>`.
Full interactive reference at `/docs` once the server is running.

| Router | Routes |
|---|---|
| `/auth` | `POST /signup`, `POST /login`, `GET /me` |
| `/profile` | `GET /me`, `POST /onboarding`, `PUT /me` |
| `/foods` | `GET /` (`?query=`), `GET /{id}`, `POST /` |
| `/logs` | `GET /{date}`, `POST /{date}`, `PATCH /{date}/{entry_id}`, `DELETE /{date}/{entry_id}`, `GET /dates` |

## Project layout

```
app/
  main.py          FastAPI app, CORS, router mounting
  config.py        .env-driven settings
  database.py      engine/session, SQLite foreign-key pragma
  security.py      password hashing (argon2) + JWT
  dependencies.py  get_current_user
  constants.py     activity multipliers / goal config (mirrors the frontend's constants)
  models/          SQLAlchemy models: User, Profile, Food, LogEntry
  schemas/         Pydantic request/response models (camelCase JSON, snake_case Python)
  routers/         auth, profile, foods, logs
  services/        nutrient_calc, food_service, log_service — the actual business logic

alembic/           migrations (targets real Postgres)
scripts/seed_foods.py   populates the food catalog from data/seed_foods.json
tests/             pytest suite (SQLite-backed, no external services needed)
```
