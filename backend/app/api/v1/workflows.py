from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.api.helpers import use_reason
from app.core.errors import NotFound
from app.models.iam import Role
from app.models.platform import WorkflowDefinition, WorkflowStep
from app.schemas.platform import SignIn, WorkflowCreateIn
from app.workflows import approval

router = APIRouter(prefix="/workflows", tags=["workflow"])


def _out(s: Session, d: WorkflowDefinition) -> dict:
    steps = s.execute(select(WorkflowStep, Role.role_code).join(Role, Role.id == WorkflowStep.role_id)
                      .where(WorkflowStep.definition_id == d.id).order_by(WorkflowStep.seq)).all()
    return {"id": d.id, "process_code": d.process_code, "version_no": d.version_no, "name": d.name,
            "status": d.status, "effective_from": d.effective_from.isoformat() if d.effective_from else None,
            "steps": [{"seq": st.seq, "name": st.name, "role_code": rc, "min_approvals": st.min_approvals,
                       "esig_required": st.esig_required, "meaning": st.meaning, "sla_hours": st.sla_hours,
                       "reject_to_seq": st.reject_to_seq} for st, rc in steps]}


@router.get("/definitions")
def list_definitions(p: Principal = Depends(require("workflow.definition.read")), s: Session = Depends(get_db)):
    return [_out(s, d) for d in s.execute(select(WorkflowDefinition).order_by(
        WorkflowDefinition.process_code, WorkflowDefinition.version_no.desc())).scalars()]


@router.post("/definitions", status_code=201)
def create_definition(body: WorkflowCreateIn, p: Principal = Depends(require("workflow.definition.create")),
                      s: Session = Depends(get_db)):
    use_reason(body.reason)
    d = approval.create_definition(s, body.process_code, body.name, [x.model_dump() for x in body.steps])
    from app.services import sod
    sod.record_action(s, "workflow_definition", d.id, "workflow.definition.author", p.user.id)
    s.commit()
    return _out(s, d)


@router.post("/definitions/{definition_id}/approve")
def approve_definition(definition_id: int, body: SignIn, p: Principal = Depends(require("workflow.definition.approve")),
                       s: Session = Depends(get_db)):
    use_reason(body.reason)
    d = s.get(WorkflowDefinition, definition_id)
    if d is None:
        raise NotFound("Workflow definition not found")
    approval.approve_definition(s, d, p.user, body.password, body.reason or "", p.perms)
    s.commit()
    return _out(s, d)
