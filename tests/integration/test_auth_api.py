import pytest

from tests.conftest import PASSWORD

pytestmark = pytest.mark.integration


def test_register_login_and_me(client, login):
    headers = login("Ada@Example.com", "Ada Lovelace")

    response = client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert body["full_name"] == "Ada Lovelace"
    assert "hashed_password" not in body


def test_register_duplicate_email_returns_409(client, login):
    login("ada@example.com")

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "ADA@example.com", "full_name": "Ada", "password": PASSWORD},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "full_name": "A", "password": PASSWORD},
        {"email": "a@example.com", "full_name": "A", "password": "short"},
        {"email": "a@example.com", "full_name": "   ", "password": PASSWORD},
        {"email": "a@example.com", "full_name": "A", "password": PASSWORD, "admin": True},
    ],
    ids=["bad-email", "short-password", "blank-name", "unknown-field"],
)
def test_register_validates_input(client, payload):
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422


def test_login_with_wrong_password_returns_401(client, login):
    login("ada@example.com")

    response = client.post(
        "/api/v1/auth/token", data={"username": "ada@example.com", "password": "nope-nope"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer garbage"}])
def test_protected_endpoints_require_a_valid_token(client, headers):
    assert client.get("/api/v1/task-lists", headers=headers).status_code == 401


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_openapi_documents_error_bodies(client):
    schema = client.get("/openapi.json").json()

    delete_task = schema["paths"]["/api/v1/task-lists/{task_list_id}/tasks/{task_id}"]["delete"]
    assert delete_task["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
