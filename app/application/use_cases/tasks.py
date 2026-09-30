"""Use cases for tasks inside a task list."""

from collections.abc import Callable
from datetime import date

from app.application.schemas import TaskCreate, TaskOut, TaskPage, TaskUpdate
from app.application.use_cases.task_lists import get_accessible_task_list
from app.domain.entities import (
    Task,
    TaskPriority,
    TaskStatus,
    User,
    completion_percentage,
    validate_due_date,
)
from app.domain.exceptions import AssigneeWithoutAccessError, TaskNotFoundError
from app.domain.ports import Notifier, TaskListRepository, TaskRepository, UserRepository


class TaskUseCases:
    def __init__(
        self,
        task_lists: TaskListRepository,
        tasks: TaskRepository,
        users: UserRepository,
        notifier: Notifier,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._task_lists = task_lists
        self._tasks = tasks
        self._users = users
        self._notifier = notifier
        self._today = today

    def create(self, user: User, task_list_id: int, data: TaskCreate) -> Task:
        """Add a task to an accessible list.

        Raises:
            TaskListNotFoundError: if the list is not accessible.
            DueDateInPastError: if ``due_date`` is before today.
        """
        get_accessible_task_list(self._task_lists, user, task_list_id)
        validate_due_date(data.due_date, self._today())
        return self._tasks.add(Task(task_list_id=task_list_id, **data.model_dump()))

    def get(self, user: User, task_list_id: int, task_id: int) -> Task:
        """Return one task of an accessible list.

        Raises:
            TaskListNotFoundError: if the list is not accessible.
            TaskNotFoundError: if the task does not exist in that list.
        """
        get_accessible_task_list(self._task_lists, user, task_list_id)
        return self._get_task(task_list_id, task_id)

    def list(
        self,
        user: User,
        task_list_id: int,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TaskPage:
        """Return a filtered page of tasks and the completion percentage of the whole list.

        Raises:
            TaskListNotFoundError: if the list is not accessible.
        """
        get_accessible_task_list(self._task_lists, user, task_list_id)
        items, total = self._tasks.list(
            task_list_id, status=status, priority=priority, limit=limit, offset=offset
        )
        counts = self._tasks.count_by_status(task_list_id)
        return TaskPage(
            items=[TaskOut.model_validate(task) for task in items],
            total=total,
            limit=limit,
            offset=offset,
            completion_percentage=completion_percentage(
                counts.get(TaskStatus.DONE, 0), sum(counts.values())
            ),
        )

    def update(self, user: User, task_list_id: int, task_id: int, data: TaskUpdate) -> Task:
        """Edit the content of a task that is not done.

        Raises:
            TaskListNotFoundError, TaskNotFoundError: if not found.
            TaskCompletedError: if the task is done.
            DueDateInPastError: if a new ``due_date`` is before today.
        """
        task = self.get(user, task_list_id, task_id)
        task.ensure_editable()
        changes = data.model_dump(exclude_unset=True)
        if "due_date" in changes:
            validate_due_date(changes["due_date"], self._today())
        for field, value in changes.items():
            setattr(task, field, value)
        return self._tasks.update(task)

    def change_status(
        self, user: User, task_list_id: int, task_id: int, status: TaskStatus
    ) -> Task:
        """Move a task to ``status``. Any transition is allowed, which is how done tasks reopen.

        Raises:
            TaskListNotFoundError, TaskNotFoundError: if not found.
        """
        task = self.get(user, task_list_id, task_id)
        task.status = status
        return self._tasks.update(task)

    def assign(self, user: User, task_list_id: int, task_id: int, assignee_id: int | None) -> Task:
        """Set (or clear, with ``None``) the user responsible for a task and notify them.

        Raises:
            TaskListNotFoundError, TaskNotFoundError: if not found.
            AssigneeWithoutAccessError: if the assignee does not exist or cannot access the
                list (deliberately indistinguishable, see the exception).
        """
        task_list = get_accessible_task_list(self._task_lists, user, task_list_id)
        task = self._get_task(task_list_id, task_id)
        assignee = None
        if assignee_id is not None:
            assignee = self._users.get(assignee_id)
            if assignee is None or not task_list.is_accessible_by(assignee):
                raise AssigneeWithoutAccessError(assignee_id)
        task.assignee_id = assignee_id
        task = self._tasks.update(task)
        if assignee is not None and assignee.id != user.id:
            self._notifier.send_email(
                to=assignee.email,
                subject=f"You were assigned '{task.title}'",
                body=f"{user.full_name} assigned you the task '{task.title}' "
                f"in the list '{task_list.name}'.",
            )
        return task

    def delete(self, user: User, task_list_id: int, task_id: int) -> None:
        """Delete a task. Allowed for any user with access, even if the task is done.

        Raises:
            TaskListNotFoundError, TaskNotFoundError: if not found.
        """
        task = self.get(user, task_list_id, task_id)
        self._tasks.delete(task.id)

    def _get_task(self, task_list_id: int, task_id: int) -> Task:
        task = self._tasks.get(task_list_id, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task
