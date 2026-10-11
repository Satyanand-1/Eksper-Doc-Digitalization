#!/bin/sh
set -e

echo "Applying Alembic database migrations..."
alembic upgrade head || true

echo "Seeding default data..."
python -m app.seed || true

echo "Starting Uvicorn on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
