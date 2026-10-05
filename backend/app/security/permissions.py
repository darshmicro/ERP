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
