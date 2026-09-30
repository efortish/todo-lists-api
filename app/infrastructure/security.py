"""Password hashing and JWT adapters."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import cached_property

import jwt

from app.domain.exceptions import InvalidTokenError


class ScryptPasswordHasher:
    """Salted scrypt from the standard library, encoded as ``scrypt$n$r$p$salt$hash``.

    Defaults (n=2**14, r=8, p=5) follow the OWASP Password Storage Cheat Sheet while
    keeping memory at 16 MiB per hash, so concurrent logins cannot exhaust RAM.
    Storing the parameters in the hash lets them be raised later without
    invalidating existing passwords.
    """

    def __init__(self, n: int = 2**14, r: int = 8, p: int = 5) -> None:
        self._n, self._r, self._p = n, r, p

    @cached_property
    def _dummy_hash(self) -> str:
        # Verified against when the user does not exist, to equalise response times.
        return self.hash(secrets.token_urlsafe(16))

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = self._derive(password, salt, self._n, self._r, self._p)
        return f"scrypt${self._n}${self._r}${self._p}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, hashed: str | None) -> bool:
        if hashed is None:
            self.verify(password, self._dummy_hash)
            return False
        try:
            scheme, n, r, p, salt, digest = hashed.split("$")
            expected = bytes.fromhex(digest)
            actual = self._derive(password, bytes.fromhex(salt), int(n), int(r), int(p))
        except ValueError:
            return False
        return scheme == "scrypt" and hmac.compare_digest(actual, expected)

    @staticmethod
    def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
        # maxmem must exceed 128 * n * r * p bytes; 64 MiB leaves room for raised params.
        return hashlib.scrypt(
            password.encode(), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024**2, dklen=32
        )


class JwtTokenService:
    """Stateless HMAC-signed tokens bound to a purpose (``typ`` claim).

    The purpose check stops a token issued for one flow (e.g. email verification)
    from being replayed in another (e.g. as an access token).
    """

    def __init__(
        self,
        secret: str,
        algorithm: str = "HS256",
        expires_minutes: int = 60,
        issuer: str = "todo-api",
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._default_ttl = timedelta(minutes=expires_minutes)
        self._issuer = issuer

    def issue(self, subject: str, purpose: str, expires_in: timedelta | None = None) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": subject,
            "typ": purpose,
            "iss": self._issuer,
            "iat": now,
            "exp": now + (expires_in or self._default_ttl),
        }
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def decode(self, token: str, purpose: str) -> str:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                options={"require": ["sub", "typ", "iss", "iat", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError() from exc
        if claims["typ"] != purpose:
            raise InvalidTokenError()
        return str(claims["sub"])
