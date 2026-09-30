"""HTTP-level security behaviour: verification, throttling, headers, limits, docs."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.conftest import PASSWORD

pytestmark = pytest.mark.integration


def test_unverified_invitee_cannot_see_the_list(client, login, owner, task_list, notifier):
    client.post(
        f"/api/v1/task-lists/{task_list['id']}/invitations",
        json={"email": "bob@example.com"},
        headers=owner,
    )
    # Someone registers with the invited address but cannot prove they own it.
    squatter = login("bob@example.com", verify=False)

    assert client.get("/api/v1/auth/me", headers=squatter).json()["email_verified"] is False
    assert client.get("/api/v1/task-lists", headers=squatter).json() == []
    assert client.get(f"/api/v1/task-lists/{task_list['id']}", headers=squatter).status_code == 404

    resent = client.post("/api/v1/auth/verify-email/resend", headers=squatter)
    assert resent.status_code == 204
    token = notifier.verification_token("bob@example.com")
    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.json()["email_verified"] is True
    assert client.get(f"/api/v1/task-lists/{task_list['id']}", headers=squatter).status_code == 200


def test_access_token_is_not_a_verification_token(client, owner):
    access_token = owner["Authorization"].removeprefix("Bearer ")

    response = client.post("/api/v1/auth/verify-email", json={"token": access_token})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_login_is_rate_limited_per_ip(make_client):
    client = make_client(auth_rate_limit_per_minute=3)
    attempt = {"username": "victim@example.com", "password": "guess-guess"}

    codes = [client.post("/api/v1/auth/token", data=attempt).status_code for _ in range(4)]

    assert codes == [401, 401, 401, 429]
    blocked = client.post("/api/v1/auth/token", data=attempt)
    assert blocked.json()["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1


@pytest.mark.parametrize("field", ["full_name", "title"])
def test_control_characters_are_rejected(client, owner, task_list, field):
    injected = "Hi\r\nBcc: everyone@example.com"
    if field == "full_name":
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "full_name": injected, "password": PASSWORD},
        )
    else:
        response = client.post(
            f"/api/v1/task-lists/{task_list['id']}/tasks", json={"title": injected}, headers=owner
        )

    assert response.status_code == 422


def test_oversized_bodies_are_rejected(make_client):
    client = make_client(max_request_body_bytes=1024)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "full_name": "A" * 2000, "password": PASSWORD},
    )

    assert response.status_code == 413


def test_security_headers(client, owner):
    headers = client.get("/api/v1/task-lists", headers=owner).headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert headers["cache-control"] == "no-store"
    assert "strict-transport-security" in headers


def test_docs_are_hidden_in_production(make_client):
    client = make_client(app_env="production")

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("secret", [None, "too-short"])
def test_jwt_secret_is_required_and_long(monkeypatch, secret):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    kwargs = {} if secret is None else {"jwt_secret": secret}

    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None, **kwargs)


@pytest.mark.parametrize("algorithm", ["none", "RS256"])
def test_only_hmac_algorithms_are_accepted(algorithm):
    with pytest.raises(ValidationError, match="jwt_algorithm"):
        Settings(jwt_algorithm=algorithm, jwt_secret="s" * 32, _env_file=None)
