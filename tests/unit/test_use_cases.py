"""Use cases exercised against in-memory fakes: no database, no HTTP."""

from datetime import date

import pytest

from app.application.schemas import (
    InvitationCreate,
    TaskCreate,
    TaskListCreate,
    TaskListUpdate,
    TaskUpdate,
    UserCreate,
)
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.task_lists import TaskListUseCases
from app.application.use_cases.tasks import TaskUseCases
from app.domain.entities import TaskPriority, TaskStatus
from app.domain.exceptions import (
    AlreadyMemberError,
    AssigneeWithoutAccessError,
    CannotInviteOwnerError,
    DueDateInPastError,
    DuplicateTaskListNameError,
    EmailAlreadyRegisteredError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
    NotTaskListOwnerError,
    TaskCompletedError,
    TaskListNotFoundError,
    TaskNotFoundError,
)
from app.infrastructure.security import JwtTokenService, ScryptPasswordHasher
from tests.fakes import (
    InMemoryTaskListRepository,
    InMemoryTaskRepository,
    InMemoryUserRepository,
    RecordingNotifier,
)

pytestmark = pytest.mark.unit

TODAY = date(2026, 1, 10)


@pytest.fixture
def users():
    return InMemoryUserRepository()


@pytest.fixture
def notifier():
    return RecordingNotifier()


@pytest.fixture
def tokens():
    return JwtTokenService("x" * 32)


@pytest.fixture
def auth(users, tokens, notifier):
    return AuthUseCases(users, ScryptPasswordHasher(n=2**10), tokens, notifier)


@pytest.fixture
def lists(users, notifier):
    return TaskListUseCases(InMemoryTaskListRepository(), users, notifier)


@pytest.fixture
def tasks(lists, users, notifier):
    # Share the list repository with ``lists`` so both see the same data.
    return TaskUseCases(
        lists._task_lists, InMemoryTaskRepository(), users, notifier, today=lambda: TODAY
    )


@pytest.fixture
def register(auth, notifier):
    def _register(email, verify=True):
        user = auth.register(UserCreate(email=email, full_name=email.title(), password="p" * 8))
        if verify:
            user = auth.verify_email(notifier.verification_token(user.email))
        notifier.sent.clear()
        return user

    return _register


@pytest.fixture
def owner(register):
    return register("owner@example.com")


@pytest.fixture
def owned_list(lists, owner):
    return lists.create(owner, TaskListCreate(name="Home"))


# --- Auth -----------------------------------------------------------------------------------


def test_register_normalises_email_and_hashes_password(register):
    user = register("Ada@Example.com", verify=False)

    assert user.email == "ada@example.com"
    assert user.hashed_password.startswith("scrypt$")
    assert not user.email_verified


def test_register_sends_verification_and_verify_is_idempotent(auth, notifier):
    user = auth.register(UserCreate(email="ada@example.com", full_name="Ada", password="p" * 8))
    token = notifier.verification_token("ada@example.com")

    assert auth.verify_email(token).email_verified
    assert auth.verify_email(token).id == user.id


def test_access_token_cannot_verify_email(auth, owner):
    with pytest.raises(InvalidTokenError):
        auth.verify_email(auth.login(owner.email, "p" * 8))


def test_verification_token_cannot_authenticate(auth, register, notifier):
    user = register("ada@example.com", verify=False)
    auth.resend_verification(user)

    with pytest.raises(InvalidTokenError):
        auth.authenticate(notifier.verification_token(user.email))


def test_resend_verification_rejects_verified_users(auth, owner):
    with pytest.raises(EmailAlreadyVerifiedError):
        auth.resend_verification(owner)


def test_register_rejects_duplicate_email(register):
    register("ada@example.com")

    with pytest.raises(EmailAlreadyRegisteredError):
        register("ADA@example.com")


def test_login_and_authenticate(auth, owner):
    token = auth.login(" OWNER@example.com ", "p" * 8)

    assert auth.authenticate(token).id == owner.id


@pytest.mark.parametrize(
    ("email", "password"), [("owner@example.com", "wrong-pass"), ("ghost@example.com", "p" * 8)]
)
def test_login_rejects_bad_credentials(auth, owner, email, password):
    with pytest.raises(InvalidCredentialsError):
        auth.login(email, password)


def test_authenticate_rejects_token_of_unknown_user(auth, tokens):
    with pytest.raises(InvalidTokenError):
        auth.authenticate(tokens.issue("999", "access"))


# --- Task lists -----------------------------------------------------------------------------


def test_task_list_names_are_unique_per_owner(lists, owner, register, owned_list):
    with pytest.raises(DuplicateTaskListNameError):
        lists.create(owner, TaskListCreate(name="Home"))

    other = register("other@example.com")
    assert lists.create(other, TaskListCreate(name="Home")).owner_id == other.id


def test_rename_to_existing_name_is_rejected(lists, owner, owned_list):
    lists.create(owner, TaskListCreate(name="Work"))

    with pytest.raises(DuplicateTaskListNameError):
        lists.update(owner, owned_list.id, TaskListUpdate(name="Work"))
    assert lists.update(owner, owned_list.id, TaskListUpdate(name="Home")).name == "Home"


def test_strangers_cannot_see_a_list(lists, register, owned_list):
    stranger = register("stranger@example.com")

    with pytest.raises(TaskListNotFoundError):
        lists.get(stranger, owned_list.id)
    assert lists.list(stranger) == []


def test_invite_grants_access_and_sends_email(lists, owner, register, owned_list, notifier):
    lists.invite(owner, owned_list.id, InvitationCreate(email="Friend@Example.com"))

    assert [email["to"] for email in notifier.sent] == ["friend@example.com"]
    assert "Create an account" in notifier.sent[0]["body"]
    friend = register("friend@example.com")
    assert lists.get(friend, owned_list.id).member_emails == ["friend@example.com"]


def test_invitation_needs_a_verified_email(lists, owner, register, owned_list):
    lists.invite(owner, owned_list.id, InvitationCreate(email="friend@example.com"))
    squatter = register("friend@example.com", verify=False)

    with pytest.raises(TaskListNotFoundError):
        lists.get(squatter, owned_list.id)


def test_invite_existing_user_tells_them_to_log_in(lists, owner, register, owned_list, notifier):
    register("friend@example.com")

    lists.invite(owner, owned_list.id, InvitationCreate(email="friend@example.com"))

    assert "Log in" in notifier.sent[0]["body"]


def test_invite_rules(lists, owner, register, owned_list):
    with pytest.raises(CannotInviteOwnerError):
        lists.invite(owner, owned_list.id, InvitationCreate(email=owner.email))

    lists.invite(owner, owned_list.id, InvitationCreate(email="friend@example.com"))
    with pytest.raises(AlreadyMemberError):
        lists.invite(owner, owned_list.id, InvitationCreate(email="friend@example.com"))

    friend = register("friend@example.com")
    with pytest.raises(NotTaskListOwnerError):
        lists.invite(friend, owned_list.id, InvitationCreate(email="third@example.com"))


def test_only_owner_can_delete(lists, owner, register, owned_list):
    lists.invite(owner, owned_list.id, InvitationCreate(email="friend@example.com"))
    friend = register("friend@example.com")

    with pytest.raises(NotTaskListOwnerError):
        lists.delete(friend, owned_list.id)
    lists.delete(owner, owned_list.id)
    with pytest.raises(TaskListNotFoundError):
        lists.get(owner, owned_list.id)


# --- Tasks ----------------------------------------------------------------------------------


def test_create_task_rejects_past_due_date(tasks, owner, owned_list):
    with pytest.raises(DueDateInPastError):
        tasks.create(owner, owned_list.id, TaskCreate(title="t", due_date=date(2026, 1, 9)))

    task = tasks.create(owner, owned_list.id, TaskCreate(title="t", due_date=TODAY))
    assert task.due_date == TODAY


def test_list_filters_and_completion(tasks, owner, owned_list):
    for title, status, priority in [
        ("a", TaskStatus.DONE, TaskPriority.HIGH),
        ("b", TaskStatus.DONE, TaskPriority.LOW),
        ("c", TaskStatus.PENDING, TaskPriority.HIGH),
        ("d", TaskStatus.IN_PROGRESS, TaskPriority.HIGH),
    ]:
        tasks.create(
            owner, owned_list.id, TaskCreate(title=title, status=status, priority=priority)
        )

    page = tasks.list(owner, owned_list.id, priority=TaskPriority.HIGH, limit=2)

    assert [t.title for t in page.items] == ["a", "c"]
    assert page.total == 3
    assert page.completion_percentage == 50.0


def test_done_task_must_be_reopened_before_editing(tasks, owner, owned_list):
    task = tasks.create(owner, owned_list.id, TaskCreate(title="t"))
    tasks.change_status(owner, owned_list.id, task.id, TaskStatus.DONE)

    with pytest.raises(TaskCompletedError):
        tasks.update(owner, owned_list.id, task.id, TaskUpdate(title="new"))

    tasks.change_status(owner, owned_list.id, task.id, TaskStatus.PENDING)
    assert tasks.update(owner, owned_list.id, task.id, TaskUpdate(title="new")).title == "new"


def test_update_validates_new_due_date_only(tasks, owner, owned_list):
    task = tasks.create(owner, owned_list.id, TaskCreate(title="t"))

    with pytest.raises(DueDateInPastError):
        tasks.update(owner, owned_list.id, task.id, TaskUpdate(due_date=date(2020, 1, 1)))
    assert tasks.update(owner, owned_list.id, task.id, TaskUpdate(due_date=None)).due_date is None


def test_task_must_belong_to_the_list(tasks, lists, owner, owned_list):
    task = tasks.create(owner, owned_list.id, TaskCreate(title="t"))
    other_list = lists.create(owner, TaskListCreate(name="Other"))

    with pytest.raises(TaskNotFoundError):
        tasks.get(owner, other_list.id, task.id)


def test_assign_rules_and_notification(tasks, lists, owner, register, owned_list, notifier):
    task = tasks.create(owner, owned_list.id, TaskCreate(title="Buy milk"))
    stranger = register("stranger@example.com")

    with pytest.raises(AssigneeWithoutAccessError):
        tasks.assign(owner, owned_list.id, task.id, 999)
    with pytest.raises(AssigneeWithoutAccessError):
        tasks.assign(owner, owned_list.id, task.id, stranger.id)

    lists.invite(owner, owned_list.id, InvitationCreate(email=stranger.email))
    notifier.sent.clear()
    assert tasks.assign(owner, owned_list.id, task.id, stranger.id).assignee_id == stranger.id
    assert notifier.sent[0]["to"] == stranger.email

    assert tasks.assign(owner, owned_list.id, task.id, None).assignee_id is None


def test_self_assignment_sends_no_email(tasks, owner, owned_list, notifier):
    task = tasks.create(owner, owned_list.id, TaskCreate(title="t"))

    tasks.assign(owner, owned_list.id, task.id, owner.id)

    assert notifier.sent == []


def test_delete_task(tasks, owner, owned_list):
    task = tasks.create(owner, owned_list.id, TaskCreate(title="t"))

    tasks.delete(owner, owned_list.id, task.id)

    with pytest.raises(TaskNotFoundError):
        tasks.get(owner, owned_list.id, task.id)
