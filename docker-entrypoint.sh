#!/bin/sh
# Apply pending migrations, then hand PID 1 over to the server.
set -e
alembic upgrade head
exec "$@"
