"""Domain exceptions.

Every error the business layer can raise derives from :class:`DomainError`. The
API layer maps each *category* (not each concrete class) to an HTTP status code,
so adding a new error never requires touching the web layer.
"""


class DomainError(Exception):
    """Base class for every business error. ``code`` is a stable, machine readable id."""

    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# --- Categories -----------------------------------------------------------------------------


class NotFoundError(DomainError):
    """The requested resource does not exist (or the caller is not allowed to know it does)."""

    code = "not_found"


class ConflictError(DomainError):
    """The request conflicts with the current state of a resource."""

    code = "conflict"


class PermissionDeniedError(DomainError):
    """The caller is authenticated but not allowed to perform the action."""

    code = "permission_denied"


class AuthenticationError(DomainError):
    """The caller could not be authenticated."""

    code = "authentication_failed"


class BusinessRuleViolationError(DomainError):
    """The request is well formed but breaks a business rule."""

    code = "business_rule_violation"


# --- Concrete errors ------------------------------------------------------------------------


class TaskListNotFoundError(NotFoundError):
    code = "task_list_not_found"

    def __init__(self, task_list_id: int) -> None:
        super().__init__(f"Task list {task_list_id} was not found.")


class TaskNotFoundError(NotFoundError):
    code = "task_not_found"

    def __init__(self, task_id: int) -> None:
        super().__init__(f"Task {task_id} was not found.")


class EmailAlreadyRegisteredError(ConflictError):
    code = "email_already_registered"

    def __init__(self, email: str) -> None:
        super().__init__(f"The email {email!r} is already registered.")


class DuplicateTaskListNameError(ConflictError):
    code = "duplicate_task_list_name"

    def __init__(self, name: str) -> None:
        super().__init__(f"You already own a task list named {name!r}.")


class AlreadyMemberError(ConflictError):
    code = "already_member"

    def __init__(self, email: str) -> None:
        super().__init__(f"{email!r} already has access to this task list.")


class TaskCompletedError(ConflictError):
    code = "task_completed"

    def __init__(self, task_id: int | None) -> None:
        super().__init__(
            f"Task {task_id} is done and cannot be edited. Change its status to reopen it first."
        )


class NotTaskListOwnerError(PermissionDeniedError):
    code = "not_task_list_owner"

    def __init__(self) -> None:
        super().__init__("Only the owner of the task list can perform this action.")


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Incorrect email or password.")


class EmailAlreadyVerifiedError(ConflictError):
    code = "email_already_verified"

    def __init__(self) -> None:
        super().__init__("Your email address is already verified.")


class InvalidTokenError(AuthenticationError):
    code = "invalid_token"

    def __init__(self) -> None:
        super().__init__("The access token is invalid or has expired.")


class DueDateInPastError(BusinessRuleViolationError):
    code = "due_date_in_past"

    def __init__(self) -> None:
        super().__init__("The due date cannot be in the past.")


class AssigneeWithoutAccessError(BusinessRuleViolationError):
    code = "assignee_without_access"

    def __init__(self, user_id: int) -> None:
        # One message whether the user does not exist or cannot access the list, so the
        # endpoint cannot be used to discover which user ids exist.
        super().__init__(
            f"User {user_id} cannot be assigned: only the owner or verified invited members "
            "of the task list can be responsible for its tasks."
        )


class CannotInviteOwnerError(BusinessRuleViolationError):
    code = "cannot_invite_owner"

    def __init__(self) -> None:
        super().__init__("The owner of a task list cannot be invited to it.")
