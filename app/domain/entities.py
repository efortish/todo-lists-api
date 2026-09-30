"""Domain entities and value objects.

Entities are plain dataclasses that carry the business rules. They know nothing
about HTTP, Pydantic or the database, so they can be tested in isolation.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from app.domain.exceptions import DueDateInPastError, TaskCompletedError


class TaskStatus(StrEnum):
    """Lifecycle of a task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(StrEnum):
    """How urgent a task is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class User:
    """A registered user. ``email`` is always stored lower-cased.

    ``email_verified`` proves the user controls the address. Access granted by
    email (invitations) requires it, otherwise anyone could register with an
    invitee's address and read the list.
    """

    email: str
    full_name: str
    hashed_password: str
    email_verified: bool = False
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class TaskList:
    """A named collection of tasks owned by one user and shared with invited members.

    Members are tracked by email so a person can be invited before they register:
    access is granted once an account with that email exists **and has verified it**.
    """

    name: str
    owner_id: int
    description: str | None = None
    member_emails: list[str] = field(default_factory=list)
    task_count: int = 0  # read-only, filled in by the repository
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def is_owner(self, user: User) -> bool:
        """Return whether ``user`` owns this list."""
        return self.owner_id == user.id

    def is_accessible_by(self, user: User) -> bool:
        """Return whether ``user`` may read and manage the tasks of this list."""
        return self.is_owner(user) or (user.email_verified and user.email in self.member_emails)


@dataclass
class Task:
    """A unit of work inside a :class:`TaskList`."""

    task_list_id: int
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    assignee_id: int | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def ensure_editable(self) -> None:
        """Reject edits on finished tasks; they must be reopened (status change) first.

        Raises:
            TaskCompletedError: if the task is done.
        """
        if self.status is TaskStatus.DONE:
            raise TaskCompletedError(self.id)


def validate_due_date(due_date: date | None, today: date) -> None:
    """Ensure a due date being set is not already in the past.

    Raises:
        DueDateInPastError: if ``due_date`` is earlier than ``today``.
    """
    if due_date is not None and due_date < today:
        raise DueDateInPastError()


def completion_percentage(done: int, total: int) -> float:
    """Percentage of finished tasks, rounded to two decimals. An empty list is 0% complete."""
    if total == 0:
        return 0.0
    return round(done * 100 / total, 2)
