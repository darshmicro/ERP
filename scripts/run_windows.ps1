# Windows dev/pilot run (production: install as a service with NSSM/WinSW behind IIS-ARR or Caddy).
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\backend"
$env:PYTHONPATH = "."
alembic upgrade head
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 4
