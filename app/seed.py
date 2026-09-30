"""Load demo data into the configured database: ``make seed``.

Data goes through the same use cases as the API, so passwords are hashed and every
business rule applies. Running it again is a no-op. The demo password comes from the
``SEED_PASSWORD`` environment variable, and seeding is refused in production, where
accounts with a published password would be a way in.
"""

import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.application.schemas import InvitationCreate, TaskCreate, TaskListCreate, UserCreate
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.task_lists import TaskListUseCases
from app.application.use_cases.tasks import TaskUseCases
from app.config import get_settings
from app.domain.entities import TaskPriority, TaskStatus, User
from app.domain.ports import PasswordHasher
from app.infrastructure.db.repositories import (
    SqlTaskListRepository,
    SqlTaskRepository,
    SqlUserRepository,
)
from app.infrastructure.db.session import build_engine, build_session_factory
from app.infrastructure.security import JwtTokenService, ScryptPasswordHasher

P, IP, D = TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.DONE
LOW, MED, HIGH = TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH

# (title, status, priority, due in days or None, assignee key or None)
SPRINT_TASKS = [
    ("Design the database schema", D, HIGH, None, "ana"),
    ("Set up the CI pipeline", D, MED, None, "bob"),
    ("Implement authentication", IP, HIGH, 2, "ana"),
    ("Add rate limiting to login", P, HIGH, 1, "bob"),
    ("Write the API documentation", P, MED, 3, "bob"),
    ("Run a load test", P, LOW, 10, None),
]
HOME_TASKS = [
    ("Pay the electricity bill", D, HIGH, None, None),
    ("Buy groceries", P, HIGH, 1, None),
    ("Fix the kitchen tap", P, LOW, None, None),
]
READING_TASKS = [
    ("The Pragmatic Programmer", D, LOW, None, None),
    ("Clean Architecture", IP, MED, 14, None),
    ("Designing Data-Intensive Applications", P, HIGH, 30, None),
]


class _Outbox:
    """Collects the simulated emails so the summary can show the verification token."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_email(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


@dataclass
class SeedResult:
    users: dict[str, User]
    task_lists: int
    tasks: int
    carla_verification_token: str


def seed(
    session: Session, hasher: PasswordHasher, tokens: JwtTokenService, password: str
) -> SeedResult | None:
    """Create the demo data with ``password`` for every account, or return ``None`` if it
    is already there."""
    users_repo = SqlUserRepository(session)
    if users_repo.get_by_email("ana@example.com") is not None:
        return None

    outbox = _Outbox()
    auth = AuthUseCases(users_repo, hasher, tokens, outbox)
    lists_repo = SqlTaskListRepository(session)
    lists = TaskListUseCases(lists_repo, users_repo, outbox)
    tasks = TaskUseCases(lists_repo, SqlTaskRepository(session), users_repo, outbox)

    users = {}
    for key, name, verified in [
        ("ana", "Ana Owner", True),
        ("bob", "Bob Member", True),
        ("carla", "Carla Unverified", False),
    ]:
        user = auth.register(
            UserCreate(email=f"{key}@example.com", full_name=name, password=password)
        )
        if verified:
            user.email_verified = True
            user = users_repo.update(user)
        users[key] = user
    carla_token = tokens.issue(str(users["carla"].id), "email_verification", timedelta(days=1))

    def fill(owner: User, name: str, description: str, rows: list) -> None:
        task_list = lists.create(owner, TaskListCreate(name=name, description=description))
        for email in invitees.get(name, []):
            lists.invite(owner, task_list.id, InvitationCreate(email=email))
        for title, status, priority, due_in, assignee in rows:
            due = date.today() + timedelta(days=due_in) if due_in is not None else None
            task = tasks.create(
                owner,
                task_list.id,
                TaskCreate(title=title, status=status, priority=priority, due_date=due),
            )
            if assignee:
                tasks.assign(owner, task_list.id, task.id, users[assignee].id)

    # Carla is invited but unverified: she must verify her email to see "Sprint 1".
    invitees = {"Sprint 1": ["bob@example.com", "carla@example.com"]}
    fill(users["ana"], "Sprint 1", "Backend work for the first sprint", SPRINT_TASKS)
    fill(users["ana"], "Home", "Chores and errands", HOME_TASKS)
    fill(users["bob"], "Reading list", "Books to read this year", READING_TASKS)

    return SeedResult(
        users=users,
        task_lists=3,
        tasks=len(SPRINT_TASKS) + len(HOME_TASKS) + len(READING_TASKS),
        carla_verification_token=carla_token,
    )


def main() -> None:
    settings = get_settings()
    password = os.environ.get("SEED_PASSWORD", "")
    if settings.app_env == "production":
        sys.exit("Refusing to seed demo accounts with a known password in production.")
    if len(password) < 8:
        sys.exit("Set SEED_PASSWORD (8+ characters). `make seed` does it for you.")

    engine = build_engine(settings.database_url)
    tokens = JwtTokenService(
        settings.jwt_secret, settings.jwt_algorithm, settings.access_token_expire_minutes
    )
    with build_session_factory(engine)() as session:
        result = seed(session, ScryptPasswordHasher(), tokens, password)
    engine.dispose()

    if result is None:
        print("Demo data already present, nothing to do.")
        return
    print(f"Created {len(result.users)} users, {result.task_lists} lists, {result.tasks} tasks.")
    print(f"\nAll accounts use the password: {password}\n")
    print("  ana@example.com    verified    owns 'Sprint 1' (shared with bob) and 'Home'")
    print("  bob@example.com    verified    member of 'Sprint 1', owns 'Reading list'")
    print("  carla@example.com  UNVERIFIED  invited to 'Sprint 1' but cannot see it yet")
    print("\nTo let Carla in, send this to POST /api/v1/auth/verify-email:")
    print(f'  {{"token": "{result.carla_verification_token}"}}')


if __name__ == "__main__":
    main()
