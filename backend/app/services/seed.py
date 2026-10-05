"""Idempotent baseline seed (reference data only; no demo business data - that lives in database/seeds)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import GENESIS
from app.models.audit import AuditChainHead
from app.models.iam import Permission, Role, RolePermission, SodRule
from app.models.org import Company, Plant
from app.security.permissions import all_permission_codes
from app.services import config_service, numbering

COMMON = ["dashboard.view.read", "notification.own.read"]
ADMIN_PERMS = [
    "iam.user.create", "iam.user.read", "iam.user.update", "iam.user.deactivate", "iam.user.assign_role",
    "iam.user.reset_password", "iam.role.create", "iam.role.read", "iam.role.update", "iam.session.read",
    "iam.session.revoke", "org.company.read", "org.company.update", "org.plant.read", "org.plant.create",
    "org.plant.update", "config.system.read", "config.system.update", "config.numbering.read",
    "config.numbering.update", "workflow.definition.read", "workflow.definition.create",
    "workflow.definition.update", "audit.trail.read", "audit.trail.export", "security.event.read",
    "training.record.read", "training.record.create"]
QA_PERMS = ["audit.trail.read", "audit.trail.export", "audit.trail.verify", "security.event.read",
            "esign.record.read", "iam.user.read", "iam.role.read", "org.company.read", "org.plant.read",
            "training.record.read", "workflow.definition.read", "workflow.definition.approve",
            "workflow.instance.read", "config.system.read", "config.numbering.read"]
AUDITOR_PERMS = ["audit.trail.read", "audit.trail.export", "security.event.read", "esign.record.read",
                 "iam.user.read", "iam.role.read", "org.company.read", "workflow.definition.read",
                 "workflow.instance.read", "config.system.read", "config.numbering.read",
                 "training.record.read"]

def _md(resources: list[str], actions: list[str]) -> list[str]:
    return [f"md.{r}.{a}" for r in resources for a in actions]


MD_ALL = ["unit", "material_type", "category", "vendor", "material", "spec", "stp", "sampling_plan",
          "warehouse", "location", "equipment", "calibration", "customer"]
MD_READ = _md(MD_ALL, ["read"]) + ["md.master.export", "doc.document.read"]
MD_CUD = ["vendor", "material", "spec", "stp", "sampling_plan", "warehouse", "location", "equipment", "customer"]
ADMIN_MD = _md(["unit", "material_type", "category"], ["create", "read", "update"]) + ["md.master.export"]
PURCHASE_MD = (_md(["vendor"], ["create", "read", "update"]) + MD_READ + ["doc.document.create",
               "import.job.create", "import.job.read"])
QC_MD = (_md(["material", "spec", "stp", "sampling_plan", "equipment"], ["create", "read", "update"])
         + ["md.calibration.create"] + MD_READ + ["doc.document.create", "import.job.create", "import.job.read"])
QA_MD = (_md(MD_CUD, ["create", "read", "update"]) + _md(["calibration"], ["create"]) + MD_READ +
         ["md.vendor.review_document", "doc.document.create", "import.job.create", "import.job.read"])
QA_HEAD_MD = QA_MD + _md(["vendor", "material", "spec", "stp", "sampling_plan"], ["approve"]) + \
    ["md.vendor.deactivate", "md.material.deactivate", "import.job.approve"]

PURCHASE_REQ = ["pr.request.create", "pr.request.read", "pr.request.update", "pr.request.submit", "pr.request.cancel"]
PURCHASE_READ = ["vq.qualification.read", "vm.mapping.read", "pr.request.read", "po.order.read", "pr.request.export",
                 "po.order.export"]
PURCHASE_USER_P3 = (PURCHASE_REQ + PURCHASE_READ + ["po.order.create", "po.order.update", "po.order.submit",
                                                    "po.order.cancel", "vm.mapping.create", "vm.mapping.update"])
PURCHASE_MGR_P3 = PURCHASE_USER_P3 + ["po.order.approve", "pr.request.approve"]
QA_P3 = ["vq.qualification.create", "vq.qualification.read", "vq.qualification.update", "vm.mapping.create",
         "vm.mapping.read", "vm.mapping.update", "po.order.read", "pr.request.read"] + PURCHASE_READ
QA_HEAD_P3 = QA_P3 + ["vq.qualification.approve", "vq.qualification.suspend", "vq.qualification.disqualify",
                      "vm.mapping.approve", "vm.mapping.withdraw"]

ROLES: dict[str, tuple[str, bool, list[str]]] = {
    # code: (name, is_admin_role, extra permissions)
    "SYSTEM_ADMIN": ("System Administrator", True, ADMIN_PERMS + ADMIN_MD + ["org.department.read", "org.department.create", "org.department.update", "config.job.run"]),
    "PURCHASE_USER": ("Purchase User", False, PURCHASE_MD + PURCHASE_USER_P3),
    "PURCHASE_MANAGER": ("Purchase Manager", False, PURCHASE_MD + PURCHASE_MGR_P3 + ["md.vendor.approve", "md.vendor.deactivate", "import.job.approve"]),
    "WAREHOUSE_USER": ("Warehouse User", False, MD_READ + _md(["warehouse", "location"], ["create", "update"]) + PURCHASE_REQ),
    "QC_ANALYST": ("QC Analyst", False, QC_MD + PURCHASE_REQ),
    "QC_HEAD": ("QC Head", False, ["workflow.instance.read"] + QC_MD + PURCHASE_REQ),
    "QA_OFFICER": ("QA Officer", False, QA_PERMS + QA_MD + QA_P3 + PURCHASE_REQ),
    "QA_HEAD": ("QA Head", False, QA_PERMS + QA_HEAD_MD + QA_HEAD_P3 + PURCHASE_REQ),
    "PRODUCTION_USER": ("Production User", False, MD_READ + PURCHASE_REQ),
    "PRODUCTION_MANAGER": ("Production Manager", False, ["workflow.instance.read"] + MD_READ + PURCHASE_REQ),
    "DEPARTMENT_HEAD": ("Department Head", False, ["pr.request.read", "pr.request.approve", "pr.request.create", "pr.request.update", "pr.request.submit", "pr.request.cancel"] + MD_READ),
    "DISPATCH_USER": ("Dispatch User", False, MD_READ + _md(["customer"], ["create", "update"])),
    "MANAGEMENT": ("Management", False, ["audit.trail.read"] + MD_READ + PURCHASE_READ),
    "AUDITOR": ("Auditor / Read Only", False, AUDITOR_PERMS + MD_READ + ["import.job.read"] + PURCHASE_READ),
}

# QA Officer may not approve/verify workflow definitions; only QA Head holds approve.
ROLE_EXCLUDE = {"QA_OFFICER": {"workflow.definition.approve", "audit.trail.verify"}}

SOD_RULES = [
    ("SOD-01", "po.order.approve", "po.order.create", "Creator of a PO cannot approve it"),
    ("SOD-01b", "pr.request.approve", "pr.request.create", "Creator of a PR cannot approve it"),
    ("SOD-02", "qc.result.review", "qc.result.enter", "Analyst cannot review their own result"),
    ("SOD-03", "qa.lot.release", "qc.result.review", "QC reviewer cannot also QA-release the lot"),
    ("SOD-04", "deviation.qa.approve", "deviation.raise", "Deviation raiser cannot be sole QA approver"),
    ("SOD-05", "vendor.qualification.approve", "vendor.qualification.author", "Qualification author cannot approve"),
    ("SOD-06", "conditional_release.approve", "conditional_release.request", "Requester cannot approve"),
    ("SOD-08", "qc.amendment.approve", "qc.amendment.request", "Requester cannot approve a result amendment"),
    ("SOD-12", "workflow.definition.approve", "workflow.definition.author", "Workflow author cannot approve"),
    ("SOD-13", "vendor.approve", "vendor.author", "Vendor record author cannot approve it"),
    ("SOD-14", "material.approve", "material.author", "Material record author cannot approve it"),
    ("SOD-15", "spec.approve", "spec.author", "Specification author cannot approve it"),
    ("SOD-16", "stp.approve", "stp.author", "STP author cannot approve it"),
    ("SOD-17", "sampling_plan.approve", "sampling_plan.author", "Sampling plan author cannot approve it"),
    ("SOD-18", "import.approve", "import.submit", "Import submitter cannot approve the import"),
    ("SOD-19", "vendor_document.review", "vendor_document.upload", "Uploader cannot review own vendor document"),
    ("SOD-20", "vendor_material.approve", "vendor_material.author", "Mapping author cannot approve it"),
    ("SOD-21", "vendor_qualification.approve", "vendor_qualification.author", "Qualification author cannot approve it"),
]


def seed_baseline(session: Session, *, company_name: str = "Company Name (configure)",
                  plant_code: str = "P01", plant_name: str = "Main Plant") -> Plant:
    existing = {p.perm_code: p for p in session.execute(select(Permission)).scalars()}
    new_codes: set[str] = set()
    for code, module, resource, action in all_permission_codes():
        if code not in existing:
            p = Permission(perm_code=code, module=module, resource=resource, action=action)
            session.add(p)
            existing[code] = p
            new_codes.add(code)
    session.flush()

    for code, (name, is_admin, extra) in ROLES.items():
        role = session.execute(select(Role).where(Role.role_code == code)).scalar_one_or_none()
        if role is None:
            role = Role(role_code=code, name=name, is_system=True, is_admin_role=is_admin)
            session.add(role)
            session.flush()
            grants = set(COMMON) | set(extra)
            grants -= ROLE_EXCLUDE.get(code, set())
            for g in grants:
                session.add(RolePermission(role_id=role.id, permission_id=existing[g].id))
        elif new_codes:  # upgrade path: grant only the *newly introduced* defaults (never undo admin changes)
            grants = (set(COMMON) | set(extra)) - ROLE_EXCLUDE.get(code, set())
            for g in grants & new_codes:
                session.add(RolePermission(role_id=role.id, permission_id=existing[g].id))

    for sod_id, action, conflict, desc in SOD_RULES:
        if session.execute(select(SodRule.id).where(SodRule.action_code == action,
                                                    SodRule.conflicts_with_action_code == conflict)).first() is None:
            session.add(SodRule(sod_id=sod_id, action_code=action, conflicts_with_action_code=conflict,
                                description=desc))

    company = session.execute(select(Company)).scalars().first()
    if company is None:
        company = Company(name=company_name)
        session.add(company)
        session.flush()
    plant = session.execute(select(Plant).where(Plant.plant_code == plant_code)).scalar_one_or_none()
    if plant is None:
        plant = Plant(company_id=company.id, plant_code=plant_code, name=plant_name)
        session.add(plant)
        session.flush()
    seed_workflows(session)
    numbering.seed_registry(session, plant.id)
    config_service.seed_defaults(session)
    if session.get(AuditChainHead, 1) is None:
        session.add(AuditChainHead(id=1, lock_counter=0, last_hash=GENESIS, row_count=0))
    return plant


BASELINE_WORKFLOWS = {
    "pr.request": ("Purchase request approval", [
        {"seq": 1, "name": "Department approval", "role_code": "DEPARTMENT_HEAD", "esig_required": False, "meaning": "REVIEWED_BY", "sla_hours": 48},
        {"seq": 2, "name": "Purchase review", "role_code": "PURCHASE_MANAGER", "esig_required": True, "meaning": "APPROVED_BY", "sla_hours": 48}]),
    "po.order": ("Purchase order approval", [
        {"seq": 1, "name": "Purchase Manager approval", "role_code": "PURCHASE_MANAGER", "esig_required": True, "meaning": "APPROVED_BY", "sla_hours": 24}]),
}


def seed_workflows(session: Session) -> None:
    """Baseline approval chains installed as configuration (approved without signature as part of the release;
    later changes require QA e-signature through the normal workflow-definition approval)."""
    from app.models.platform import WorkflowDefinition
    from app.core.time import utcnow
    from app.workflows import approval
    from app.workflows.state_machine import transition_context
    for code, (name, steps) in BASELINE_WORKFLOWS.items():
        if session.execute(select(WorkflowDefinition.id).where(WorkflowDefinition.process_code == code)).first():
            continue
        session.flush()
        d = approval.create_definition(session, code, name, steps)
        session.flush()
        with transition_context():
            d.status = "APPROVED"
            d.effective_from = utcnow()
            session.flush()
