from datetime import date

import pytest

from app.domain.entities import (
    Task,
    TaskList,
    TaskStatus,
    User,
    completion_percentage,
    validate_due_date,
)
from app.domain.exceptions import DueDateInPastError, TaskCompletedError

pytestmark = pytest.mark.unit

OWNER = User(id=1, email="owner@example.com", full_name="Owner", hashed_password="x")
MEMBER = User(
    id=2, email="member@example.com", full_name="Member", hashed_password="x", email_verified=True
)
UNVERIFIED = User(id=4, email="member@example.com", full_name="Squatter", hashed_password="x")
STRANGER = User(id=3, email="stranger@example.com", full_name="Stranger", hashed_password="x")


@pytest.mark.parametrize(
    ("done", "total", "expected"),
    [(0, 0, 0.0), (0, 4, 0.0), (1, 3, 33.33), (2, 3, 66.67), (5, 5, 100.0)],
)
def test_completion_percentage(done, total, expected):
    assert completion_percentage(done, total) == expected


def test_task_list_access_rules():
    task_list = TaskList(id=1, name="L", owner_id=OWNER.id, member_emails=[MEMBER.email])

    assert task_list.is_owner(OWNER)
    assert not task_list.is_owner(MEMBER)
    assert task_list.is_accessible_by(OWNER)
    assert task_list.is_accessible_by(MEMBER)
    assert not task_list.is_accessible_by(STRANGER)
    assert not task_list.is_accessible_by(UNVERIFIED)


@pytest.mark.parametrize("status", [TaskStatus.PENDING, TaskStatus.IN_PROGRESS])
def test_open_tasks_are_editable(status):
    Task(id=1, task_list_id=1, title="t", status=status).ensure_editable()


def test_done_tasks_are_not_editable():
    with pytest.raises(TaskCompletedError):
        Task(id=1, task_list_id=1, title="t", status=TaskStatus.DONE).ensure_editable()


def test_due_date_validation():
    today = date(2026, 1, 10)

    validate_due_date(None, today)
    validate_due_date(today, today)
    validate_due_date(date(2026, 1, 11), today)
    with pytest.raises(DueDateInPastError):
        validate_due_date(date(2026, 1, 9), today)
