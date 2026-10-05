from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform import SystemConfiguration

DEFAULTS = {
    "training.gate": ("false", "Require valid training record before e-signing"),
    "calibration.override_allowed": ("false", "Allow QA-signed override of expired calibration"),
    "po.over_delivery_tolerance_pct": ("0", "GRN over-delivery tolerance %"),
    "stats.min_n_capability": ("25", "Minimum n for Cp/Cpk/Pp/Ppk"),
    "expiry.alert_days": ("90,60,30", "Expiry/retest alert thresholds (days)"),
    "label.max_copies": ("10", "Maximum copies per label print"),
    "grn.over_delivery_tolerance_pct": ("0", "Allowed over-delivery % on GRN"),
    "loc.capacity_block": ("true", "Block put-away that exceeds location capacity"),
    "vq.alert_days": ("90,60,30,7", "Vendor requalification due-date alert thresholds (days)"),
    "vq.default_validity_months": ("36", "Default requalification interval (months) suggested on a new qualification"),
    "po.warn_vendor_due_days": ("60", "Warn on PO when vendor requalification is due within this many days"),
    "po.required_docs.CRITICAL": ("GMP_CERTIFICATE,MANUFACTURING_LICENCE,QUALITY_AGREEMENT,COA_SAMPLE", "Vendor documents that must be approved and unexpired (critical vendors)"),
    "po.required_docs.HIGH": ("GMP_CERTIFICATE,MANUFACTURING_LICENCE", "Required vendor documents (high risk)"),
    "po.required_docs.MEDIUM": ("MANUFACTURING_LICENCE", "Required vendor documents (medium risk)"),
    "recon.tolerance_pct": ("0.5", "Batch reconciliation tolerance % (unaccounted / issued)"),
    "po.required_docs.LOW": ("", "Required vendor documents (low risk)"),
}


def get(session: Session, key: str, default: str | None = None) -> str | None:
    row = session.execute(select(SystemConfiguration.value).where(SystemConfiguration.config_key == key)
                          ).scalar_one_or_none()
    if row is not None:
        return row
    return DEFAULTS.get(key, (default, ""))[0] if default is None else default


def get_bool(session: Session, key: str, default: bool = False) -> bool:
    v = get(session, key, "true" if default else "false")
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def seed_defaults(session: Session) -> None:
    for k, (v, d) in DEFAULTS.items():
        if session.execute(select(SystemConfiguration.id).where(SystemConfiguration.config_key == k)).first() is None:
            session.add(SystemConfiguration(config_key=k, value=v, description=d))
