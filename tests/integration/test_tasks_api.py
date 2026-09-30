from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def tasks_url(task_list) -> str:
    return f"/api/v1/task-lists/{task_list['id']}/tasks"


@pytest.fixture
def create_task(client, owner, tasks_url):
    def _create(**payload):
        response = client.post(tasks_url, json={"title": "Task", **payload}, headers=owner)
        assert response.status_code == 201, response.text
        return response.json()

    return _create


def test_task_crud(client, owner, tasks_url, create_task):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    task = create_task(title="Buy milk", priority="high", due_date=tomorrow)
    assert task["status"] == "pending"
    assert task["priority"] == "high"
    assert task["due_date"] == tomorrow
    item_url = f"{tasks_url}/{task['id']}"

    assert client.get(item_url, headers=owner).json() == task

    updated = client.patch(item_url, json={"title": "Buy oat milk"}, headers=owner).json()
    assert updated["title"] == "Buy oat milk"
    assert updated["priority"] == "high"

    assert client.delete(item_url, headers=owner).status_code == 204
    missing = client.get(item_url, headers=owner)
    assert missing.status_code == 404
    assert missing.json()["code"] == "task_not_found"


def test_create_task_validations(client, owner, tasks_url):
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    past = client.post(tasks_url, json={"title": "t", "due_date": yesterday}, headers=owner)
    assert past.status_code == 422
    assert past.json()["code"] == "due_date_in_past"

    for payload in ({"title": ""}, {"title": "t", "priority": "urgent"}, {"title": "t" * 201}):
        assert client.post(tasks_url, json=payload, headers=owner).status_code == 422


def test_filters_pagination_and_completion(client, owner, tasks_url, create_task):
    create_task(status="done", priority="high")
    create_task(status="done", priority="low")
    create_task(status="pending", priority="high")
    create_task(status="in_progress", priority="medium")

    everything = client.get(tasks_url, headers=owner).json()
    assert everything["total"] == 4
    assert everything["completion_percentage"] == 50.0

    done = client.get(tasks_url, params={"status": "done"}, headers=owner).json()
    assert {t["status"] for t in done["items"]} == {"done"}
    assert done["total"] == 2

    high_pending = client.get(
        tasks_url, params={"status": "pending", "priority": "high"}, headers=owner
    ).json()
    assert high_pending["total"] == 1
    assert high_pending["completion_percentage"] == 50.0  # filters never change completion

    page = client.get(tasks_url, params={"limit": 3, "offset": 3}, headers=owner).json()
    assert len(page["items"]) == 1
    assert page["total"] == 4

    bad = client.get(tasks_url, params={"status": "archived"}, headers=owner)
    assert bad.status_code == 422


def test_task_lists_report_their_task_count(client, owner, task_list, create_task):
    list_url = f"/api/v1/task-lists/{task_list['id']}"
    assert task_list["task_count"] == 0

    create_task()
    task = create_task()
    assert client.get(list_url, headers=owner).json()["task_count"] == 2
    assert client.get("/api/v1/task-lists", headers=owner).json()[0]["task_count"] == 2

    client.delete(f"{list_url}/tasks/{task['id']}", headers=owner)
    renamed = client.patch(list_url, json={"name": "Renamed"}, headers=owner).json()
    assert renamed["task_count"] == 1


def test_empty_list_is_zero_percent_complete(client, owner, tasks_url):
    body = client.get(tasks_url, headers=owner).json()

    assert body == {"items": [], "total": 0, "limit": 50, "offset": 0, "completion_percentage": 0}


def test_status_changes_and_done_tasks_are_locked(client, owner, tasks_url, create_task):
    task = create_task()
    item_url = f"{tasks_url}/{task['id']}"

    done = client.patch(f"{item_url}/status", json={"status": "done"}, headers=owner)
    assert done.json()["status"] == "done"

    locked = client.patch(item_url, json={"title": "new"}, headers=owner)
    assert locked.status_code == 409
    assert locked.json()["code"] == "task_completed"

    client.patch(f"{item_url}/status", json={"status": "in_progress"}, headers=owner)
    assert client.patch(item_url, json={"title": "new"}, headers=owner).json()["title"] == "new"


def test_assignment(client, login, owner, task_list, tasks_url, create_task, notifier):
    task = create_task(title="Cook")
    assignee_url = f"{tasks_url}/{task['id']}/assignee"
    friend_headers = login("friend@example.com", "Frank Friend")
    friend_id = client.get("/api/v1/auth/me", headers=friend_headers).json()["id"]

    denied = client.put(assignee_url, json={"assignee_id": friend_id}, headers=owner)
    assert denied.status_code == 422
    assert denied.json()["code"] == "assignee_without_access"
    unknown = client.put(assignee_url, json={"assignee_id": 999}, headers=owner)
    assert unknown.json() == {
        "code": "assignee_without_access",
        "message": denied.json()["message"].replace(str(friend_id), "999"),
    }

    client.post(
        f"/api/v1/task-lists/{task_list['id']}/invitations",
        json={"email": "friend@example.com"},
        headers=owner,
    )
    assigned = client.put(assignee_url, json={"assignee_id": friend_id}, headers=owner)
    assert assigned.json()["assignee_id"] == friend_id
    assert notifier.sent[-1]["to"] == "friend@example.com"
    assert "Cook" in notifier.sent[-1]["subject"]

    cleared = client.put(assignee_url, json={"assignee_id": None}, headers=owner)
    assert cleared.json()["assignee_id"] is None


def test_deleting_a_list_deletes_its_tasks(client, owner, task_list, tasks_url, create_task):
    task = create_task()

    client.delete(f"/api/v1/task-lists/{task_list['id']}", headers=owner)

    assert client.get(f"{tasks_url}/{task['id']}", headers=owner).status_code == 404


def test_tasks_of_foreign_lists_are_hidden(client, login, tasks_url, create_task):
    task = create_task()
    stranger = login("stranger@example.com")

    assert client.get(tasks_url, headers=stranger).status_code == 404
    assert client.get(f"{tasks_url}/{task['id']}", headers=stranger).status_code == 404
    assert client.post(tasks_url, json={"title": "x"}, headers=stranger).status_code == 404
