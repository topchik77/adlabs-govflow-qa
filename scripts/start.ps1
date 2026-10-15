$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" -w /workspace python:3.12-alpine python scripts/configure.py
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
docker compose up --build -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Inspect docker compose logs' }
Write-Host 'GovFlow: http://127.0.0.1:8014 | Swagger: http://127.0.0.1:8014/docs'
Write-Host 'Login: applicant.a; password is DEMO_PASSWORD in .env'
