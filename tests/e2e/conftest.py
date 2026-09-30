"""Fixtures for the end-to-end suite: a real HTTP client against a running stack.

Run with ``make e2e``. It starts nothing: bring the stack up first with ``make up`` or
``make dev``. The Makefile exports ``.env``, which provides the stack's ``JWT_SECRET``.
"""

import os
import time
import uuid
from datetime import timedelta

import httpx2
import pytest

from app.application.use_cases.auth import EMAIL_VERIFICATION
from app.infrastructure.security import JwtTokenService

BASE_URL = os.environ.get("E2E_BASE_URL", "")
PASSWORD = "e2e-Password-123"


class Api:
    """Thin client that retries once when the auth rate limit answers 429."""

    def __init__(self, client: httpx2.Client) -> None:
        self._client = client

    def request(self, method: str, url: str, token: str | None = None, **kwargs):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = self._client.request(method, url, headers=headers, **kwargs)
        if response.status_code == 429:
            time.sleep(int(response.headers["retry-after"]))
            response = self._client.request(method, url, headers=headers, **kwargs)
        return response

    def get(self, url, token=None, **kwargs):
        return self.request("GET", url, token, **kwargs)

    def post(self, url, token=None, **kwargs):
        return self.request("POST", url, token, **kwargs)

    def patch(self, url, token=None, **kwargs):
        return self.request("PATCH", url, token, **kwargs)

    def put(self, url, token=None, **kwargs):
        return self.request("PUT", url, token, **kwargs)

    def delete(self, url, token=None, **kwargs):
        return self.request("DELETE", url, token, **kwargs)

    def register(self, email: str, full_name: str = "E2E User"):
        return self.post(
            "/api/v1/auth/register",
            json={"email": email, "full_name": full_name, "password": PASSWORD},
        )

    def login(self, email: str) -> str:
        response = self.post("/api/v1/auth/token", data={"username": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]


def verification_token(api: "Api", access_token: str) -> str:
    """Sign a verification token for the logged-in user with the stack's own secret.

    The real token travels in a simulated email (the container log). Signing an
    equivalent one with ``JWT_SECRET`` from ``.env`` keeps the suite independent from
    Docker, while still exercising the real ``verify-email`` endpoint; that the email
    is actually sent is covered by the integration tests.
    """
    user_id = api.get("/api/v1/auth/me", access_token).json()["id"]
    tokens = JwtTokenService(os.environ["JWT_SECRET"], os.environ.get("JWT_ALGORITHM", "HS256"))
    return tokens.issue(str(user_id), EMAIL_VERIFICATION, timedelta(minutes=5))


@pytest.fixture(scope="session")
def api():
    with httpx2.Client(base_url=BASE_URL, timeout=10) as client:
        health = client.get("/health")
        assert health.status_code == 200, f"API not reachable at {BASE_URL}"
        yield Api(client)


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture(scope="session")
def emails(run_id):
    return {name: f"{name}-{run_id}@e2e.example.com" for name in ("owner", "member", "stranger")}
