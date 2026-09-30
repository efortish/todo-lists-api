"""FastAPI dependency wiring: builds use cases from request-scoped adapters."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.api.errors import RateLimitedError
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.task_lists import TaskListUseCases
from app.application.use_cases.tasks import TaskUseCases
from app.domain.entities import User
from app.infrastructure.db.repositories import (
    SqlTaskListRepository,
    SqlTaskRepository,
    SqlUserRepository,
)
from app.infrastructure.security import JwtTokenService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_session(request: Request) -> Iterator[Session]:
    """Open one database session per request."""
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def rate_limit_auth(request: Request) -> None:
    """Throttle auth endpoints per client IP and path (brute force, enumeration, spam)."""
    client_ip = request.client.host if request.client else "unknown"
    retry_after = request.app.state.auth_rate_limiter.hit(f"{request.url.path}|{client_ip}")
    if retry_after is not None:
        raise RateLimitedError(retry_after)


def get_auth_use_cases(request: Request, session: SessionDep) -> AuthUseCases:
    settings = request.app.state.settings
    return AuthUseCases(
        users=SqlUserRepository(session),
        hasher=request.app.state.password_hasher,
        tokens=JwtTokenService(
            settings.jwt_secret, settings.jwt_algorithm, settings.access_token_expire_minutes
        ),
        notifier=request.app.state.notifier,
    )


AuthUseCasesDep = Annotated[AuthUseCases, Depends(get_auth_use_cases)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], auth: AuthUseCasesDep) -> User:
    """Resolve the bearer token into a user, or fail with 401."""
    return auth.authenticate(token)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_task_list_use_cases(request: Request, session: SessionDep) -> TaskListUseCases:
    return TaskListUseCases(
        task_lists=SqlTaskListRepository(session),
        users=SqlUserRepository(session),
        notifier=request.app.state.notifier,
    )


def get_task_use_cases(request: Request, session: SessionDep) -> TaskUseCases:
    return TaskUseCases(
        task_lists=SqlTaskListRepository(session),
        tasks=SqlTaskRepository(session),
        users=SqlUserRepository(session),
        notifier=request.app.state.notifier,
    )


TaskListUseCasesDep = Annotated[TaskListUseCases, Depends(get_task_list_use_cases)]
TaskUseCasesDep = Annotated[TaskUseCases, Depends(get_task_use_cases)]
