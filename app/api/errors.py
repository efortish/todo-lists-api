"""Translation of domain exceptions into HTTP responses."""

import math

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.application.schemas import ErrorResponse
from app.domain.exceptions import (
    AuthenticationError,
    BusinessRuleViolationError,
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
)

_STATUS_BY_CATEGORY: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    BusinessRuleViolationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}

_DESCRIPTIONS = {
    401: "Missing, invalid or expired access token.",
    403: "Authenticated, but only the list owner may do this.",
    404: "The resource does not exist or you do not have access to it.",
    409: "Conflicts with the current state (duplicate name, finished task, ...).",
    422: "Invalid input or a broken business rule.",
    429: "Too many requests from this client. Retry after `Retry-After` seconds.",
}


class RateLimitedError(Exception):
    """Raised by the rate limiting dependency; rendered as 429 with ``Retry-After``."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("rate limited")
        self.retry_after = max(1, math.ceil(retry_after))


def error_responses(*codes: int) -> dict[int | str, dict]:
    """OpenAPI ``responses`` entries documenting the error body for ``codes``."""
    return {code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]} for code in codes}


def _error(status_code: int, code: str, message: str, **kwargs) -> JSONResponse:
    body = ErrorResponse(code=code, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body, **kwargs)


async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
    status_code = next(
        (code for category, code in _STATUS_BY_CATEGORY.items() if isinstance(exc, category)),
        status.HTTP_400_BAD_REQUEST,
    )
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return _error(status_code, exc.code, exc.message, headers=headers)


async def _handle_integrity_error(_request: Request, _exc: IntegrityError) -> JSONResponse:
    # Safety net for races that slip past the use-case checks (e.g. two identical
    # registrations at once): the database constraint wins, the client gets a 409.
    return _error(
        status.HTTP_409_CONFLICT, "conflict", "The request conflicts with existing data."
    )


async def _handle_rate_limited(_request: Request, exc: RateLimitedError) -> JSONResponse:
    return _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limited",
        f"Too many requests. Retry in {exc.retry_after} seconds.",
        headers={"Retry-After": str(exc.retry_after)},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)
    app.add_exception_handler(IntegrityError, _handle_integrity_error)
    app.add_exception_handler(RateLimitedError, _handle_rate_limited)
