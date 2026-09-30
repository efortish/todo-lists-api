"""SQLAlchemy implementations of the repository ports.

Each write commits immediately: every use case performs a single logical write,
so a request-wide unit of work would add machinery without adding safety.
"""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.domain.entities import Task, TaskList, TaskPriority, TaskStatus, User
from app.infrastructure.db.models import (
    TaskListMemberModel,
    TaskListModel,
    TaskModel,
    UserModel,
)

_TASK_FIELDS = ("title", "description", "status", "priority", "due_date", "assignee_id")


def _to_user(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        hashed_password=row.hashed_password,
        email_verified=row.email_verified,
        created_at=row.created_at,
    )


def _to_task_list(row: TaskListModel) -> TaskList:
    return TaskList(
        id=row.id,
        name=row.name,
        description=row.description,
        owner_id=row.owner_id,
        member_emails=[member.email for member in row.members],
        task_count=row.task_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_task(row: TaskModel) -> Task:
    return Task(
        id=row.id,
        task_list_id=row.task_list_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        **{name: getattr(row, name) for name in _TASK_FIELDS},
    )


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> User:
        row = UserModel(
            email=user.email, full_name=user.full_name, hashed_password=user.hashed_password
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return _to_user(row)

    def get(self, user_id: int) -> User | None:
        row = self._session.get(UserModel, user_id)
        return _to_user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        row = self._session.scalar(select(UserModel).where(UserModel.email == email))
        return _to_user(row) if row else None

    def update(self, user: User) -> User:
        row = self._session.get_one(UserModel, user.id)
        row.full_name = user.full_name
        row.email_verified = user.email_verified
        self._session.commit()
        self._session.refresh(row)
        return _to_user(row)


class SqlTaskListRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, task_list: TaskList) -> TaskList:
        row = TaskListModel(
            name=task_list.name, description=task_list.description, owner_id=task_list.owner_id
        )
        self._session.add(row)
        return self._commit(row)

    def get(self, task_list_id: int) -> TaskList | None:
        row = self._session.get(TaskListModel, task_list_id)
        return _to_task_list(row) if row else None

    def list_accessible_by(self, user: User) -> list[TaskList]:
        # Must mirror TaskList.is_accessible_by: membership counts only for verified emails.
        conditions = [TaskListModel.owner_id == user.id]
        if user.email_verified:
            conditions.append(
                exists().where(
                    TaskListMemberModel.task_list_id == TaskListModel.id,
                    TaskListMemberModel.email == user.email,
                )
            )
        rows = self._session.scalars(
            select(TaskListModel).where(or_(*conditions)).order_by(TaskListModel.id)
        )
        return [_to_task_list(row) for row in rows]

    def name_exists(self, owner_id: int, name: str, exclude_id: int | None = None) -> bool:
        query = select(TaskListModel.id).where(
            TaskListModel.owner_id == owner_id, TaskListModel.name == name
        )
        if exclude_id is not None:
            query = query.where(TaskListModel.id != exclude_id)
        return self._session.scalar(query) is not None

    def update(self, task_list: TaskList) -> TaskList:
        row = self._session.get_one(TaskListModel, task_list.id)
        row.name = task_list.name
        row.description = task_list.description
        return self._commit(row)

    def delete(self, task_list_id: int) -> None:
        self._session.delete(self._session.get_one(TaskListModel, task_list_id))
        self._session.commit()

    def add_member(self, task_list_id: int, email: str) -> TaskList:
        row = self._session.get_one(TaskListModel, task_list_id)
        row.members.append(TaskListMemberModel(email=email))
        return self._commit(row)

    def _commit(self, row: TaskListModel) -> TaskList:
        self._session.commit()
        self._session.refresh(row)
        return _to_task_list(row)


class SqlTaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, task: Task) -> Task:
        row = TaskModel(
            task_list_id=task.task_list_id, **{name: getattr(task, name) for name in _TASK_FIELDS}
        )
        self._session.add(row)
        return self._commit(row)

    def get(self, task_list_id: int, task_id: int) -> Task | None:
        row = self._session.get(TaskModel, task_id)
        return _to_task(row) if row and row.task_list_id == task_list_id else None

    def list(
        self,
        task_list_id: int,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        query = select(TaskModel).where(TaskModel.task_list_id == task_list_id)
        if status is not None:
            query = query.where(TaskModel.status == status)
        if priority is not None:
            query = query.where(TaskModel.priority == priority)
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(query.order_by(TaskModel.id).limit(limit).offset(offset))
        return [_to_task(row) for row in rows], total or 0

    def count_by_status(self, task_list_id: int) -> dict[TaskStatus, int]:
        rows = self._session.execute(
            select(TaskModel.status, func.count())
            .where(TaskModel.task_list_id == task_list_id)
            .group_by(TaskModel.status)
        )
        return {status: count for status, count in rows}

    def update(self, task: Task) -> Task:
        row = self._session.get_one(TaskModel, task.id)
        for name in _TASK_FIELDS:
            setattr(row, name, getattr(task, name))
        return self._commit(row)

    def delete(self, task_id: int) -> None:
        self._session.delete(self._session.get_one(TaskModel, task_id))
        self._session.commit()

    def _commit(self, row: TaskModel) -> Task:
        self._session.commit()
        self._session.refresh(row)
        return _to_task(row)
