"""Use cases for task lists and their membership."""

from app.application.schemas import InvitationCreate, TaskListCreate, TaskListUpdate
from app.domain.entities import TaskList, User
from app.domain.exceptions import (
    AlreadyMemberError,
    CannotInviteOwnerError,
    DuplicateTaskListNameError,
    NotTaskListOwnerError,
    TaskListNotFoundError,
)
from app.domain.ports import Notifier, TaskListRepository, UserRepository


def get_accessible_task_list(repo: TaskListRepository, user: User, task_list_id: int) -> TaskList:
    """Load a list the user can access.

    Lists the user cannot access are reported as missing (404, not 403) so their
    existence is not leaked to strangers.

    Raises:
        TaskListNotFoundError: if the list does not exist or is not accessible.
    """
    task_list = repo.get(task_list_id)
    if task_list is None or not task_list.is_accessible_by(user):
        raise TaskListNotFoundError(task_list_id)
    return task_list


class TaskListUseCases:
    def __init__(
        self, task_lists: TaskListRepository, users: UserRepository, notifier: Notifier
    ) -> None:
        self._task_lists = task_lists
        self._users = users
        self._notifier = notifier

    def create(self, user: User, data: TaskListCreate) -> TaskList:
        """Create a list owned by ``user``.

        Raises:
            DuplicateTaskListNameError: if ``user`` already owns a list with that name.
        """
        if self._task_lists.name_exists(user.id, data.name):
            raise DuplicateTaskListNameError(data.name)
        return self._task_lists.add(
            TaskList(name=data.name, description=data.description, owner_id=user.id)
        )

    def list(self, user: User) -> list[TaskList]:
        """Return every list ``user`` owns or was invited to."""
        return self._task_lists.list_accessible_by(user)

    def get(self, user: User, task_list_id: int) -> TaskList:
        """Return one accessible list (see :func:`get_accessible_task_list`)."""
        return get_accessible_task_list(self._task_lists, user, task_list_id)

    def update(self, user: User, task_list_id: int, data: TaskListUpdate) -> TaskList:
        """Rename or re-describe a list. Owner and members may edit.

        Raises:
            TaskListNotFoundError: if not accessible.
            DuplicateTaskListNameError: if the owner already has a list with the new name.
        """
        task_list = get_accessible_task_list(self._task_lists, user, task_list_id)
        changes = data.model_dump(exclude_unset=True)
        new_name = changes.get("name")
        if new_name and self._task_lists.name_exists(
            task_list.owner_id, new_name, exclude_id=task_list.id
        ):
            raise DuplicateTaskListNameError(new_name)
        for field, value in changes.items():
            setattr(task_list, field, value)
        return self._task_lists.update(task_list)

    def delete(self, user: User, task_list_id: int) -> None:
        """Delete a list and all its tasks.

        Raises:
            TaskListNotFoundError: if not accessible.
            NotTaskListOwnerError: if ``user`` is a member but not the owner.
        """
        task_list = self._get_owned(user, task_list_id)
        self._task_lists.delete(task_list.id)

    def invite(self, user: User, task_list_id: int, data: InvitationCreate) -> TaskList:
        """Share a list with someone by email and send them a (simulated) invitation.

        Raises:
            TaskListNotFoundError: if not accessible.
            NotTaskListOwnerError: if ``user`` is not the owner.
            CannotInviteOwnerError: if the email is the owner's own.
            AlreadyMemberError: if the email was already invited.
        """
        task_list = self._get_owned(user, task_list_id)
        email = data.email.lower()
        if email == user.email:
            raise CannotInviteOwnerError()
        if email in task_list.member_emails:
            raise AlreadyMemberError(email)
        task_list = self._task_lists.add_member(task_list.id, email)
        has_account = self._users.get_by_email(email) is not None
        next_step = (
            "Log in to see it."
            if has_account
            else "Create an account with this email address to get access."
        )
        self._notifier.send_email(
            to=email,
            subject=f"{user.full_name} invited you to '{task_list.name}'",
            body=f"{user.full_name} ({user.email}) shared the task list "
            f"'{task_list.name}' with you. {next_step}",
        )
        return task_list

    def _get_owned(self, user: User, task_list_id: int) -> TaskList:
        task_list = get_accessible_task_list(self._task_lists, user, task_list_id)
        if not task_list.is_owner(user):
            raise NotTaskListOwnerError()
        return task_list
