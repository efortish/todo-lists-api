"""SQLAlchemy ORM models. They mirror the domain entities but stay in infrastructure."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column, relationship

from app.domain.entities import TaskPriority, TaskStatus


class Base(DeclarativeBase):
    pass


def _str_enum(enum_cls: type) -> Enum:
    # Store the value ("in_progress"), not the member name, as a portable VARCHAR + CHECK.
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda members: [m.value for m in members],
        name=f"{enum_cls.__name__.lower()}_enum",
    )


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TaskListModel(Base):
    __tablename__ = "task_lists"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_task_lists_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["TaskListMemberModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TaskListMemberModel.email"
    )


class TaskListMemberModel(Base):
    __tablename__ = "task_list_members"

    task_list_id: Mapped[int] = mapped_column(
        ForeignKey("task_lists.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(320), primary_key=True, index=True)


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_list_id: Mapped[int] = mapped_column(
        ForeignKey("task_lists.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(_str_enum(TaskStatus), index=True)
    priority: Mapped[TaskPriority] = mapped_column(_str_enum(TaskPriority), index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# Read-only, computed by the database in the same query that loads each list.
TaskListModel.task_count = column_property(
    select(func.count(TaskModel.id))
    .where(TaskModel.task_list_id == TaskListModel.id)
    .correlate_except(TaskModel)
    .scalar_subquery()
)
