"""In-memory adapters for the domain ports, used by the use-case unit tests."""

import re
from dataclasses import replace
from itertools import count

from app.domain.entities import Task, TaskList, TaskPriority, TaskStatus, User


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.rows: dict[int, User] = {}
        self._ids = count(1)

    def add(self, user: User) -> User:
        stored = replace(user, id=next(self._ids))
        self.rows[stored.id] = stored
        return replace(stored)

    def get(self, user_id: int) -> User | None:
        user = self.rows.get(user_id)
        return replace(user) if user else None

    def get_by_email(self, email: str) -> User | None:
        return next((replace(u) for u in self.rows.values() if u.email == email), None)

    def update(self, user: User) -> User:
        self.rows[user.id] = replace(user)
        return replace(user)


class InMemoryTaskListRepository:
    def __init__(self) -> None:
        self.rows: dict[int, TaskList] = {}
        self._ids = count(1)

    def add(self, task_list: TaskList) -> TaskList:
        stored = replace(task_list, id=next(self._ids), member_emails=[])
        self.rows[stored.id] = stored
        return self._copy(stored)

    def get(self, task_list_id: int) -> TaskList | None:
        task_list = self.rows.get(task_list_id)
        return self._copy(task_list) if task_list else None

    def list_accessible_by(self, user: User) -> list[TaskList]:
        return [self._copy(t) for t in self.rows.values() if t.is_accessible_by(user)]

    def name_exists(self, owner_id: int, name: str, exclude_id: int | None = None) -> bool:
        return any(
            t.owner_id == owner_id and t.name == name and t.id != exclude_id
            for t in self.rows.values()
        )

    def update(self, task_list: TaskList) -> TaskList:
        self.rows[task_list.id] = self._copy(task_list)
        return self._copy(task_list)

    def delete(self, task_list_id: int) -> None:
        del self.rows[task_list_id]

    def add_member(self, task_list_id: int, email: str) -> TaskList:
        self.rows[task_list_id].member_emails.append(email)
        return self._copy(self.rows[task_list_id])

    @staticmethod
    def _copy(task_list: TaskList) -> TaskList:
        return replace(task_list, member_emails=list(task_list.member_emails))


class InMemoryTaskRepository:
    def __init__(self) -> None:
        self.rows: dict[int, Task] = {}
        self._ids = count(1)

    def add(self, task: Task) -> Task:
        stored = replace(task, id=next(self._ids))
        self.rows[stored.id] = stored
        return replace(stored)

    def get(self, task_list_id: int, task_id: int) -> Task | None:
        task = self.rows.get(task_id)
        return replace(task) if task and task.task_list_id == task_list_id else None

    def list(
        self,
        task_list_id: int,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        matches = [
            replace(t)
            for t in self.rows.values()
            if t.task_list_id == task_list_id
            and status in (None, t.status)
            and priority in (None, t.priority)
        ]
        return matches[offset : offset + limit], len(matches)

    def count_by_status(self, task_list_id: int) -> dict[TaskStatus, int]:
        counts: dict[TaskStatus, int] = {}
        for task in self.rows.values():
            if task.task_list_id == task_list_id:
                counts[task.status] = counts.get(task.status, 0) + 1
        return counts

    def update(self, task: Task) -> Task:
        self.rows[task.id] = replace(task)
        return replace(task)

    def delete(self, task_id: int) -> None:
        del self.rows[task_id]


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send_email(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})

    def verification_token(self, email: str) -> str:
        """Extract the token of the latest verification email sent to ``email``."""
        body = next(
            m["body"]
            for m in reversed(self.sent)
            if m["to"] == email and m["subject"] == "Verify your email address"
        )
        return re.search(r"token (\S+) ", body).group(1)

    def emails_to(self, email: str, subject_contains: str = "") -> list[dict[str, str]]:
        return [m for m in self.sent if m["to"] == email and subject_contains in m["subject"]]
