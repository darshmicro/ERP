from fastapi import APIRouter

from app.api.v1 import audit, auth, imports_docs, masters, org, purchase, qc, quality_masters, manufacturing, dispatch, quality, reports, em, stability, costing, warehouse, system, users, workflows

api_router = APIRouter(prefix="/api/v1")
for r in (auth.router, users.router, audit.router, org.router, workflows.router, system.router,
          masters.router, quality_masters.router, imports_docs.router, purchase.router, warehouse.router, qc.router, manufacturing.router, dispatch.router, quality.router, reports.router, em.router, stability.router, costing.router):
    api_router.include_router(r)
