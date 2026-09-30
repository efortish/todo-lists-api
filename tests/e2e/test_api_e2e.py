"""Every endpoint, exercised over real HTTP against the running stack and PostgreSQL."""

from datetime import date, timedelta

import pytest

from tests.e2e.conftest import PASSWORD, verification_token

pytestmark = pytest.mark.e2e

AUTH = "/api/v1/auth"
LISTS = "/api/v1/task-lists"


@pytest.fixture(scope="module")
def users(api, emails):
    """Owner and member registered, verified and logged in; stranger only logged in."""
    tokens = {}
    for name, email in emails.items():
        assert api.register(email, full_name=name.title()).status_code == 201
        tokens[name] = api.login(email)
        if name != "stranger":
            token = verification_token(api, tokens[name])
            verified = api.post(f"{AUTH}/verify-email", json={"token": token})
            assert verified.json()["email_verified"] is True, verified.text
    ids = {name: api.get(f"{AUTH}/me", token).json()["id"] for name, token in tokens.items()}
    return {"token": tokens, "id": ids}


@pytest.fixture(scope="module")
def shared_list(api, users, emails):
    token = users["token"]["owner"]
    created = api.post(LISTS, token, json={"name": "E2E list", "description": "Shared"})
    assert created.status_code == 201, created.text
    task_list = created.json()
    invited = api.post(
        f"{LISTS}/{task_list['id']}/invitations", token, json={"email": emails["member"]}
    )
    assert invited.status_code == 201, invited.text
    return invited.json()


# --- Health and docs ------------------------------------------------------------------------


def test_health(api):
    assert api.get("/health").json() == {"status": "ok"}


def test_docs_are_served_in_development(api):
    assert api.get("/docs").status_code == 200
    spec = api.get("/openapi.json").json()
    login_form = spec["paths"]["/api/v1/auth/token"]["post"]["requestBody"]["content"]
    schema_name = login_form["application/x-www-form-urlencoded"]["schema"]["$ref"]
    fields = spec["components"]["schemas"][schema_name.split("/")[-1]]["properties"]
    assert list(fields) == ["username", "password"]


# --- Auth -----------------------------------------------------------------------------------


def test_register_rejects_duplicates_and_bad_input(api, users, emails):
    duplicate = api.register(emails["owner"].upper())
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "email_already_registered"

    bad = api.post(
        f"{AUTH}/register", json={"email": "nope", "full_name": "X", "password": "short"}
    )
    assert bad.status_code == 422


def test_login_and_me(api, users, emails):
    me = api.get(f"{AUTH}/me", users["token"]["owner"]).json()
    assert me["email"] == emails["owner"]
    assert me["email_verified"] is True
    assert "hashed_password" not in me

    wrong = api.post(f"{AUTH}/token", data={"username": emails["owner"], "password": "x" * 9})
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "invalid_credentials"
    unknown = api.post(
        f"{AUTH}/token", data={"username": "ghost@e2e.example.com", "password": PASSWORD}
    )
    assert unknown.json() == wrong.json()

    assert api.get(f"{AUTH}/me").status_code == 401
    assert api.get(f"{AUTH}/me", "not-a-token").status_code == 401


def test_email_verification_endpoints(api, users, emails):
    stranger = users["token"]["stranger"]
    assert api.get(f"{AUTH}/me", stranger).json()["email_verified"] is False

    assert api.post(f"{AUTH}/verify-email/resend", stranger).status_code == 204
    already = api.post(f"{AUTH}/verify-email/resend", users["token"]["owner"])
    assert already.status_code == 409
    assert already.json()["code"] == "email_already_verified"

    bad_token = api.post(f"{AUTH}/verify-email", json={"token": "forged"})
    assert bad_token.status_code == 401
    access_as_verification = api.post(f"{AUTH}/verify-email", json={"token": stranger})
    assert access_as_verification.status_code == 401


# --- Task lists -----------------------------------------------------------------------------


def test_task_list_crud(api, users):
    token = users["token"]["owner"]
    created = api.post(LISTS, token, json={"name": "Temporary"})
    assert created.status_code == 201
    task_list = created.json()
    assert task_list["task_count"] == 0
    item = f"{LISTS}/{task_list['id']}"

    assert api.post(LISTS, token, json={"name": "Temporary"}).status_code == 409
    assert api.get(item, token).json()["name"] == "Temporary"
    assert task_list["id"] in [t["id"] for t in api.get(LISTS, token).json()]

    updated = api.patch(item, token, json={"name": "Renamed", "description": "New"})
    assert updated.status_code == 200
    assert (updated.json()["name"], updated.json()["description"]) == ("Renamed", "New")
    assert api.patch(item, token, json={"name": None}).status_code == 422

    assert api.delete(item, token).status_code == 204
    assert api.get(item, token).status_code == 404


def test_invitations_and_access_control(api, users, emails, shared_list):
    owner, member, stranger = (users["token"][k] for k in ("owner", "member", "stranger"))
    item = f"{LISTS}/{shared_list['id']}"
    invitations = f"{item}/invitations"

    assert shared_list["member_emails"] == [emails["member"]]
    assert api.post(invitations, owner, json={"email": emails["member"]}).status_code == 409
    assert api.post(invitations, owner, json={"email": emails["owner"]}).status_code == 422
    not_owner = api.post(invitations, member, json={"email": "x@e2e.example.com"})
    assert not_owner.status_code == 403

    assert api.get(item, member).status_code == 200
    assert api.get(item, stranger).status_code == 404
    assert api.delete(item, stranger).status_code == 404
    assert api.delete(item, member).json()["code"] == "not_task_list_owner"

    # Invited but unverified: the invitation grants nothing until the email is verified.
    squat = api.post(invitations, owner, json={"email": emails["stranger"]})
    assert squat.status_code == 201
    assert api.get(item, stranger).status_code == 404


# --- Tasks ----------------------------------------------------------------------------------


def test_task_crud_filters_and_completion(api, users, shared_list):
    token = users["token"]["member"]
    tasks = f"{LISTS}/{shared_list['id']}/tasks"
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    for title, status, priority in [
        ("Done high", "done", "high"),
        ("Done low", "done", "low"),
        ("Pending high", "pending", "high"),
        ("Doing medium", "in_progress", "medium"),
    ]:
        payload = {"title": title, "status": status, "priority": priority, "due_date": tomorrow}
        assert api.post(tasks, token, json=payload).status_code == 201

    past = (date.today() - timedelta(days=1)).isoformat()
    rejected = api.post(tasks, token, json={"title": "Late", "due_date": past})
    assert rejected.json()["code"] == "due_date_in_past"

    page = api.get(tasks, token).json()
    assert (page["total"], page["completion_percentage"]) == (4, 50.0)
    high = api.get(tasks, token, params={"priority": "high"}).json()
    assert {t["title"] for t in high["items"]} == {"Done high", "Pending high"}
    done = api.get(tasks, token, params={"status": "done"}).json()
    assert (done["total"], done["completion_percentage"]) == (2, 50.0)
    second_page = api.get(tasks, token, params={"limit": 3, "offset": 3}).json()
    assert len(second_page["items"]) == 1
    assert api.get(tasks, token, params={"status": "nope"}).status_code == 422

    assert api.get(f"{LISTS}/{shared_list['id']}", token).json()["task_count"] == 4


def test_task_get_update_status_and_lock(api, users, shared_list):
    token = users["token"]["owner"]
    tasks = f"{LISTS}/{shared_list['id']}/tasks"
    task = api.post(tasks, token, json={"title": "Editable"}).json()
    item = f"{tasks}/{task['id']}"

    assert api.get(item, token).json()["title"] == "Editable"
    edited = api.patch(item, token, json={"title": "Edited", "priority": "high"}).json()
    assert (edited["title"], edited["priority"]) == ("Edited", "high")
    assert api.patch(item, token, json={"status": "done"}).status_code == 422

    assert api.patch(f"{item}/status", token, json={"status": "done"}).json()["status"] == "done"
    locked = api.patch(item, token, json={"title": "Again"})
    assert locked.json()["code"] == "task_completed"
    api.patch(f"{item}/status", token, json={"status": "pending"})
    assert api.patch(item, token, json={"title": "Again"}).status_code == 200


def test_assignment(api, users, shared_list):
    token = users["token"]["owner"]
    task = api.post(f"{LISTS}/{shared_list['id']}/tasks", token, json={"title": "Assign"}).json()
    assignee = f"{LISTS}/{shared_list['id']}/tasks/{task['id']}/assignee"

    assigned = api.put(assignee, token, json={"assignee_id": users["id"]["member"]})
    assert assigned.json()["assignee_id"] == users["id"]["member"]
    stranger = api.put(assignee, token, json={"assignee_id": users["id"]["stranger"]})
    missing = api.put(assignee, token, json={"assignee_id": 10**9})
    assert stranger.status_code == missing.status_code == 422
    assert stranger.json()["code"] == missing.json()["code"] == "assignee_without_access"
    assert api.put(assignee, token, json={"assignee_id": None}).json()["assignee_id"] is None


def test_delete_task_and_cascade(api, users):
    token = users["token"]["owner"]
    task_list = api.post(LISTS, token, json={"name": "To delete"}).json()
    tasks = f"{LISTS}/{task_list['id']}/tasks"
    task = api.post(tasks, token, json={"title": "Gone"}).json()
    other = api.post(tasks, token, json={"title": "Also gone"}).json()

    assert api.delete(f"{tasks}/{task['id']}", token).status_code == 204
    assert api.get(f"{tasks}/{task['id']}", token).json()["code"] == "task_not_found"

    api.delete(f"{LISTS}/{task_list['id']}", token)
    assert api.get(f"{tasks}/{other['id']}", token).status_code == 404


# --- Transport security ---------------------------------------------------------------------


def test_security_headers(api, users):
    headers = api.get(LISTS, users["token"]["owner"]).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"
    assert headers["content-security-policy"].startswith("default-src 'none'")
    assert "server" not in headers or "uvicorn" not in headers["server"].lower()


def test_oversized_body_is_rejected(api, users):
    huge = {"title": "x" * (2 * 1024 * 1024)}
    response = api.post(LISTS, users["token"]["owner"], json=huge)
    assert response.status_code == 413
