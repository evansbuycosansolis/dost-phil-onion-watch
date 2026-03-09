#!/bin/sh
set -eu

cd /workspace/apps/api

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  if python - <<'PY'
import os
import sys

from sqlalchemy import create_engine, inspect

engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    exists = "alembic_version" in inspect(conn).get_table_names()
sys.exit(0 if exists else 1)
PY
  then
    echo "[entrypoint] running alembic upgrade head"
    alembic upgrade head
  else
    echo "[entrypoint] bootstrapping schema and stamping alembic head"
    python - <<'PY'
from app import models  # noqa: F401
from app.core.database import Base, engine

Base.metadata.create_all(bind=engine)
PY
    alembic stamp head
  fi
fi

if [ "${WAIT_FOR_JOB_RUNS_TABLE:-false}" = "true" ]; then
  echo "[entrypoint] waiting for job_runs table availability"
  python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, inspect, text

database_url = os.environ["DATABASE_URL"]
timeout_seconds = int(os.environ.get("JOB_RUNS_WAIT_TIMEOUT_SECONDS", "180"))
sleep_seconds = 2
deadline = time.time() + timeout_seconds
last_error: Exception | None = None

while time.time() < deadline:
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if "job_runs" in inspect(conn).get_table_names():
                print("[entrypoint] job_runs table found")
                sys.exit(0)
    except Exception as exc:  # pragma: no cover - startup guard
        last_error = exc
    time.sleep(sleep_seconds)

message = f"[entrypoint] timed out waiting for job_runs table after {timeout_seconds}s"
if last_error is not None:
    message = f"{message}: {last_error}"
print(message, file=sys.stderr)
sys.exit(1)
PY
fi

exec "$@"
