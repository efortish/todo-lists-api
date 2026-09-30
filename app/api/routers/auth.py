"""Registration, email verification and login endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Response, status

from app.api.dependencies import AuthUseCasesDep, CurrentUser, rate_limit_auth
from app.api.errors import error_responses
from app.application.schemas import EmailVerification, Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])
throttled = [Depends(rate_limit_auth)]


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    dependencies=throttled,
    responses=error_responses(409, 429),
)
def register(data: UserCreate, auth: AuthUseCasesDep):
    """Register a new user. Emails are case-insensitive and must be unique.

    A verification token is sent by (simulated) email, visible in the API logs. You can
    use the API right away, but lists shared with you by invitation only become visible
    after verifying the address with `POST /auth/verify-email`.
    """
    return auth.register(data)


@router.post(
    "/verify-email",
    response_model=UserOut,
    summary="Verify your email address",
    dependencies=throttled,
    responses=error_responses(401, 429),
)
def verify_email(data: EmailVerification, auth: AuthUseCasesDep):
    """Confirm ownership of the email with the token received after registering.

    Idempotent: verifying twice returns the same user. Tokens expire after 24 hours.
    """
    return auth.verify_email(data.token)


@router.post(
    "/verify-email/resend",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Resend the verification email",
    dependencies=throttled,
    responses=error_responses(401, 409, 429),
)
def resend_verification(user: CurrentUser, auth: AuthUseCasesDep):
    """Send a new verification token to the current user's email."""
    auth.resend_verification(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/token",
    response_model=Token,
    summary="Log in and get an access token",
    dependencies=throttled,
    responses=error_responses(401, 429),
)
def login(
    username: Annotated[
        str, Form(description="Your account **email**.", examples=["ana@example.com"])
    ],
    password: Annotated[str, Form(json_schema_extra={"format": "password"})],
    auth: AuthUseCasesDep,
):
    """Exchange your email and password for an access token.

    Only two form fields: `username` (your email) and `password`. The field is named
    `username` because that is what the OAuth2 password flow sends, which is what lets
    the **Authorize** button of this page log you in directly. Limited per client IP to
    slow down brute force.
    """
    return Token(access_token=auth.login(username, password))


@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the current user",
    responses=error_responses(401),
)
def me(user: CurrentUser):
    """Return the profile of the authenticated user."""
    return user
