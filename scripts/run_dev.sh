#!/usr/bin/env bash
# Development convenience: migrate + run API with reload. Requires .env (copy .env.example).
set -euo pipefail
cd "$(dirname "$0")/../backend"
export PYTHONPATH=.
alembic upgrade head
exec uvicorn app.main:create_app --factory --reload --port 8000
