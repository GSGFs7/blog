# AGENTS.md

## Core Tech Stack

Asynchronous Django + Django-Ninja + pgvector + Celery + HTMX + solid.js + uv/ruff.

## CLI Workflow

```bash
# Setup: podman-compose up -d blog-postgres blog-redis
uv run manage.py migrate                # Database migrations
uv run manage.py test                   # Run tests
ruff check --fix && ruff format .       # Lint and format
```

## Project Map

- `api/`: Main application for business entities and HTTP API.
- `api/models/`: Core models such as posts, pages, comments, categories, anime, galgame, guest.
- `api/routers/`: Django-Ninja routers mounted under `/api/`.
- `api/schemas/`: Request/response schemas for Ninja endpoints.
- `api/tests/`: API and app-level tests, including upload/auth/rate-limit coverage.
- `media_service/`: Dedicated media app for image resources, processing, admin, signals, and tests.
- `blog/settings.py`: Global settings, environment detection, Redis/Celery/database configuration.
- `web/`: Frontend, powered by django template & HTMX & solid.js
- `scripts/`: Deployment, backup/restore, model download, embedding regeneration, and env/build helpers.

## Documentation & Comments

- **Minimize Comments**: Write self-documenting code. Avoid adding new comments unless the logic is extremely complex.
- **Preserve Existing**: Do not modify or remove existing comments unless the underlying logic has changed and the comment is now incorrect.
- **No Docstrings**: Avoid adding new docstrings for internal methods or straightforward API endpoints.

## Troubleshooting

- **Sandbox Environment Check**: If you cannot connect to the database, Redis, or other local services, first check if you are running in a restricted sandbox environment (e.g., a terminal sandbox that blocks network or host access) and request necessary permissions (e.g., `unsandboxed` command action) or run the commands accordingly.
