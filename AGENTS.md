# AGENTS.md

Guide for anyone (human or AI agent) changing this repository. Read it before writing
code. The *why* behind each rule lives in [DECISION_LOG.md](DECISION_LOG.md), and how to
run things lives in [README.md](README.md).

## Commands

Always go through the Makefile. It prepares `.env`, combines the right Compose files and
waits for the services to be healthy.

| Task | Command |
| --- | --- |
| First setup, or after pulling | `make all` |
| Develop with hot reload | `make dev`, then `make dev-logs` |
| Load demo data | `make seed` (accounts use `Password123!`) |
| Format | `make format` |
| Lint + unit/integration tests | `make check` |
| Real HTTP tests against the running stack | `make e2e` (needs `make dev` or `make up`) |
| Dependency vulnerability scan | `make audit` |

**Definition of done:** `make check` and `make e2e` pass, coverage stays above 75%, and
the docs affected by the change are updated.

## Architecture

```text
api  ──►  application  ──►  domain  ◄──  infrastructure
```

Dependencies point **inwards only**. This is the most important rule in the repo.

| Layer | Path | Contains | Must not import |
| --- | --- | --- | --- |
| Domain | `app/domain/` | Entities (dataclasses), business rules, exceptions, ports (`Protocol`s) | FastAPI, Pydantic, SQLAlchemy, anything in `app/` outside `domain` |
| Application | `app/application/` | Use cases (`use_cases/`), Pydantic DTOs (`schemas.py`) | FastAPI, SQLAlchemy, `app.infrastructure`, `app.api` |
| Infrastructure | `app/infrastructure/` | Adapters that implement the ports: SQLAlchemy models and repositories, JWT, scrypt, rate limiter, notifier | `app.api`, `app.application.use_cases` |
| API | `app/api/` | Routers, dependency wiring, error translation, middleware | Business rules (they belong in domain or application) |

- `app/main.py` is the only place that builds the app and its long-lived objects
  (engine, notifier, hasher, rate limiter on `app.state`).
- `app/api/dependencies.py` is the only place that wires adapters into use cases.
- The `Session` never leaves infrastructure and the API layer. Use cases only see ports.

## Adding a feature

Work from the inside out:

1. **Domain.** Add or extend entities in `entities.py`. A rule that depends only on the
   entity's own data is a method or function there (see `Task.ensure_editable`,
   `validate_due_date`).
2. **Exceptions.** Each new failure is a subclass of the right category in
   `exceptions.py` (`NotFoundError`, `ConflictError`, `PermissionDeniedError`,
   `AuthenticationError`, `BusinessRuleViolationError`), with a stable snake_case `code`.
   Do not touch `api/errors.py`: categories are already mapped to HTTP statuses.
3. **Ports.** If the use case needs something new from the outside world, add a method
   to a `Protocol` in `ports.py`, with a docstring that states the contract.
4. **Use case.** Add a method to the aggregate's class in `application/use_cases/`. It
   receives the current `User` and validated DTOs, enforces access (reuse
   `get_accessible_task_list`), and raises domain exceptions. The docstring lists
   everything it raises.
5. **DTOs.** Input and output models go in `application/schemas.py`:
   - inputs extend `_Input` (strips whitespace, `extra="forbid"`) and outputs extend
     `_Output`;
   - any text that can end up in an email uses `SingleLine`;
   - every field gets limits (`min_length`, `max_length`, `ge`, ...) and, where useful,
     a `description` and `examples`.
6. **Adapter.** Implement the new port method in infrastructure. Repositories map rows
   to entities (`_to_*` helpers) and commit on each write (ADR-006). Also update the
   in-memory fakes in `tests/fakes.py`.
7. **Migration.** Any change to `infrastructure/db/models.py` needs a new Alembic
   revision:
   - autogenerate it, then review it by hand;
   - make it portable to both PostgreSQL and SQLite;
   - keep `alembic check` clean;
   - never edit a migration that has already been merged.
8. **Endpoint.** Add it in the right router under `app/api/routers/`:
   - set `response_model`, the status code and a `summary`;
   - list the errors it can return with `responses=error_responses(...)`;
   - write the docstring, which becomes the Swagger description;
   - add `dependencies=throttled` if it is unauthenticated or sensitive.
9. **Tests.** Write them at each level (see [Testing](#testing)).
10. **Docs.** Update the README (API table, config, Make targets) and add or amend an
    ADR in `DECISION_LOG.md` when the change involves a real decision or trade-off.

## Conventions

**Code**

- Python 3.12, type hints everywhere, and `X | None` rather than `Optional`.
- Formatting by black and isort (line length 99). Lint with flake8 and ruff (bugbear,
  pyupgrade, simplify, pytest-style, naming, bandit).
- **Never silence a linter** (`# noqa`, `type: ignore`, `pylint: disable`). Fix the code.
  A suppression that already exists somewhere is not precedent. If a rule really does
  not apply, explain why and ask before adding an exception to the config.
- Everything in English: identifiers, docstrings, comments, API messages and docs.
- Public functions and classes get a docstring. Use cases and ports document `Raises:`.
- Comments explain *why*, not *what*. A deliberate shortcut gets a `ponytail:` comment
  naming its limit and upgrade path (see `infrastructure/rate_limit.py`).
- Prefer the standard library and what is already installed. A new dependency needs a
  reason stated in the commit or an ADR, and `make audit` must stay clean.

**API**

- Resources are nested (`/task-lists/{id}/tasks/{task_id}`). Use `PATCH` for partial
  updates (`model_dump(exclude_unset=True)`) and sub-resources for state changes
  (`/status`, `/assignee`).
- Resources the caller cannot access answer **404**, never 403. Use 403 only for
  "you can see it, but you are not the owner".
- Errors always follow `{"code", "message"}`. Never return raw exception text or stack
  traces.

## Security rules

These are non-negotiable. See ADR-017.

- No secrets in code or Compose files. Settings without a safe default have no default
  (`jwt_secret`), and `make env` generates real values.
- Every new token type gets its own purpose (`typ`), and `decode` must be called with
  that purpose.
- Access by email (membership) requires `email_verified`. Keep
  `TaskList.is_accessible_by` and the SQL in `list_accessible_by` in sync, and test both.
- Do not reveal whether an email or an id exists: use the same error and the same work
  for "missing" and "not allowed".
- Validate at the boundary: bounded lengths, no control characters in single-line text,
  `extra="forbid"`.
- Unauthenticated endpoints are rate limited (`dependencies=throttled`).
- Never log passwords, tokens or secrets. The only exception is the simulated email
  notifier, which exists precisely to show the email content in development.
- Containers keep running as non-root on a read-only filesystem with all capabilities
  dropped. If something needs to write, give it a `tmpfs`.

## Testing

| Suite | Path | What it is for | How it runs |
| --- | --- | --- | --- |
| Unit | `tests/unit/` | Domain rules, adapters without I/O, use cases with in-memory fakes | `make test` |
| Integration | `tests/integration/` | Real app over HTTP (`TestClient`) and SQLAlchemy on in-memory SQLite, migrations vs models | `make test` |
| End to end | `tests/e2e/` | Real HTTP against the running Docker stack and PostgreSQL | `make e2e` |

- Use plain `assert` statements. Never use `self.assertEqual`-style methods.
- Mark every module with `pytestmark = pytest.mark.unit`, `integration` or `e2e`.
- Useful fixtures in `tests/conftest.py`:
  - `client`, and `make_client(**settings)` for a custom configuration;
  - `login(email, verify=True)`, which returns auth headers;
  - `owner`, `task_list`;
  - `notifier`, which records every email sent.
- Each bug fix comes with a test that fails without the fix.
- The e2e suite creates users with unique emails on every run, so it is safe against a
  database that already has data (including the seed).
- `test_migrations.py` fails if models and migrations drift apart. Do not work around it,
  write the migration.

## Git

- Branch from `main`. Keep commits small and focused, with the code, tests and docs of
  one change together.
- Commit messages: an imperative subject line of 72 characters or fewer, a blank line,
  then plain prose explaining what changed and why. Point at concrete cases and avoid
  filler. Do not use em dashes, and use commas, colons or parentheses instead.
- Never commit `.env`, local databases, coverage output or anything listed in
  `.gitignore`.
- Before pushing, run `make check`, and `make e2e` if an endpoint changed.
