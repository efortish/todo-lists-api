"""Pydantic DTOs at the application boundary.

Inputs are validated here once and double as the public API contract (they are
what Swagger documents), so the web layer does not duplicate them.

Partial-update models declare non-nullable fields as ``T = Field(None, ...)``:
omitting the field is allowed (``exclude_unset`` drops it), but sending an
explicit ``null`` fails validation because ``None`` is not a valid ``T``.
"""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.domain.entities import TaskPriority, TaskStatus

# Single-line text: control characters (CR/LF, NUL, ...) are rejected because names and
# titles are interpolated into email subjects, where CRLF would allow header injection.
SingleLine = Annotated[str, StringConstraints(pattern=r"^[^\x00-\x1f\x7f]*$")]


class _Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Errors ---------------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Body returned for every business error."""

    code: str = Field(description="Stable machine readable error id.", examples=["task_not_found"])
    message: str = Field(
        description="Human readable explanation.", examples=["Task 7 was not found."]
    )


# --- Users and auth -------------------------------------------------------------------------


class UserCreate(_Input):
    email: EmailStr = Field(description="Login email, stored lower-cased.")
    full_name: SingleLine = Field(min_length=1, max_length=120, examples=["Ada Lovelace"])
    password: str = Field(min_length=8, max_length=128, examples=["s3cure-passw0rd"])


class UserOut(_Output):
    id: int
    email: EmailStr
    full_name: str
    email_verified: bool = Field(
        description="Invitations only grant access once the email is verified."
    )
    created_at: datetime | None


class EmailVerification(_Input):
    token: str = Field(
        min_length=1, max_length=2048, description="Token received by email after registering."
    )


class Token(BaseModel):
    access_token: str = Field(description="JWT to send as `Authorization: Bearer <token>`.")
    token_type: str = Field(default="bearer", examples=["bearer"])


# --- Task lists -----------------------------------------------------------------------------


class TaskListCreate(_Input):
    name: SingleLine = Field(
        min_length=1,
        max_length=100,
        description="Unique among the lists you own.",
        examples=["Sprint 42"],
    )
    description: str | None = Field(default=None, max_length=1000, examples=["Backend work"])


class TaskListUpdate(_Input):
    name: SingleLine = Field(
        None, min_length=1, max_length=100, description="New name (not null)."
    )
    description: str | None = Field(None, max_length=1000, description="`null` clears it.")


class TaskListOut(_Output):
    id: int
    name: str
    description: str | None
    owner_id: int
    member_emails: list[str] = Field(description="Emails invited to collaborate on the list.")
    task_count: int = Field(description="Number of tasks in the list.", examples=[6])
    created_at: datetime | None
    updated_at: datetime | None


class InvitationCreate(_Input):
    email: EmailStr = Field(description="Person to invite. They do not need an account yet.")


# --- Tasks ----------------------------------------------------------------------------------


class TaskCreate(_Input):
    title: SingleLine = Field(min_length=1, max_length=200, examples=["Write the README"])
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = Field(default=None, description="Cannot be in the past.")


class TaskUpdate(_Input):
    title: SingleLine = Field(
        None, min_length=1, max_length=200, description="New title (not null)."
    )
    description: str | None = Field(None, max_length=5000, description="`null` clears it.")
    priority: TaskPriority = Field(None, description="New priority (not null).")
    due_date: date | None = Field(None, description="Cannot be in the past. `null` clears it.")


class TaskStatusUpdate(_Input):
    status: TaskStatus


class TaskAssignment(_Input):
    assignee_id: int | None = Field(
        description="User responsible for the task, or `null` to unassign. Must be the list "
        "owner or an invited member with a verified account.",
        examples=[2],
    )


class TaskOut(_Output):
    id: int
    task_list_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    assignee_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


class TaskPage(BaseModel):
    """A filtered page of tasks plus the completion of the whole list."""

    items: list[TaskOut]
    total: int = Field(description="Number of tasks matching the filters.")
    limit: int
    offset: int
    completion_percentage: float = Field(
        description="Share of tasks in `done` over **all** tasks of the list, ignoring filters "
        "and pagination (0-100, two decimals).",
        examples=[66.67],
    )
