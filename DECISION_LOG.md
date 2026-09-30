# Decision Log

Architecture Decision Records (ADRs) for the Todo Lists API. Each record states the
context, the decision, the alternatives considered and the consequences, including what
would make us revisit it.

| # | Decision | Status |
| --- | --- | --- |
| [001](#adr-001-layered-architecture-with-ports-and-adapters) | Layered architecture with ports and adapters | Accepted |
| [002](#adr-002-plain-dataclasses-in-the-domain-pydantic-at-the-boundary) | Plain dataclasses in the domain, Pydantic at the boundary | Accepted |
| [003](#adr-003-postgresql-in-production-sqlite-for-tests) | PostgreSQL in production, SQLite for tests | Accepted |
| [004](#adr-004-synchronous-sqlalchemy-20) | Synchronous SQLAlchemy 2.0 | Accepted |
| [005](#adr-005-alembic-migrations-applied-on-container-start) | Alembic migrations applied on container start | Accepted |
| [006](#adr-006-one-commit-per-repository-write-no-unit-of-work) | One commit per repository write, no Unit of Work | Accepted |
| [007](#adr-007-exception-hierarchy-mapped-to-http-by-category) | Exception hierarchy mapped to HTTP by category | Accepted |
| [008](#adr-008-jwt-authentication-with-the-oauth2-password-flow) | JWT authentication with the OAuth2 password flow | Accepted |
| [009](#adr-009-password-hashing-with-stdlib-scrypt) | Password hashing with stdlib scrypt | Accepted |
| [010](#adr-010-sharing-model-owner-plus-members-invited-by-email) | Sharing model: owner plus members invited by email | Accepted |
| [011](#adr-011-simulated-email-behind-a-notifier-port) | Simulated email behind a Notifier port | Accepted |
| [012](#adr-012-resource-design-and-http-semantics) | Resource design and HTTP semantics | Accepted |
| [013](#adr-013-completion-percentage-ignores-filters) | Completion percentage ignores filters | Accepted |
| [014](#adr-014-business-rules) | Business rules | Accepted |
| [015](#adr-015-tooling-lint-format-test) | Tooling: lint, format, test | Accepted |
| [016](#adr-016-docker-image-and-compose-stack) | Docker image and Compose stack | Accepted |
| [017](#adr-017-security-hardening) | Security hardening | Accepted |
| [018](#adr-018-development-container-with-hot-reload) | Development container with hot reload | Accepted |

---

## ADR-001: Layered architecture with ports and adapters

**Context.** The code should be split into clear Domain, Application/Use Cases and
Infrastructure layers, and the business rules must be testable without a web server or a
database.

**Decision.** Four packages with a strict inward dependency rule:

```text
api  ──►  application  ──►  domain  ◄──  infrastructure
```

- `domain`: entities, business rules, exceptions and **ports** (interfaces). No framework
  imports.
- `application`: one class per aggregate (`AuthUseCases`, `TaskListUseCases`,
  `TaskUseCases`) whose methods are the use cases. They receive ports in their constructor.
- `infrastructure`: adapters that implement the ports (SQLAlchemy repositories, JWT,
  scrypt, log-based email).
- `api`: FastAPI routers, dependency wiring and translation of errors to HTTP.

Ports are `typing.Protocol`s, so adapters satisfy them structurally without inheriting
anything.

**Alternatives.** A classic "routers → services → models" layout is shorter but couples
business rules to the ORM. One class per use case (`CreateTaskUseCase`, ...) is more
orthodox but produces around 20 near-empty classes for this scope.

**Consequences.** Use cases are unit tested against in-memory fakes (`tests/fakes.py`) in
milliseconds. The price is a mapping step between ORM rows and entities in the
repositories. Grouping use cases per aggregate should be split if a class grows past a
handful of methods or starts needing unrelated dependencies.

## ADR-002: Plain dataclasses in the domain, Pydantic at the boundary

**Context.** Every payload should be strongly typed and validated once. Pydantic is what
FastAPI uses to validate input and render the OpenAPI schema.

**Decision.** Domain entities are standard-library `dataclass`es holding behaviour
(`TaskList.is_accessible_by`, `Task.ensure_editable`). Pydantic v2 models live in
`application/schemas.py` and are the validated input of the use cases **and** the public
API contract (request and response bodies). Responses are built with
`from_attributes=True` straight from the entities. Inputs strip whitespace and forbid
unknown fields (`extra="forbid"`), so typos like `{"titel": ...}` fail with 422 instead of
being silently ignored.

**Alternatives.** Pydantic models as entities would remove the mapping but tie the domain
to a serialisation library. Separate API schemas and application commands would duplicate
every field for no present benefit.

**Consequences.** One definition per payload, documented once in Swagger. If the public
contract ever needs to diverge from the use-case input (for example, a v2 API), API-specific
schemas can be introduced in `api/` without touching the use cases.

## ADR-003: PostgreSQL in production, SQLite for tests

**Context.** The API needs a real, production-grade database, while tests must be fast
and runnable without Docker.

**Decision.** PostgreSQL 16 runs in Docker Compose. The integration tests use SQLAlchemy
on in-memory SQLite (`StaticPool`, foreign keys enabled with `PRAGMA foreign_keys=ON` so
`ON DELETE CASCADE` / `SET NULL` behave like PostgreSQL). The schema avoids
database-specific features: enums are `VARCHAR` plus a `CHECK` constraint instead of
native PostgreSQL enums.

**Alternatives.** Testcontainers or a Compose-managed test database would give full
production parity at the cost of needing Docker for every test run and much slower
feedback.

**Consequences.** `make test` runs about 70 tests in a few seconds anywhere Python runs.
The migrations are also exercised against SQLite in the suite and against PostgreSQL on
every `make up`. The risk is a PostgreSQL-only behaviour that SQLite does not reproduce
(for example, collation or locking). If the project starts using PostgreSQL-specific
features, a PostgreSQL job in CI should be added.

## ADR-004: Synchronous SQLAlchemy 2.0

**Context.** FastAPI supports both `async def` and plain `def` endpoints.

**Decision.** Endpoints and repositories are synchronous, using the typed SQLAlchemy 2.0
API. FastAPI runs `def` endpoints in its thread pool, so the event loop is never blocked.

**Alternatives.** `asyncpg` with `AsyncSession` brings extra complexity (async fixtures,
lazy loading pitfalls, `greenlet`) that only pays off with very high concurrency or
long I/O waits.

**Consequences.** Simpler code and tests. Throughput is bounded by the thread pool size
(40 by default), which is plenty for this workload. Revisit if profiling shows threads
waiting on the database.

## ADR-005: Alembic migrations applied on container start

**Context.** The schema must be versioned and reproducible.

**Decision.** Alembic owns the schema. `alembic/env.py` reads the same settings as the
app and uses the ORM metadata as the target. The first migration was autogenerated and
then reviewed by hand: autogenerate produced duplicated `CHECK` constraints and a
SQLite-specific `CURRENT_TIMESTAMP` default, both fixed. The container entrypoint runs
`alembic upgrade head` before starting Uvicorn. `tests/integration/test_migrations.py`
applies the migrations and asserts there is no difference with the models, so a model
change without a migration breaks the build.

**Alternatives.** `Base.metadata.create_all()` at startup cannot evolve an existing
schema.

**Consequences.** Running migrations at start is simple and fine for one replica. With
several replicas, migrations should move to a dedicated release step or init job.

## ADR-006: One commit per repository write, no Unit of Work

**Context.** Something has to decide when transactions commit.

**Decision.** Each repository write method commits and refreshes. Every use case performs
at most one logical write, so there is no partial state to roll back. Committing inside
the use case also means errors surface **before** the response is sent, which does not
hold for commits placed in the teardown of a `yield` dependency.

**Alternatives.** A Unit of Work port (`with uow: ...; uow.commit()`) is the textbook
answer and the right one once a use case touches several aggregates atomically.

**Consequences.** Less machinery today. The day a use case needs two writes in one
transaction, introduce a Unit of Work instead of chaining repository calls.

## ADR-007: Exception hierarchy mapped to HTTP by category

**Context.** Clients need consistent, machine-readable errors, and the business layer
should express failures in its own terms rather than in HTTP.

**Decision.** `domain/exceptions.py` defines a base `DomainError` with a stable `code`,
five categories and specific errors under them:

| Category | HTTP | Examples |
| --- | --- | --- |
| `NotFoundError` | 404 | `task_list_not_found`, `task_not_found` |
| `ConflictError` | 409 | `duplicate_task_list_name`, `email_already_registered`, `email_already_verified`, `task_completed`, `already_member` |
| `PermissionDeniedError` | 403 | `not_task_list_owner` |
| `AuthenticationError` | 401 | `invalid_credentials`, `invalid_token` |
| `BusinessRuleViolationError` | 422 | `due_date_in_past`, `assignee_without_access`, `cannot_invite_owner` |

One FastAPI exception handler maps a category to its status and returns
`{"code", "message"}`. Adding a new error never touches the web layer. Every endpoint
documents the error bodies it can return, so they show up in Swagger. A second handler
turns an `IntegrityError` into a 409 as a safety net for races, such as two identical
registrations at the same time, that slip past the use-case checks.

Two errors come from the HTTP layer rather than the domain and use the same body:
`rate_limited` (429, with `Retry-After`) and `request_too_large` (413). See ADR-017.

Request-shape errors keep FastAPI's standard 422 `detail` body, which clients and tools
already understand.

**Consequences.** Clients can switch on `code` instead of parsing messages.

## ADR-008: JWT authentication with the OAuth2 password flow

**Context.** Every endpoint except registration and login must be protected, and anyone
exploring the API should be able to try it from Swagger.

**Decision.** `POST /auth/token` implements the OAuth2 password flow (form fields
`username` and `password`, where `username` is the email). It returns a JWT signed with
PyJWT, holding `sub` (user id), `typ` (purpose), `iss`, `iat` and `exp`. All of them are
required when decoding. The algorithm is pinned on decode and restricted by the settings
to the HMAC family (`HS256`, `HS384`, `HS512`), so `alg=none` and algorithm-confusion
tokens are rejected. Because FastAPI's `OAuth2PasswordBearer` points at this endpoint, the
**Authorize** button in Swagger logs in with an email and password.

The secret has **no default**. It must be at least 32 characters (the RFC 7518 minimum for
HS256), and `make env` generates one with `secrets.token_urlsafe(48)`.

The `typ` claim binds a token to one purpose. The same signing key issues access tokens
(`typ=access`) and email verification tokens (`typ=email_verification`, see ADR-010).
Without the claim, a verification token received by email would also work as an access
token.

Login returns the same `invalid_credentials` error, **after the same hashing work**, for
an unknown email and for a wrong password, so neither the body nor the response time
reveals which emails are registered.

**Alternatives.** A JSON login body is more "REST-y" but loses the Swagger integration.
Session cookies would need CSRF protection.

**Consequences.** Tokens are stateless and cannot be revoked before they expire (60
minutes by default, 24 hours at most). Refresh tokens and revocation are listed in the
future work below. Rate limiting is covered in ADR-017.

## ADR-009: Password hashing with stdlib scrypt

**Context.** Passwords must be stored with a slow, salted hash.

**Decision.** `hashlib.scrypt` from the standard library with `n=2**14, r=8, p=5` and a
16-byte random salt, compared with `hmac.compare_digest`. Those are one of the parameter
sets in the OWASP Password Storage Cheat Sheet. Among the OWASP options it uses the least
memory per hash (16 MiB), so a burst of concurrent logins cannot exhaust the container's
RAM. The hash stores its own parameters (`scrypt$n$r$p$salt$hash`), so the cost can be
raised later while old hashes keep verifying.

When the email does not exist, the hasher verifies against a dummy hash anyway, so both
login failures take the same time.

**Alternatives.** `passlib` is unmaintained and has known incompatibilities with recent
`bcrypt` releases. `argon2-cffi` is the modern best choice but adds a compiled
dependency.

**Consequences.** No extra dependency, and scrypt is a memory-hard KDF recommended by
OWASP. Switching to Argon2id later is a new adapter behind the `PasswordHasher` port.

## ADR-010: Sharing model: owner plus members invited by email

**Context.** Task assignment and email invitations only make sense if
more than one person can work on a list.

**Decision.** Every list has one owner. The owner can invite people **by email**, stored
in `task_list_members(task_list_id, email)`. Access is granted to the owner and to any
user whose email is a member **and verified**, so a person can be invited **before** they
have an account.

Verification is not optional here. Without it, anyone could register with an invitee's
address before the real person does and read the list. Registration sends a
(simulated) email with a token (`typ=email_verification`, 24 hours). `POST
/auth/verify-email` marks the address as verified, and `POST /auth/verify-email/resend`
issues a new token. Unverified users can still log in and manage their own lists.
Invitations simply do not grant them anything yet. The rule lives in
`TaskList.is_accessible_by`, and the SQL of `list_accessible_by` mirrors it. A test covers
each of them.

| Action | Owner | Member | Anyone else |
| --- | --- | --- | --- |
| Read the list, manage its tasks, rename it | ✅ | ✅ | 404 |
| Invite people, delete the list | ✅ | 403 | 404 |

Lists a user cannot access return **404, not 403**, so strangers cannot probe which ids
exist. A task can only be assigned to a user who can access its list. An unknown
assignee id and an assignee without access produce the same error, so the endpoint cannot
be used to enumerate user ids.

**Alternatives.** Storing members by user id is simpler but would force invitees to
register before being invited, which defeats the purpose of an email invitation.

**Consequences.** Accepting or declining invitations, removing members and roles beyond
owner and member are left as future work.

## ADR-011: Simulated email behind a Notifier port

**Context.** Users are notified by email (invitations, assignments, verification), but
the project does not integrate a real email provider yet.

**Decision.** A `Notifier` port with `send_email(to, subject, body)`. The production
adapter, `LoggingEmailNotifier`, writes the message to the application log (visible with
`make logs`). Tests inject a `RecordingNotifier` and assert on what was "sent". Emails are
sent to verify an address, when someone is invited to a list, and when someone is
assigned a task by another user.

**Consequences.** Sending is synchronous. A real provider (SMTP, SES) should be called from
a background task or a queue with retries, so a slow mail server never slows down or fails
a request. Only the adapter changes.

## ADR-012: Resource design and HTTP semantics

**Decision.**

- **Versioned prefix** `/api/v1`.
- **Nested resources.** Tasks live under `/task-lists/{id}/tasks/{task_id}`. A task
  requested under the wrong list is a 404, so ids cannot be mixed across lists.
- **PATCH for partial updates** with explicit `null` semantics: an omitted field is left
  unchanged. `null` clears nullable fields (`description`, `due_date`) and is rejected
  with 422 for required ones (`name`, `title`, `priority`).
- **Status as a sub-resource.** `PATCH .../status` is the documented way to change the
  status, and the only way to reopen a done task (see ADR-014). The general `PATCH` does
  not accept `status`.
- **Assignment as a sub-resource.** `PUT .../assignee` with `{"assignee_id": 2 | null}`
  is idempotent and makes the notification side effect explicit.
- **Pagination** with `limit` (1 to 100, default 50) and `offset`. The response includes
  `total`.
- **Status codes.** 201 on creation, 204 on deletion, and the error mapping from ADR-007.
- **Swagger.** Every route has a summary and a description (the endpoint docstring),
  field descriptions and examples, grouped by tags and documenting its error responses.

## ADR-013: Completion percentage ignores filters

**Context.** "List all the tasks of a list with filters by status or priority and an
extra field with the completion percentage" is ambiguous: the percentage could describe
the filtered page or the whole list.

**Decision.** `completion_percentage` is `done / total * 100` over **all** tasks of the
list, rounded to two decimals. An empty list is `0.0`. It is computed in the database with
a `GROUP BY status` count, independent of filters and pagination.

**Rationale.** A percentage over a status-filtered set is meaningless: it is always 0% or
100%. The useful number is the progress of the list. `total` already tells the client how
many tasks match the filters.

## ADR-014: Business rules

| Rule | Where | Error |
| --- | --- | --- |
| List names are unique per owner (not globally) | Use case plus DB unique constraint | 409 `duplicate_task_list_name` |
| Emails are unique and case-insensitive (stored lower-cased) | Use case plus DB unique constraint | 409 `email_already_registered` |
| A due date cannot be in the past, checked only when it is set, so an overdue task can still be edited | `validate_due_date` | 422 `due_date_in_past` |
| A `done` task cannot be edited, it must be reopened through the status endpoint first | `Task.ensure_editable` | 409 `task_completed` |
| Any status transition is allowed, including reopening | `change_status` | |
| Assignees must have access to the list (unknown ids get the same error) | `TaskUseCases.assign` | 422 `assignee_without_access` |
| Invitations only grant access to verified emails | `TaskList.is_accessible_by` | 404 on the list |
| The owner cannot invite themselves, nor invite the same email twice | `TaskListUseCases.invite` | 422 / 409 |
| Deleting a list deletes its tasks and memberships. Deleting a user unassigns their tasks | DB `ON DELETE CASCADE` / `SET NULL` | |

"Today" is injected into `TaskUseCases`, so date rules are tested deterministically.

## ADR-015: Tooling: lint, format, test

**Decision.**

- **black** (line length 99) and **isort** (`profile = "black"`) for formatting.
- **flake8**, configured in `.flake8` (ignores `E203` and `W503`, which conflict with
  black). **ruff** is also configured, with bugbear, pyupgrade,
  simplify, pytest-style, naming and bandit (security) rules. The code has no inline
  suppressions (`noqa`): every finding was fixed.
- **pytest** with `pytest-cov`. `pytest.ini` sets the coverage threshold
  (`--cov-fail-under=75`) and registers the `unit`, `integration` and `e2e` markers.
  Tests use plain `assert`.
- **End-to-end suite** (`make e2e`) runs over real HTTP against the running stack and
  PostgreSQL. It closes the gap left by running integration tests on SQLite (ADR-003).
  It signs email verification tokens with the stack's own `JWT_SECRET` instead of
  scraping container logs, so it needs no Docker access. Actual email sending is covered
  by the integration tests.
- **pip-audit** (`make audit`) checks the installed dependencies against the PyPA
  advisory database.
- **pyproject.toml** is the single source of dependencies. The Docker build reads the
  runtime dependencies from it, so there is no `requirements.txt` to keep in sync.

**Consequences.** Versions are ranges, not a lock file. See future work.

## ADR-016: Docker image and Compose stack

**Decision.**

- **Multi-stage Dockerfile** with three stages: `builder`, `dev` (see ADR-018) and
  `runtime`, which is the default. The builder installs only the dependencies into a
  virtualenv, copying `pyproject.toml` alone so the layer stays cached across code
  changes. The runtime stage is `python:3.12-slim` with that virtualenv and the source.
  The code is owned by root and only readable by the process. It runs as a **non-root**
  user (uid 10001, no shell) with a `HEALTHCHECK` on `/health`, which also pings the
  database.
- **Entrypoint** applies migrations and then `exec`s Uvicorn, so Uvicorn is PID 1 and
  receives signals.
- **Compose** runs PostgreSQL with a healthcheck and a named volume. The API waits for
  `service_healthy`. `make up` uses `--wait`, so it only returns once both services are
  healthy. Ports and credentials come from `.env`, and Compose refuses to start without
  `JWT_SECRET` and `POSTGRES_PASSWORD`. The hardening options are described in ADR-017.
- **Makefile** is the single entry point. `make all` takes a fresh clone to a linted,
  tested, running stack.

## ADR-017: Security hardening

**Context.** The API handles credentials and private data. A security review of the
first version found the following issues, all fixed here:

| Finding | Risk | Fix |
| --- | --- | --- |
| Invitations granted access to any account with the invited email, and emails were not verified | High | Email verification gates membership access (ADR-010) |
| Default JWT secret and database password were published in the repo, and PostgreSQL listened on `0.0.0.0` | High | No default secrets. `make env` generates them, Compose requires them, and the database binds to `127.0.0.1` |
| No throttling on login or registration | High | Rate limiting per client IP |
| Login was fast for unknown emails and slow for known ones | Medium | Dummy hash verification (ADR-009) |
| Assigning an unknown user id and a user without access returned different errors | Medium | Same error for both |
| Names and titles accepted CR/LF, which reach email subjects | Medium | Control characters rejected (email header injection) |
| No request body limit | Medium | 1 MiB limit, returning `413` |
| A token for one purpose could be used for another | Medium | `typ` claim (ADR-008) |
| scrypt used `p=1`, below the OWASP parameters | Low | `p=5` (ADR-009) |
| No security headers, docs exposed everywhere, any JWT algorithm accepted, no container hardening | Low | See the decision below |

**Decision.**

- **Rate limiting.** Each auth endpoint (`/auth/register`, `/auth/token`,
  `/auth/verify-email`, `/auth/verify-email/resend`) allows
  `AUTH_RATE_LIMIT_PER_MINUTE` requests (default 10) per client IP in a sliding window.
  Over the limit, it answers `429` with `Retry-After`. The limiter is in process memory
  with a lock and bounded key growth.
- **Security headers** on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS (two years),
  `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin`, and a
  restrictive `Permissions-Policy`. API responses also get
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` and
  `Cache-Control: no-store`, so tokens and private data are never cached. Swagger UI and
  ReDoc are exempt from the CSP because they load scripts from a CDN.
- **Body size limit.** An ASGI middleware checks `Content-Length` and also counts the
  bytes actually received, so chunked uploads cannot bypass it.
- **Docs in production.** `/docs`, `/redoc` and `/openapi.json` are disabled when
  `APP_ENV=production`. Compose defaults to production. The `.env` generated for
  development enables them.
- **CORS** is deliberately not configured. Browsers therefore block cross-origin calls,
  which is the safe default until a known frontend origin exists.
- **Containers.** The API service runs with `read_only: true` (plus a `tmpfs` for `/tmp`),
  `cap_drop: [ALL]`, `no-new-privileges`, `mem_limit: 512m` and `pids_limit: 200`.
  Uvicorn runs with `--no-server-header`. PostgreSQL gets `no-new-privileges` and is
  published on loopback only.
- **Checks in the pipeline.** ruff's bandit rules (`S`) run on every lint, pip-audit on
  demand, and the security behaviour has its own integration tests
  (`tests/integration/test_security_api.py`).

**Alternatives.** `slowapi` for rate limiting adds a dependency for about 30 lines of
code. A reverse proxy (nginx, Traefik) or an API gateway could handle rate limits, body
size and headers, but this project ships the API alone, so the API protects itself.

**Consequences.** The in-memory limiter counts per worker process and resets on restart.
With several replicas it should move to Redis or to the proxy. The rate limit keys on
the client IP, so behind a proxy Uvicorn's `--forwarded-allow-ips` must list that proxy
for the real IP to be used. Otherwise every client would share one bucket.

## ADR-018: Development container with hot reload

**Context.** During development the API should run in the same container setup as
production and restart by itself when the code changes, without rebuilding the image.

**Decision.** A `dev` stage in the Dockerfile adds the dev dependencies on top of the
builder's virtualenv. `docker-compose.dev.yml` is an override applied by `make dev`, and
it:

- builds the `dev` target and bind-mounts the project at `/app`,
- runs `uvicorn --reload --reload-dir app` (the stage's default command),
- sets `WATCHFILES_FORCE_POLLING=true`, because inotify events do not reliably cross
  bind mounts on Docker Desktop or WSL,
- runs as the host user (`HOST_UID`/`HOST_GID`, exported by the Makefile), so the files
  the container writes stay owned by the developer,
- relaxes `read_only` (the mount must be writable for coverage and caches) and adds a
  healthcheck, so `--wait` only returns once Uvicorn is serving.

`make test-docker` runs the linters and the test suite inside that same image.

**Consequences.** Saving a file under `app/` restarts the API in about two seconds.
Polling costs a little CPU; on native Linux it can be turned off with
`WATCHFILES_FORCE_POLLING=false`. The dev image is never what `make up` runs: the runtime
stage stays minimal.

---

## Future work

Deliberately out of scope for now, in rough priority order:

1. **CI pipeline** (GitHub Actions): `make check`, plus the integration suite against a
   PostgreSQL service container.
2. **Lock file** (`uv lock` or `pip-tools`) for reproducible builds.
3. **Auth hardening**: refresh tokens, token revocation (a `jti` denylist, or a per-user
   token version bumped on password change), a shared rate limit store (Redis), rehashing
   passwords on login when the scrypt parameters are raised, and pinning base images by
   digest.
4. **Membership management**: list and remove members, accept or decline invitations with
   expiring tokens, roles beyond owner and member.
5. **Real email delivery** from a background worker (ADR-011).
6. **Unit of Work** once a use case needs multi-aggregate transactions (ADR-006).
7. **Richer listing**: sorting, text search, due-date ranges, "assigned to me".
8. **Observability**: structured JSON logs with request ids, metrics, readiness separate
   from liveness.
9. **Optimistic concurrency** (a `version` column) to avoid lost updates on concurrent
   edits.
