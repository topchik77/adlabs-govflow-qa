$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose exec -T app python -m pytest --tb=short --junitxml=/tmp/pytest.xml
$testResult = $LASTEXITCODE
New-Item -ItemType Directory -Force reports | Out-Null
docker compose cp app:/tmp/pytest.xml reports/pytest.xml
if ($testResult -ne 0) { throw 'GovFlow regression failed. See reports/pytest.xml' }
docker compose exec -T app ruff check services scripts tests
if ($LASTEXITCODE -ne 0) { throw 'Ruff check failed' }
Write-Host 'PostgreSQL regression passed; reports/pytest.xml saved.'
