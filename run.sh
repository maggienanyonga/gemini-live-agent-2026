#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/backend"
exec uvicorn main:app --host 127.0.0.1 --port 8080 --reload
