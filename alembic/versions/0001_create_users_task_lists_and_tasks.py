"""Create users, task lists, memberships and tasks.

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _str_enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=20)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        _timestamp("created_at"),
    )
    op.create_table(
        "task_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("owner_id", "name", name="uq_task_lists_owner_name"),
    )
    op.create_index("ix_task_lists_owner_id", "task_lists", ["owner_id"])

    op.create_table(
        "task_list_members",
        sa.Column(
            "task_list_id",
            sa.Integer(),
            sa.ForeignKey("task_lists.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("email", sa.String(320), primary_key=True),
    )
    op.create_index("ix_task_list_members_email", "task_list_members", ["email"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_list_id",
            sa.Integer(),
            sa.ForeignKey("task_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _str_enum("taskstatus_enum", "pending", "in_progress", "done"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            _str_enum("taskpriority_enum", "low", "medium", "high"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )
    for column in ("task_list_id", "status", "priority", "assignee_id"):
        op.create_index(f"ix_tasks_{column}", "tasks", [column])


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("task_list_members")
    op.drop_table("task_lists")
    op.drop_table("users")
