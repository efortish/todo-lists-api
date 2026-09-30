import pytest

pytestmark = pytest.mark.integration

URL = "/api/v1/task-lists"


def test_task_list_crud(client, owner):
    created = client.post(
        URL, json={"name": "  Groceries ", "description": "Weekly"}, headers=owner
    )
    assert created.status_code == 201
    task_list = created.json()
    assert task_list["name"] == "Groceries"
    assert task_list["member_emails"] == []
    item_url = f"{URL}/{task_list['id']}"

    assert client.get(item_url, headers=owner).json() == task_list
    assert [t["id"] for t in client.get(URL, headers=owner).json()] == [task_list["id"]]

    updated = client.patch(item_url, json={"description": None}, headers=owner)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Groceries"
    assert updated.json()["description"] is None

    assert client.delete(item_url, headers=owner).status_code == 204
    assert client.get(item_url, headers=owner).status_code == 404


def test_duplicate_name_returns_409(client, owner, task_list):
    response = client.post(URL, json={"name": "Groceries"}, headers=owner)

    assert response.status_code == 409
    assert response.json() == {
        "code": "duplicate_task_list_name",
        "message": "You already own a task list named 'Groceries'.",
    }


@pytest.mark.parametrize("payload", [{"name": None}, {"name": ""}, {"color": "red"}])
def test_update_rejects_invalid_payloads(client, owner, task_list, payload):
    response = client.patch(f"{URL}/{task_list['id']}", json=payload, headers=owner)

    assert response.status_code == 422


def test_other_users_get_404(client, login, task_list):
    stranger = login("stranger@example.com")
    item_url = f"{URL}/{task_list['id']}"

    assert client.get(item_url, headers=stranger).status_code == 404
    assert client.patch(item_url, json={"name": "x"}, headers=stranger).status_code == 404
    assert client.delete(item_url, headers=stranger).status_code == 404
    assert client.get(URL, headers=stranger).json() == []


def test_invitation_flow(client, login, owner, task_list, notifier):
    invite_url = f"{URL}/{task_list['id']}/invitations"

    response = client.post(invite_url, json={"email": "Friend@Example.com"}, headers=owner)

    assert response.status_code == 201
    assert response.json()["member_emails"] == ["friend@example.com"]
    assert len(notifier.emails_to("friend@example.com", "Groceries")) == 1

    # The invitee registers later and, once verified, sees the list but cannot manage it.
    friend = login("friend@example.com")
    assert [t["id"] for t in client.get(URL, headers=friend).json()] == [task_list["id"]]
    renamed = client.patch(f"{URL}/{task_list['id']}", json={"name": "Shop"}, headers=friend)
    assert renamed.status_code == 200
    forbidden = client.delete(f"{URL}/{task_list['id']}", headers=friend)
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "not_task_list_owner"

    again = client.post(invite_url, json={"email": "friend@example.com"}, headers=owner)
    assert again.status_code == 409
    self_invite = client.post(invite_url, json={"email": "owner@example.com"}, headers=owner)
    assert self_invite.status_code == 422
