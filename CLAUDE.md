# CLAUDE.md

## 言語設定
- Respond terse like smart caveman. All technical substance stay. Only fluff die.
- 常に日本語で会話する
- コメントも日本語で記述する
- エラーメッセージの説明も日本語で行う
- ドキュメントも日本語で生成する
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run locally
python main.py                          # uvicorn on 0.0.0.0:8000 with --reload

# Docker
docker-compose up                       # full stack (requires SECRET_KEY in .env)

# Tests
pytest                                  # full test suite (uses in-memory SQLite)
pytest -q                               # quiet mode

# Utilities
python app/generate_thumbs.py           # batch-regenerate thumbnails for existing uploads
```

## Architecture

FastAPI REST API for an illustration-sharing web app. Recently migrated from Flask; old code is archived in `flask_legacy/` (not executed, reference only).

**Key directories:**
- `app/` — main application package
  - `main.py` — app factory, CORS, static file mounts, Jinja2 template routes, lifespan hook
  - `db.py` — SQLAlchemy engine/session + all three ORM models (`User`, `Post`, `Like`)
  - `schemas.py` — Pydantic schemas for request/response validation
  - `image_service.py` — image validation, Pillow processing, thumbnail generation
  - `routers/auth.py` — register, login, logout (JWT HS256, 30-min expiry)
  - `routers/posts.py` — CRUD, image upload, like toggle
  - `routers/search.py` — title search
- `templates/` — Jinja2 HTML templates (SSR pages: `/`, `/login`, `/register`, `/upload`, `/post/{id}`, `/search`)
- `static/` — CSS and uploaded images (`uploads/`), thumbnails (`uploads/thumbs/`)
- `tests/` — integration tests; `conftest.py` sets up in-memory SQLite + `TestClient`

**URL layout:**
- Template routes: `/`, `/login`, `/register`, `/upload`, `/search`, `/post/{id}`, `/health`
- API routes: `/auth/*`, `/posts/*`, `/search` (JSON)

## Auth flow

JWT token issued on `POST /auth/login`, passed as `Authorization: Bearer <token>`. The `get_current_user` dependency (in `routers/`) decodes it and injects the current user into protected endpoints. Passwords hashed with bcrypt via `passlib`.

## Database

SQLite (`database.db` in project root) created automatically on startup via `Base.metadata.create_all()`. No migrations tool is active — schema changes require manually updating models in `app/db.py` and re-initializing (drop/recreate or manual ALTER). The README mentions Alembic (`fastapi_app/alembic.ini`) as a future path for PostgreSQL.

Three tables: `users`, `posts` (FK → users), `likes` (FK → users + posts).

## Environment variables

Copy `.env.example` to `.env`. Docker Compose requires `SECRET_KEY` to be set (it uses `${SECRET_KEY:?...}`).

| Variable | Default in code | Notes |
|---|---|---|
| `SECRET_KEY` | `"dev-secret-key-change-in-production"` | Must be changed for production |
| `DATABASE_URL` | `sqlite:///./database.db` | Override for PostgreSQL |
| `APP_ENV` | `dev` | |

## Image handling

`image_service.py` validates extension, MIME type, and pixel dimensions (max 4000×4000). Files are saved with a UUID filename under `static/uploads/`. A 300×300 thumbnail is auto-generated to `static/uploads/thumbs/`. RGBA/P mode images are converted to RGB before saving.
