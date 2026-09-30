"""Use cases for registration, email verification, login and resolving the current user."""

from datetime import timedelta

from app.application.schemas import UserCreate
from app.domain.entities import User
from app.domain.exceptions import (
    EmailAlreadyRegisteredError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.domain.ports import Notifier, PasswordHasher, TokenService, UserRepository

ACCESS = "access"
EMAIL_VERIFICATION = "email_verification"
EMAIL_VERIFICATION_TTL = timedelta(hours=24)


class AuthUseCases:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        notifier: Notifier,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._notifier = notifier

    def register(self, data: UserCreate) -> User:
        """Create an unverified account and email it a verification token.

        Raises:
            EmailAlreadyRegisteredError: if the email is taken.
        """
        email = data.email.lower()
        if self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)
        user = self._users.add(
            User(
                email=email,
                full_name=data.full_name,
                hashed_password=self._hasher.hash(data.password),
            )
        )
        self._send_verification(user)
        return user

    def resend_verification(self, user: User) -> None:
        """Send a fresh verification token to ``user``.

        Raises:
            EmailAlreadyVerifiedError: if there is nothing to verify.
        """
        if user.email_verified:
            raise EmailAlreadyVerifiedError()
        self._send_verification(user)

    def verify_email(self, token: str) -> User:
        """Mark the email behind a verification token as verified. Idempotent.

        Raises:
            InvalidTokenError: if the token is invalid, expired, not a verification token,
                or its user no longer exists.
        """
        user = self._user_from_token(token, EMAIL_VERIFICATION)
        if user.email_verified:
            return user
        user.email_verified = True
        return self._users.update(user)

    def login(self, email: str, password: str) -> str:
        """Return an access token for valid credentials.

        Raises:
            InvalidCredentialsError: if the email is unknown or the password is wrong. Both
                cases share one error and the same hashing cost, so neither the response
                nor its timing reveals which emails are registered.
        """
        user = self._users.get_by_email(email.strip().lower())
        password_ok = self._hasher.verify(password, user.hashed_password if user else None)
        if user is None or not password_ok:
            raise InvalidCredentialsError()
        return self._tokens.issue(str(user.id), ACCESS)

    def authenticate(self, token: str) -> User:
        """Resolve the user behind an access token.

        Raises:
            InvalidTokenError: if the token is invalid, expired, not an access token, or its
                user no longer exists.
        """
        return self._user_from_token(token, ACCESS)

    def _user_from_token(self, token: str, purpose: str) -> User:
        subject = self._tokens.decode(token, purpose)
        user = self._users.get(int(subject)) if subject.isdigit() else None
        if user is None:
            raise InvalidTokenError()
        return user

    def _send_verification(self, user: User) -> None:
        token = self._tokens.issue(str(user.id), EMAIL_VERIFICATION, EMAIL_VERIFICATION_TTL)
        self._notifier.send_email(
            to=user.email,
            subject="Verify your email address",
            body=f"Hi {user.full_name}, confirm your address to access the task lists shared "
            f"with you: POST /api/v1/auth/verify-email with the token {token} "
            f"(valid for {EMAIL_VERIFICATION_TTL.total_seconds() / 3600:.0f} hours).",
        )
