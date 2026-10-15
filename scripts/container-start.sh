#!/bin/sh
set -eu
python -m alembic -c services/core-api/alembic.ini upgrade head
python -m govflow.seed
exec python -m uvicorn govflow.main:app --host 0.0.0.0 --port 8014
