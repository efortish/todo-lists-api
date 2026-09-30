"""Task list endpoints."""

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, TaskListUseCasesDep
from app.api.errors import error_responses
from app.application.schemas import InvitationCreate, TaskListCreate, TaskListOut, TaskListUpdate

router = APIRouter(prefix="/task-lists", tags=["Task lists"], responses=error_responses(401))


@router.post(
    "",
    response_model=TaskListOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task list",
    responses=error_responses(409),
)
def create_task_list(data: TaskListCreate, user: CurrentUser, use_cases: TaskListUseCasesDep):
    """Create a list owned by the current user. Names are unique per owner."""
    return use_cases.create(user, data)


@router.get("", response_model=list[TaskListOut], summary="List my task lists")
def list_task_lists(user: CurrentUser, use_cases: TaskListUseCasesDep):
    """Return the lists you own plus the ones you were invited to."""
    return use_cases.list(user)


@router.get(
    "/{task_list_id}",
    response_model=TaskListOut,
    summary="Get a task list",
    responses=error_responses(404),
)
def get_task_list(task_list_id: int, user: CurrentUser, use_cases: TaskListUseCasesDep):
    """Return one list you own or were invited to."""
    return use_cases.get(user, task_list_id)


@router.patch(
    "/{task_list_id}",
    response_model=TaskListOut,
    summary="Update a task list",
    responses=error_responses(404, 409),
)
def update_task_list(
    task_list_id: int, data: TaskListUpdate, user: CurrentUser, use_cases: TaskListUseCasesDep
):
    """Partially update a list: only the fields you send are changed."""
    return use_cases.update(user, task_list_id, data)


@router.delete(
    "/{task_list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task list",
    responses=error_responses(403, 404),
)
def delete_task_list(task_list_id: int, user: CurrentUser, use_cases: TaskListUseCasesDep):
    """Delete a list **and all of its tasks**. Only the owner can do it."""
    use_cases.delete(user, task_list_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{task_list_id}/invitations",
    response_model=TaskListOut,
    status_code=status.HTTP_201_CREATED,
    summary="Invite someone to a task list",
    responses=error_responses(403, 404, 409, 422),
)
def invite_to_task_list(
    task_list_id: int, data: InvitationCreate, user: CurrentUser, use_cases: TaskListUseCasesDep
):
    """Share the list with an email address and send a **simulated** invitation email.

    The email is written to the application log instead of being delivered. The
    invitee does not need an account yet: access is granted as soon as they register
    with that address. Only the owner can invite.
    """
    return use_cases.invite(user, task_list_id, data)
