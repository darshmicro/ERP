from fastapi import APIRouter

from app.api.v1 import audit, auth, org, system, users, workflows

api_router = APIRouter(prefix="/api/v1")
for r in (auth.router, users.router, audit.router, org.router, workflows.router, system.router):
    api_router.include_router(r)
