"""Application factory. Run with ``uvicorn --factory app.main:create_app``."""

import logging

from fastapi import FastAPI
from sqlalchemy import text

from app.api.errors import register_error_handlers
from app.api.middleware import BodySizeLimitMiddleware, add_security_headers
from app.api.routers import auth, task_lists, tasks
from app.config import Settings, get_settings
from app.infrastructure.db.session import build_engine, build_session_factory
from app.infrastructure.notifications import LoggingEmailNotifier
from app.infrastructure.rate_limit import RateLimiter
from app.infrastructure.security import ScryptPasswordHasher

DESCRIPTION = """
REST API to manage **task lists** and the **tasks** inside them.

### How to try it
1. `POST /api/v1/auth/register` to create an account.
2. Click **Authorize** (top right) and log in with your email and password.
3. Create a task list, add tasks, filter them and watch `completion_percentage`.
4. To see lists others share with you, verify your email: the token is in the
   (simulated) email printed in the API logs, send it to `POST /api/v1/auth/verify-email`.

### Conventions
* Every business error returns `{"code": "...", "message": "..."}` with a stable `code`.
* Lists you cannot access answer **404**, so their existence is not revealed.
* Verification, invitation and assignment emails are **simulated**: they are written to
  the app log.
* Auth endpoints are rate limited per client IP (`429` with `Retry-After`).
"""

TAGS = [
    {"name": "Auth", "description": "Registration and JWT login."},
    {"name": "Task lists", "description": "Create, share and manage task lists."},
    {"name": "Tasks", "description": "Tasks inside a list: CRUD, status, filters, assignment."},
    {"name": "Health", "description": "Liveness and database readiness probe."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application and its infrastructure from ``settings``."""
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    docs = settings.docs_enabled
    app = FastAPI(
        title="Todo Lists API",
        version="1.0.0",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    engine = build_engine(settings.database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.notifier = LoggingEmailNotifier()
    app.state.password_hasher = ScryptPasswordHasher()
    app.state.auth_rate_limiter = RateLimiter(settings.auth_rate_limit_per_minute)

    register_error_handlers(app)
    add_security_headers(app)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    for router in (auth.router, task_lists.router, tasks.router):
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", tags=["Health"], summary="Health check")
    def health() -> dict[str, str]:
        """Return `ok` when the process is up and the database answers."""
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app
