#!/bin/bash
cd "$(dirname "$0")"

echo "Starting Huey queue worker..."
uv run huey_consumer main.huey &
HUEY_PID=$!

trap "kill $HUEY_PID" EXIT

echo "Starting Uvicorn server..."
exec uv run uvicorn main:app --host 127.0.0.1 --port 8910 "$@"
