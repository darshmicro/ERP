"""Electronic signatures (spec 6, Doc 01 §3.2). Fresh re-authentication at every signing."""
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import get_context
from app.core.errors import AuthenticationError, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models.audit import ESignature
from app.models.iam import TrainingRecord, User
from app.security.permissions import active_role_codes, effective_permissions
from app.security.providers import provider_for
from app.services import config_service
from app.services.auth_service import register_failed_attempt

MEANINGS = {"CREATED_BY", "REVIEWED_BY", "APPROVED_BY", "REJECTED_BY", "RELEASED_BY", "SAMPLED_BY",
            "TESTED_BY", "VERIFIED_BY", "QA_APPROVED", "QA_RELEASED"}
REASON_REQUIRED_MEANINGS = {"REJECTED_BY"}


def canonical_hash(snapshot: Any) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def sign(session: Session, user: User, password: str, *, meaning: str, entity: str, record_id: Any,
         record_snapshot: Any, record_version: Any = None, reason: str | None = None,
         required_permission: str | None = None, training_code: str | None = None) -> ESignature:
    if meaning not in MEANINGS:
        raise ValidationFailed(f"Unknown signature meaning '{meaning}'")
    if meaning in REASON_REQUIRED_MEANINGS and not (reason or "").strip():
        raise ValidationFailed("A reason is required for this signature meaning", code="REASON_REQUIRED")
    if not password:
        raise AuthenticationError("Password is required to sign.")
    ctx = get_context()
    if not user.is_active:
        raise AuthenticationError("Account is not active.")
    if not provider_for(user).verify(user, password):
        register_failed_attempt(user.id, ctx.ip_address, "bad credentials on e-signature")
        raise AuthenticationError("Signature authentication failed.")
    perms = effective_permissions(session, user.id)
    if required_permission and required_permission not in perms:
        raise PermissionDenied(f"You are not authorised to sign this action ({required_permission}).")
    if config_service.get_bool(session, "training.gate", False) and training_code:
        from datetime import date
        ok = session.execute(select(TrainingRecord.id).where(
            TrainingRecord.user_id == user.id, TrainingRecord.training_code == training_code,
            (TrainingRecord.valid_until.is_(None)) | (TrainingRecord.valid_until >= date.today())
        ).limit(1)).first()
        if not ok:
            raise PermissionDenied(f"Valid training on {training_code} is required before signing.",
                                   rule_id="G-04")
    now = utcnow()
    rec_hash = canonical_hash(record_snapshot)
    roles = ", ".join(active_role_codes(session, user.id))
    manifest = canonical_hash({"u": user.id, "name": user.full_name, "m": meaning, "e": entity,
                               "r": str(record_id), "v": str(record_version), "h": rec_hash,
                               "t": now.isoformat()})
    sig = ESignature(user_id=user.id, signed_at=now, tz_name="UTC", printed_name=user.full_name,
                     username=user.username, role_name=roles, meaning=meaning, reason=reason,
                     entity=entity, record_id=str(record_id),
                     record_version=None if record_version is None else str(record_version),
                     record_hash=rec_hash, auth_method=user.auth_source, ip_address=ctx.ip_address,
                     manifest_hash=manifest)
    session.add(sig)
    session.flush()
    audit.log_event(session, module="esign", entity=entity, record_id=record_id, action="E_SIGNATURE",
                    field_name=meaning, new=manifest, reason=reason, signature_id=sig.id)
    return sig
