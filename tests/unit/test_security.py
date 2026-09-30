import jwt
import pytest

from app.domain.exceptions import InvalidTokenError
from app.infrastructure.security import JwtTokenService, ScryptPasswordHasher

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret-that-is-long-enough-for-hs256"


def test_password_hash_roundtrip():
    hasher = ScryptPasswordHasher(n=2**10)
    hashed = hasher.hash("hunter22")

    assert hashed.startswith("scrypt$")
    assert "hunter22" not in hashed
    assert hasher.verify("hunter22", hashed)
    assert not hasher.verify("hunter23", hashed)


def test_password_hashes_are_salted():
    hasher = ScryptPasswordHasher(n=2**10)

    assert hasher.hash("same") != hasher.hash("same")


@pytest.mark.parametrize("corrupted", ["", "plain", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$1$aa$bb"])
def test_password_verify_rejects_malformed_hashes(corrupted):
    assert not ScryptPasswordHasher(n=2**10).verify("anything", corrupted)


def test_password_verify_without_hash_is_false():
    assert not ScryptPasswordHasher(n=2**10).verify("anything", None)


def test_default_hash_parameters_meet_owasp():
    assert ScryptPasswordHasher().hash("x").split("$")[1:4] == ["16384", "8", "5"]


def test_token_roundtrip():
    tokens = JwtTokenService(SECRET)

    assert tokens.decode(tokens.issue("42", "access"), "access") == "42"


def test_token_issued_for_another_purpose_is_rejected():
    tokens = JwtTokenService(SECRET)

    with pytest.raises(InvalidTokenError):
        tokens.decode(tokens.issue("42", "email_verification"), "access")


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        JwtTokenService("another-secret-that-is-long-enough-for-hs256").issue("42", "access"),
        JwtTokenService(SECRET, expires_minutes=-1).issue("42", "access"),
        JwtTokenService(SECRET, issuer="someone-else").issue("42", "access"),
        jwt.encode({"sub": "42", "typ": "access", "iss": "todo-api"}, SECRET, algorithm="HS256"),
        jwt.encode({"sub": "42", "typ": "access"}, "", algorithm="none"),
    ],
    ids=["garbage", "wrong-signature", "expired", "wrong-issuer", "missing-exp", "alg-none"],
)
def test_token_rejects_invalid_tokens(token):
    with pytest.raises(InvalidTokenError):
        JwtTokenService(SECRET).decode(token, "access")
