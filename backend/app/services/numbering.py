"""Configurable, duplicate-free document numbering (spec 61).

Allocation uses an atomic `UPDATE ... SET current_value = current_value + 1` inside the business
transaction, then reads the value back: the row lock taken by UPDATE serialises concurrent writers
on SQL Server, PostgreSQL and SQLite, and the number is released with the transaction (rolled back
transactions do not burn numbers; committed numbers are never reissued).
"""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.time import utcnow
from app.models.platform import NumberRegistry, NumberSequence

MASTER_FORMAT = "{prefix}-{seq:05d}"
# doc types numbered without yearly reset (masters): doc_type -> prefix
MASTER_REGISTRY = {"VENDOR": "VEN", "MATERIAL": "MAT", "CUSTOMER": "CUS", "SPEC": "SPEC", "STP": "STP",
                   "SPLAN": "SPL", "EQUIPMENT": "EQ", "IMPORT": "IMP", "VQUAL": "VQ", "BOM": "BOM", "ANIMAL": "ANM", "BLEED": "BLD",
                   "POOL": "POOL", "SOP": "SOP"}

DEFAULT_REGISTRY = {  # doc_type -> prefix (yearly reset)
    "PR": "PR", "PO": "PO", "GRN": "GRN", "SAMPLE": "SMP", "SFG": "SFG", "FG": "FG",
    "DISPATCH": "DSP", "DEVIATION": "DEV", "CAPA": "CAPA", "CC": "CC", "QCNO": "QC", "QARELEASE": "QAR",
    "INDENT": "IND", "COA": "COA", "OOS": "OOS", "LABEL": "LBL", "HOLD": "HLD", "LOT": "LOT", "DESTR": "DES",
    "OOT": "OOT", "CRELEASE": "CRL", "TEST": "TST", "BATCH_VOID": "VOID", "RECON": "REC", "RETURN": "RTN", "ISSUE": "ISS", "RISK": "RA", "COMPLAINT": "CMP", "RECALL": "RCL", "REPORTCOPY": "RPT", "ARCHIVE": "ARC",
}


def seed_registry(session: Session, plant_id: int) -> None:
    for doc_type, prefix in DEFAULT_REGISTRY.items():
        if session.execute(select(NumberRegistry.id).where(NumberRegistry.plant_id == plant_id,
                                                           NumberRegistry.doc_type == doc_type)).first() is None:
            session.add(NumberRegistry(plant_id=plant_id, doc_type=doc_type, prefix=prefix))
    for doc_type, prefix in MASTER_REGISTRY.items():
        if session.execute(select(NumberRegistry.id).where(NumberRegistry.plant_id == plant_id,
                                                           NumberRegistry.doc_type == doc_type)).first() is None:
            session.add(NumberRegistry(plant_id=plant_id, doc_type=doc_type, prefix=prefix,
                                       format=MASTER_FORMAT, reset_policy="NEVER"))


def next_number(session: Session, plant_id: int, doc_type: str, when: datetime | None = None) -> str:
    when = when or utcnow()
    reg = session.execute(select(NumberRegistry).where(NumberRegistry.plant_id == plant_id,
                                                       NumberRegistry.doc_type == doc_type)).scalar_one_or_none()
    if reg is None:
        raise NotFound(f"No numbering scheme configured for '{doc_type}'")
    period = str(when.year) if reg.reset_policy == "YEARLY" else "ALL"
    seq_row = _get_or_create(session, plant_id, doc_type, period)
    session.execute(update(NumberSequence).where(NumberSequence.id == seq_row)
                    .values(current_value=NumberSequence.current_value + 1))
    value = session.execute(select(NumberSequence.current_value).where(NumberSequence.id == seq_row)).scalar_one()
    return reg.format.format(prefix=reg.prefix, year=when.year, yy=when.year % 100, seq=value)


def _get_or_create(session: Session, plant_id: int, doc_type: str, period: str) -> int:
    q = select(NumberSequence.id).where(NumberSequence.plant_id == plant_id,
                                        NumberSequence.doc_type == doc_type,
                                        NumberSequence.period_key == period)
    found = session.execute(q).scalar_one_or_none()
    if found:
        return found
    try:
        with session.begin_nested():
            row = NumberSequence(plant_id=plant_id, doc_type=doc_type, period_key=period, current_value=0)
            session.add(row)
            session.flush()
            return row.id
    except IntegrityError:
        return session.execute(q).scalar_one()


def default_plant_id(session: Session) -> int:
    from app.models.org import Plant
    pid = session.execute(select(Plant.id).order_by(Plant.id)).scalar()
    if pid is None:
        raise NotFound("No plant configured")
    return pid
