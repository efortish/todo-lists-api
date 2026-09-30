"""Ports: the interfaces the application layer depends on.

Infrastructure provides the concrete adapters (SQLAlchemy repositories, JWT,
log-based email). Tests provide in-memory fakes. Structural typing via
``Protocol`` keeps adapters free from inheriting anything.
"""

from datetime import timedelta
from typing import Protocol

from app.domain.entities import Task, TaskList, TaskPriority, TaskStatus, User


class UserRepository(Protocol):
    def add(self, user: User) -> User:
        """Persist a new user and return it with its generated id."""
        ...

    def get(self, user_id: int) -> User | None:
        """Return the user with ``user_id`` or ``None``."""
        ...

    def get_by_email(self, email: str) -> User | None:
        """Return the user registered with ``email`` (lower-cased) or ``None``."""
        ...

    def update(self, user: User) -> User:
        """Persist the mutable fields of ``user`` and return the stored version."""
        ...


class TaskListRepository(Protocol):
    def add(self, task_list: TaskList) -> TaskList:
        """Persist a new task list and return it with its generated id."""
        ...

    def get(self, task_list_id: int) -> TaskList | None:
        """Return the task list with ``task_list_id`` or ``None``."""
        ...

    def list_accessible_by(self, user: User) -> list[TaskList]:
        """Return the lists ``user`` owns or has been invited to, oldest first."""
        ...

    def name_exists(self, owner_id: int, name: str, exclude_id: int | None = None) -> bool:
        """Return whether ``owner_id`` already owns a list called ``name``."""
        ...

    def update(self, task_list: TaskList) -> TaskList:
        """Persist the editable fields of ``task_list`` and return the stored version."""
        ...

    def delete(self, task_list_id: int) -> None:
        """Delete the list together with its tasks and memberships."""
        ...

    def add_member(self, task_list_id: int, email: str) -> TaskList:
        """Grant ``email`` access to the list and return the updated list."""
        ...


class TaskRepository(Protocol):
    def add(self, task: Task) -> Task:
        """Persist a new task and return it with its generated id."""
        ...

    def get(self, task_list_id: int, task_id: int) -> Task | None:
        """Return the task only if it belongs to ``task_list_id``."""
        ...

    def list(
        self,
        task_list_id: int,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        """Return one page of matching tasks and the total number of matches."""
        ...

    def count_by_status(self, task_list_id: int) -> dict[TaskStatus, int]:
        """Return how many tasks of the list are in each status (missing keys mean 0)."""
        ...

    def update(self, task: Task) -> Task:
        """Persist the editable fields of ``task`` and return the stored version."""
        ...

    def delete(self, task_id: int) -> None:
        """Delete the task."""
        ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str:
        """Return a salted, self-describing hash of ``password``."""
        ...

    def verify(self, password: str, hashed: str | None) -> bool:
        """Return whether ``password`` matches ``hashed``.

        With ``hashed=None`` (unknown user) it must still spend the time of a real
        check and return ``False``, so response times do not reveal which emails exist.
        """
        ...


class TokenService(Protocol):
    def issue(self, subject: str, purpose: str, expires_in: timedelta | None = None) -> str:
        """Return a signed token for ``subject`` usable only for ``purpose``.

        ``expires_in`` defaults to the access token lifetime.
        """
        ...

    def decode(self, token: str, purpose: str) -> str:
        """Return the subject of a valid token issued for ``purpose``.

        Raises:
            InvalidTokenError: if the token is malformed, tampered with, expired or was
                issued for another purpose.
        """
        ...


class Notifier(Protocol):
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Deliver an email to ``to``."""
        ...
