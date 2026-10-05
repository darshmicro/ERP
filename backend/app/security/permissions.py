"""Permission catalogue (single source of truth) and effective-permission resolution."""
from datetime import date

from sqlalchemy import false as sa_false, true as sa_true
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.iam import Permission, Role, RolePermission, UserRole

# module -> resource -> actions.  perm_code = module.resource.action
CATALOGUE: dict[str, dict[str, list[str]]] = {
    "iam": {"user": ["create", "read", "update", "deactivate", "assign_role", "reset_password"],
            "role": ["create", "read", "update"],
            "session": ["read", "revoke"]},
    "org": {"company": ["read", "update"], "plant": ["read", "create", "update"]},
    "audit": {"trail": ["read", "export", "verify"]},
    "security": {"event": ["read"]},
    "config": {"system": ["read", "update"], "numbering": ["read", "update"]},
    "workflow": {"definition": ["read", "create", "update", "approve"], "instance": ["read"]},
    "esign": {"record": ["read"]},
    "training": {"record": ["read", "create"]},
    "dashboard": {"view": ["read"]},
    "notification": {"own": ["read"]},
    # --- Phase 2: master data ---
    "md": {
        "unit": ["create", "read", "update"], "material_type": ["create", "read", "update"],
        "category": ["create", "read", "update"],
        "vendor": ["create", "read", "update", "approve", "deactivate", "review_document"],
        "material": ["create", "read", "update", "approve", "deactivate"],
        "spec": ["create", "read", "update", "approve"], "stp": ["create", "read", "update", "approve"],
        "sampling_plan": ["create", "read", "update", "approve"],
        "warehouse": ["create", "read", "update"], "location": ["create", "read", "update"],
        "equipment": ["create", "read", "update"], "calibration": ["create", "read"],
        "customer": ["create", "read", "update"], "master": ["export"],
    },
    "doc": {"document": ["create", "read"]},
    "import": {"job": ["create", "read", "approve"]},
    # --- Phase 3: purchase ---
    "vq": {"qualification": ["create", "read", "update", "approve", "suspend", "disqualify"]},
    "vm": {"mapping": ["create", "read", "update", "approve", "withdraw"]},
    "pr": {"request": ["create", "read", "update", "submit", "approve", "cancel", "export"]},
    "po": {"order": ["create", "read", "update", "submit", "approve", "cancel", "export"]},
}
CATALOGUE["grn"] = {"receipt": ["create", "read", "update", "submit", "verify", "reject", "cancel", "exception", "export"]}
CATALOGUE["inventory"] = {"stock": ["read", "transfer", "export"], "lot": ["read"], "ledger": ["read", "verify"]}
CATALOGUE["qa"] = {"hold": ["place", "read", "release"], "lot": ["reject"]}
CATALOGUE["label"] = {"lot": ["print"], "location": ["print"]}
CATALOGUE["warehouse"] = {"temperature": ["create", "read"], "destruction": ["create", "read", "approve"], "checklist": ["read", "update"]}
CATALOGUE["qc"] = {"sample": ["create", "read", "dispose"], "test": ["assign", "read", "start", "enter", "override_calibration"],
                   "result": ["amend_request", "amend_approve"], "release": ["submit", "approve"]}
CATALOGUE["oos"] = {"investigation": ["create", "read", "update", "decide"]}
CATALOGUE["oot"] = {"event": ["read", "review"]}
CATALOGUE["coa"] = {"document": ["read", "generate"]}
CATALOGUE["stats"] = {"trend": ["read"]}
CATALOGUE["conditional_release"] = {"request": ["create", "read", "approve"]}
CATALOGUE["md"]["bom"] = ["create", "read", "update", "approve"]
CATALOGUE["mfg"] = {"batch": ["create", "read", "update", "override_number", "cancel", "release_check"], "issue": ["create", "read", "additional"],
                    "return": ["request", "accept", "read"], "step": ["execute", "verify"], "ipc": ["create", "read"], "consumption": ["record"],
                    "equipment": ["use"], "reconciliation": ["read", "approve", "qa_approve"], "output": ["create"]}
CATALOGUE["antisera"] = {"animal": ["create", "read", "update"], "bleed": ["create", "read"], "pool": ["create", "read"]}
CATALOGUE["dispatch"] = {"order": ["create", "read", "update", "validate", "approve", "dispatch", "deliver", "cancel", "export"]}
CATALOGUE["trace"] = {"record": ["read"]}
CATALOGUE["quality"] = {"deviation": ["create", "read", "update", "investigate", "close", "cancel"], "capa": ["create", "read", "update", "close"],
                        "cc": ["create", "read", "update", "assess", "approve", "close"], "risk": ["create", "read", "update", "approve"],
                        "sop": ["create", "read", "update", "approve", "acknowledge"], "complaint": ["create", "read", "update", "close"],
                        "recall": ["create", "read", "update", "close"]}
CATALOGUE["reports"] = {"catalog": ["read"], "export": ["run"], "run": ["read"]}
CATALOGUE["dashboard"].update({"management": ["read"], "qc": ["read"], "qa": ["read"], "warehouse": ["read"]})
CATALOGUE["retention"] = {"policy": ["read", "update"], "archive": ["create", "read"]}
CATALOGUE["backup"] = {"status": ["read", "record"]}
CATALOGUE["org"]["department"] = ["read", "create", "update"]
CATALOGUE["config"]["job"] = ["run"]

# Actions that confer GMP approval authority (used by SoD-09: admin roles must not hold them)
GMP_AUTHORITY_ACTIONS = {"approve", "release", "reject", "sign"}


def all_permission_codes() -> list[tuple[str, str, str, str]]:
    out = []
    for module, resources in CATALOGUE.items():
        for resource, actions in resources.items():
            for action in actions:
                out.append((f"{module}.{resource}.{action}", module, resource, action))
    return out


def effective_permissions(session: Session, user_id: int, today: date | None = None) -> set[str]:
    today = today or date.today()
    q = (select(Permission.perm_code)
         .join(RolePermission, RolePermission.permission_id == Permission.id)
         .join(Role, Role.id == RolePermission.role_id)
         .join(UserRole, UserRole.role_id == Role.id)
         .where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None),
                UserRole.is_disabled == sa_false(), UserRole.valid_from <= today,
                (UserRole.valid_to.is_(None)) | (UserRole.valid_to >= today),
                RolePermission.revoked_at.is_(None), Role.is_active == sa_true()))
    return set(session.execute(q).scalars().all())


def active_role_codes(session: Session, user_id: int, today: date | None = None) -> list[str]:
    today = today or date.today()
    q = (select(Role.role_code).join(UserRole, UserRole.role_id == Role.id)
         .where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None),
                UserRole.is_disabled == sa_false(), UserRole.valid_from <= today,
                (UserRole.valid_to.is_(None)) | (UserRole.valid_to >= today), Role.is_active == sa_true())
         .order_by(Role.role_code))
    return list(session.execute(q).scalars().all())
