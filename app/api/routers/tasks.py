"""Task endpoints, nested under their task list."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUser, TaskUseCasesDep
from app.api.errors import error_responses
from app.application.schemas import (
    TaskAssignment,
    TaskCreate,
    TaskOut,
    TaskPage,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.domain.entities import TaskPriority, TaskStatus

router = APIRouter(
    prefix="/task-lists/{task_list_id}/tasks",
    tags=["Tasks"],
    responses=error_responses(401, 404),
)


@router.post(
    "",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    responses=error_responses(422),
)
def create_task(
    task_list_id: int, data: TaskCreate, user: CurrentUser, use_cases: TaskUseCasesDep
):
    """Add a task to the list. `due_date`, when given, cannot be in the past."""
    return use_cases.create(user, task_list_id, data)


@router.get("", response_model=TaskPage, summary="List the tasks of a list")
def list_tasks(
    task_list_id: int,
    user: CurrentUser,
    use_cases: TaskUseCasesDep,
    status_filter: Annotated[
        TaskStatus | None, Query(alias="status", description="Only tasks in this status.")
    ] = None,
    priority: Annotated[
        TaskPriority | None, Query(description="Only tasks with this priority.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size.")] = 50,
    offset: Annotated[int, Query(ge=0, description="Tasks to skip.")] = 0,
):
    """Return the tasks of a list, optionally filtered by status and/or priority.

    `completion_percentage` is always computed over **every** task of the list, so it
    reports the progress of the list no matter which filters are applied.
    """
    return use_cases.list(
        user, task_list_id, status=status_filter, priority=priority, limit=limit, offset=offset
    )


@router.get("/{task_id}", response_model=TaskOut, summary="Get a task")
def get_task(task_list_id: int, task_id: int, user: CurrentUser, use_cases: TaskUseCasesDep):
    """Return one task of the list."""
    return use_cases.get(user, task_list_id, task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskOut,
    summary="Update a task",
    responses=error_responses(409, 422),
)
def update_task(
    task_list_id: int,
    task_id: int,
    data: TaskUpdate,
    user: CurrentUser,
    use_cases: TaskUseCasesDep,
):
    """Partially update the content of a task.

    Tasks in `done` cannot be edited (409): reopen them with the status endpoint first.
    Status and assignee have their own endpoints.
    """
    return use_cases.update(user, task_list_id, task_id, data)


@router.patch("/{task_id}/status", response_model=TaskOut, summary="Change the status of a task")
def change_task_status(
    task_list_id: int,
    task_id: int,
    data: TaskStatusUpdate,
    user: CurrentUser,
    use_cases: TaskUseCasesDep,
):
    """Move a task to any status (`pending`, `in_progress`, `done`)."""
    return use_cases.change_status(user, task_list_id, task_id, data.status)


@router.put(
    "/{task_id}/assignee",
    response_model=TaskOut,
    summary="Assign a task",
    responses=error_responses(422),
)
def assign_task(
    task_list_id: int,
    task_id: int,
    data: TaskAssignment,
    user: CurrentUser,
    use_cases: TaskUseCasesDep,
):
    """Set the user responsible for a task, or clear it with `null`.

    The assignee must be the owner or an invited member of the list, and receives a
    **simulated** notification email (written to the log).
    """
    return use_cases.assign(user, task_list_id, task_id, data.assignee_id)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a task")
def delete_task(task_list_id: int, task_id: int, user: CurrentUser, use_cases: TaskUseCasesDep):
    """Delete a task."""
    use_cases.delete(user, task_list_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
