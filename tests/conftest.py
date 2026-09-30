import os
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.infrastructure.db.models import Base
from app.infrastructure.security import ScryptPasswordHasher
from app.main import create_app
from tests.fakes import RecordingNotifier

# The end-to-end suite needs a running stack: only collect it when it is pointed at one.
collect_ignore_glob = [] if os.environ.get("E2E_BASE_URL") else ["e2e/*"]

PASSWORD = "correct-horse-battery"
TEST_SECRET = "integration-test-secret-long-enough-for-hs256"


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def make_client(notifier: RecordingNotifier) -> Iterator[Callable[..., TestClient]]:
    """Build a client for an app created with ``Settings`` overrides."""
    engines = []

    def _make(**overrides) -> TestClient:
        settings = Settings(
            **{"database_url": "sqlite://", "jwt_secret": TEST_SECRET, "app_env": "test"}
            | overrides,
            _env_file=None,
        )
        app = create_app(settings)
        Base.metadata.create_all(app.state.engine)
        app.state.notifier = notifier
        # Production cost is OWASP-grade; tests only need the behaviour, not the cost.
        app.state.password_hasher = ScryptPasswordHasher(n=2**10, p=1)
        engines.append(app.state.engine)
        return TestClient(app)

    yield _make
    for engine in engines:
        engine.dispose()


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def login(client: TestClient, notifier: RecordingNotifier) -> Callable[..., dict[str, str]]:
    """Register (if needed), verify the email and log in a user; return its auth headers."""

    def _login(
        email: str = "owner@example.com", full_name: str = "Olivia Owner", verify: bool = True
    ) -> dict[str, str]:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "full_name": full_name, "password": PASSWORD},
        )
        if verify and registered.status_code == 201:
            token = notifier.verification_token(email.lower())
            client.post("/api/v1/auth/verify-email", json={"token": token})
        response = client.post(
            "/api/v1/auth/token", data={"username": email, "password": PASSWORD}
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def owner(login) -> dict[str, str]:
    return login()


@pytest.fixture
def task_list(client: TestClient, owner: dict[str, str]) -> dict:
    response = client.post("/api/v1/task-lists", json={"name": "Groceries"}, headers=owner)
    return response.json()
