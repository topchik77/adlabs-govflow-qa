#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$task_root"
docker run --rm --mount "type=bind,source=$task_root,target=/workspace" -w /workspace python:3.12-alpine python scripts/configure.py
docker compose up --build -d --wait
printf '%s\n' 'GovFlow: http://127.0.0.1:8014 | Swagger: http://127.0.0.1:8014/docs'
printf '%s\n' 'Login: applicant.a; password is DEMO_PASSWORD in .env'
