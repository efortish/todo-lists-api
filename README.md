# Todo Lists API

A REST API to manage **task lists** and the **tasks** inside them, built with FastAPI,
SQLAlchemy 2, PostgreSQL and a layered (Domain / Application / Infrastructure / API)
architecture.

The technical decisions and their trade-offs are recorded in [DECISION_LOG.md](DECISION_LOG.md).

> [!IMPORTANT]
> **Use the Makefile to build and run the containers.** It is the recommended and
> clearest way to work with this project. Every target generates the `.env` file with
> random secrets when it is missing, combines the right Compose files, waits until the
> services are healthy and prints the URLs to open. Running `docker compose` by hand also
> works (see [Without Make](#without-make)), but then those steps are up to you.

## Features

**Task management**

- CRUD for task lists.
- CRUD for tasks inside a list.
- Dedicated endpoint to change the status of a task (`pending`, `in_progress`, `done`).
- Listing of a list's tasks filtered by status and/or priority, paginated, with a
  `completion_percentage` field that reports the progress of the whole list.

**Collaboration and security**

- **JWT authentication.** Every endpoint except register, login, email verification and
  health is protected. The Swagger **Authorize** button works out of the box.
- **Task assignment.** Each task can have a responsible user, who must be the owner or a
  verified invited member of the list.
- **Simulated email notifications.** Email verification, invitations to a list and task
  assignments "send" an email that is written to the application log.

**Business rules**

- List names are unique per owner.
- Due dates cannot be in the past.
- A task in `done` cannot be edited until it is reopened through the status endpoint.
- Only the owner can delete a list or invite people. Members can manage the tasks.
- Invitations are by email and only grant access once the invitee **verifies** that
  address.
- Lists you cannot access answer `404`, so their existence is never revealed.

## Quick start

Requirements: Docker with Compose v2, GNU Make and Python 3.12+ (the last one only for
local development and tests).

```bash
make all
```

That single command:

1. creates `.env` from `.env.example` with **freshly generated random secrets**
   (database password and JWT key, file mode `600`),
2. creates `.venv` and installs the app and dev dependencies,
3. runs flake8, ruff, black and isort checks and the full test suite with coverage,
4. builds the image and starts PostgreSQL and the API, waiting until both are healthy
   (migrations are applied automatically on start).

Then open **http://localhost:8000/docs**.

> If port 8000 or 5432 is already taken on your machine, set `API_PORT` / `POSTGRES_PORT`
> in `.env` before running `make`.

### Development mode with hot reload

```bash
make dev         # API in Docker, source mounted, restarts on every change under app/
make dev-logs    # watch the reloads (and the simulated emails)
make test-docker # lint + tests inside the dev container
```

`make dev` layers `docker-compose.dev.yml` on top of the main Compose file. It builds the
`dev` stage of the Dockerfile (runtime and dev dependencies), bind-mounts the project into
the container and runs Uvicorn with `--reload`. Save any file under `app/` and the API
restarts within a couple of seconds, without rebuilding the image. The container runs
with your user id, so the files it writes (coverage, caches) stay yours.

### All Make targets

Run `make` (or `make help`) to list them.

| Target | What it does |
| --- | --- |
| `make all` | From a fresh clone to a linted, tested, running stack |
| `make up` / `make down` | Start (production-like image) / stop the stack. Data is kept |
| `make dev` / `make dev-logs` | Start the stack with hot reload / follow its logs |
| `make test-docker` | Lint and tests inside the dev container |
| `make seed` | Load demo users, lists and tasks into the running stack (safe to repeat) |
| `make logs` | Follow the API logs (the simulated emails appear here) |
| `make test` | Unit + integration tests with coverage on the host (fails under 75%) |
| `make e2e` | Hit every endpoint of the running stack over real HTTP and PostgreSQL |
| `make lint` / `make format` | Check / apply flake8, ruff, black and isort |
| `make audit` | Scan dependencies for known vulnerabilities (pip-audit) |
| `make run` | Run the API on the host with auto-reload against the dockerised database |
| `make migrate`, `make psql`, `make shell` | Migrations, database shell and API container shell |
| `make env` | Generate `.env` with random secrets (never overwrites an existing one) |
| `make nuke` | Remove containers, the database volume and the virtualenv |

### Without Make

Supported, but you have to prepare `.env` yourself with real secrets:

```bash
cp .env.example .env    # then replace every "generate" with a random value
docker compose up -d --build --wait                                            # production-like
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build --wait  # hot reload
```

Compose refuses to start if `JWT_SECRET` or `POSTGRES_PASSWORD` are missing.

## Trying the API

### With demo data

```bash
make seed
```

This creates three accounts, all with the password `Password123!` (override it with
`make seed SEED_PASSWORD=...`):

| Account | Status | What it has |
| --- | --- | --- |
| `ana@example.com` | verified | Owns **Sprint 1** (6 tasks, 33.33% done, shared with Bob) and **Home** |
| `bob@example.com` | verified | Member of **Sprint 1** with tasks assigned to him, owns **Reading list** |
| `carla@example.com` | unverified | Invited to **Sprint 1**, but cannot see it until she verifies her email |

The seed prints a verification token for Carla, so you can try the verification flow.
It goes through the same use cases as the API, it does nothing when the data already
exists, and it refuses to run with `APP_ENV=production`.

In `/docs`, click **Authorize** and log in with one of those emails.

### From scratch

Open `/docs` and follow these steps:

1. `POST /api/v1/auth/register` to create an account.
2. Click **Authorize** and log in with your email and password.
3. Create a task list, add tasks, filter them and check `completion_percentage`.
4. To see lists that others share with you, verify your email. The token is in the
   simulated email printed by `make logs` (or `make dev-logs`); send it to
   `POST /api/v1/auth/verify-email`.

The same flow with curl:

```bash
API=http://localhost:8000/api/v1
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"email": "ana@example.com", "full_name": "Ana", "password": "supersecret1"}'
TOKEN=$(curl -s -X POST $API/auth/token -d 'username=ana@example.com&password=supersecret1' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

curl -s -X POST $API/task-lists -H "$AUTH" -H 'Content-Type: application/json' -d '{"name": "Sprint 1"}'
curl -s -X POST $API/task-lists/1/tasks -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"title": "Write the README", "priority": "high"}'
curl -s -X PATCH $API/task-lists/1/tasks/1/status -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"status": "done"}'
curl -s "$API/task-lists/1/tasks?priority=high" -H "$AUTH"
```

## API overview

All endpoints are under `/api/v1`. Interactive documentation lives at `/docs` (Swagger UI)
and `/redoc`, and is disabled when `APP_ENV=production`.

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/auth/register` | Create an account (sends a verification email) |
| `POST` | `/auth/verify-email` | Verify the email with the received token |
| `POST` | `/auth/verify-email/resend` | Send a new verification token |
| `POST` | `/auth/token` | Log in (OAuth2 password form, email as `username`) |
| `GET` | `/auth/me` | Current user |
| `POST` | `/task-lists` | Create a list |
| `GET` | `/task-lists` | Lists you own or were invited to |
| `GET` / `PATCH` / `DELETE` | `/task-lists/{id}` | Get / partially update / delete a list |
| `POST` | `/task-lists/{id}/invitations` | Invite an email to the list (simulated email) |
| `POST` | `/task-lists/{id}/tasks` | Create a task |
| `GET` | `/task-lists/{id}/tasks?status=&priority=&limit=&offset=` | Filtered page plus `completion_percentage` |
| `GET` / `PATCH` / `DELETE` | `/task-lists/{id}/tasks/{task_id}` | Get / partially update / delete a task |
| `PATCH` | `/task-lists/{id}/tasks/{task_id}/status` | Change the status |
| `PUT` | `/task-lists/{id}/tasks/{task_id}/assignee` | Assign or unassign (`null`) |
| `GET` | `/health` | Liveness and database check |

Business errors share one shape, with a stable `code`:

```json
{ "code": "task_completed", "message": "Task 1 is done and cannot be edited. Change its status to reopen it first." }
```

## Security

Security measures in place (the reasoning is in ADR-017 of the decision log):

- **Secrets.** There are no default secrets in the code or in Compose. `make env`
  generates them, and the app and Compose refuse to start without them.
- **Passwords.** Salted scrypt that meets OWASP parameters, compared in constant time.
  Login spends the same time whether the email exists or not.
- **Tokens.** HS256 JWTs with required `exp`, `iat`, `iss` and a `typ` claim that binds
  each token to one purpose (access or email verification). `alg=none` and other
  algorithms are rejected.
- **Account takeover of invitations.** Access granted by invitation requires a verified
  email.
- **Brute force and enumeration.**
  - Auth endpoints are rate limited per client IP and answer `429` with `Retry-After`.
  - Login does not reveal which emails exist.
  - Assignment does not reveal which user ids exist.
  - Foreign lists answer `404`.
- **Input.**
  - Strict Pydantic validation with unknown fields rejected.
  - Control characters are rejected in names and titles, which prevents email header
    injection.
  - Request bodies are limited to 1 MiB (`413`).
  - SQL goes through the ORM with bound parameters only.
- **HTTP.** Every response carries `nosniff`, `X-Frame-Options: DENY`, a CSP of
  `default-src 'none'`, `Cache-Control: no-store`, HSTS and `Referrer-Policy`. The
  `Server` header is removed, and Swagger and OpenAPI are hidden in production.
- **Containers.** The API runs as a non-root user on a read-only filesystem, with all
  Linux capabilities dropped, `no-new-privileges`, and memory and PID limits. PostgreSQL
  is published on `127.0.0.1` only.
- **Supply chain.** `make audit` runs pip-audit, and ruff runs the bandit (`S`) rules on
  every lint.

## Local development without Docker for the API

```bash
make install     # python3 -m venv .venv && pip install -e ".[dev]"
make run         # starts only PostgreSQL in Docker, migrates, runs uvicorn --reload
```

To skip Docker entirely, point `DATABASE_URL` to SQLite (with `.env` generated by
`make env` for the secret):

```bash
source .venv/bin/activate
DATABASE_URL=sqlite:///./todo.db alembic upgrade head
DATABASE_URL=sqlite:///./todo.db uvicorn app.main:create_app --factory --reload
```

### Configuration

All settings are environment variables (a `.env` file is read automatically).

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `development` (`production` in Compose if unset) | `production` disables `/docs`, `/redoc` and `/openapi.json` |
| `DATABASE_URL` | `sqlite:///./todo.db` | SQLAlchemy URL. Compose builds the PostgreSQL one |
| `JWT_SECRET` | **required** | HMAC key for tokens, at least 32 characters |
| `JWT_ALGORITHM` | `HS256` | `HS256`, `HS384` or `HS512` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime (maximum 1440) |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | Requests per minute and IP on each auth endpoint |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Larger request bodies get `413` |
| `LOG_LEVEL` | `INFO` | Python log level |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `todo` / **required** / `todo` | Database credentials used by Compose |
| `API_PORT` / `POSTGRES_PORT` | `8000` / `5432` | Host ports published by Compose |
| `WATCHFILES_FORCE_POLLING` | `true` | Dev mode only. Polling makes hot reload work on every Docker host |

## Tests

```bash
make test          # on the host
make test-docker   # inside the dev container
make e2e           # against the running stack (after make dev or make up)
```

- `tests/unit`: domain rules, security helpers, the rate limiter and every use case run
  against in-memory fakes of the repository ports (no database, no HTTP).
- `tests/integration`: the real FastAPI app over HTTP with SQLAlchemy on an in-memory
  SQLite database, including the security behaviour (verification, rate limiting, headers,
  body limit, hidden docs) and a test that applies the Alembic migrations and checks they
  match the ORM models exactly.
- `tests/e2e`: every endpoint over real HTTP against the running Docker stack and
  PostgreSQL. Each run registers users with unique emails, so it can run repeatedly and
  next to the seed data. It is only collected when `E2E_BASE_URL` is set, which
  `make e2e` does.

Coverage is enforced in `pytest.ini` (`--cov-fail-under=75`); the current suite is at about
98%. Run a single layer with `pytest -m unit` or `pytest -m integration`, and get an HTML
report with `make coverage-html`.

## Project structure

```text
app/
├── domain/              # Pure Python: entities, business rules, exceptions, ports
│   ├── entities.py
│   ├── exceptions.py
│   └── ports.py         # Repository / security / notifier interfaces (typing.Protocol)
├── application/         # Use cases and the Pydantic DTOs at the boundary
│   ├── schemas.py
│   └── use_cases/       # auth.py, task_lists.py, tasks.py
├── infrastructure/      # Adapters: SQLAlchemy, JWT + scrypt, rate limiter, log-based email
│   ├── db/              # models.py, repositories.py, session.py
│   ├── rate_limit.py
│   ├── security.py
│   └── notifications.py
├── api/                 # FastAPI: routers, dependency wiring, errors, security middleware
├── config.py            # pydantic-settings
└── main.py              # Application factory
alembic/                 # Migrations
tests/                   # unit/, integration/, in-memory fakes
Dockerfile               # builder → dev (hot reload) → runtime (default)
docker-compose.yml       # Production-like stack
docker-compose.dev.yml   # Hot reload override used by `make dev`
```

Dependencies point inwards only: `api → application → domain ← infrastructure`.
[AGENTS.md](AGENTS.md) explains how to develop in this repository.
