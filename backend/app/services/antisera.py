"""Phase 6b antisera extension: donor animals, immunisation, bleeds and plasma pools -> batch genealogy."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ValidationFailed
from app.models.manufacturing import Animal, BleedRecord, ImmunisationRecord, PlasmaPool
from app.models.master import Location, Material
from app.models.warehouse import MaterialBatch, MaterialContainer
from app.services import inventory, numbering

D = Decimal


def _plant(s: Session) -> int:
    return numbering.default_plant_id(s)


def immunise(session: Session, user, animal: Animal, antigen: str, dose: str | None, on: date, remarks: str | None) -> ImmunisationRecord:
    if animal.status != "ACTIVE":
        raise BusinessRuleError(f"Animal {animal.animal_tag} is {animal.status}", rule_id="BR-ANM-001")
    if on > date.today():
        raise ValidationFailed("Immunisation date cannot be in the future")
    r = ImmunisationRecord(animal_id=animal.id, antigen=antigen, dose=dose, administered_on=on, administered_by_id=user.id, remarks=remarks)
    session.add(r)
    session.flush()
    return r


def record_bleed(session: Session, user, animal: Animal, bled_on: date, volume_l: D, remarks: str | None) -> BleedRecord:
    if animal.status != "ACTIVE":
        raise BusinessRuleError(f"Animal {animal.animal_tag} is {animal.status} and cannot be bled", rule_id="BR-ANM-001")
    if bled_on > date.today():
        raise ValidationFailed("Bleed date cannot be in the future")
    last = session.execute(select(BleedRecord.bled_on).where(BleedRecord.animal_id == animal.id).order_by(BleedRecord.bled_on.desc())).scalars().first()
    if last and bled_on < last + timedelta(days=animal.min_bleed_interval_days):
        raise BusinessRuleError(f"Minimum bleed interval of {animal.min_bleed_interval_days} days not respected (last bleed {last.isoformat()})", rule_id="BR-ANM-002")
    if D(str(volume_l)) <= 0:
        raise ValidationFailed("Volume must be positive")
    b = BleedRecord(bleed_no=numbering.next_number(session, _plant(session), "BLEED"), animal_id=animal.id, bled_on=bled_on,
                    volume_l=volume_l, recorded_by_id=user.id, remarks=remarks)
    session.add(b)
    session.flush()
    return b


def create_pool(session: Session, user, bleed_ids: list[int], material: Material, quarantine_location: Location) -> PlasmaPool:
    if not bleed_ids:
        raise ValidationFailed("Select at least one bleed")
    bleeds = [session.get(BleedRecord, i) for i in dict.fromkeys(bleed_ids)]
    if any(b is None for b in bleeds):
        raise ValidationFailed("Unknown bleed")
    used = [b.bleed_no for b in bleeds if b.pool_id]
    if used:
        raise BusinessRuleError(f"Bleeds already pooled: {', '.join(used)}", rule_id="BR-ANM-003")
    if not quarantine_location.is_quarantine:
        raise BusinessRuleError("Plasma must be received into a quarantine location", rule_id="BR-QRN-001")
    total = sum((D(str(b.volume_l)) for b in bleeds), D(0))
    pool_no = numbering.next_number(session, _plant(session), "POOL")
    lot = MaterialBatch(lot_no=pool_no, material_id=material.id, source_type="POOL", quantity=total, unit_id=material.base_unit_id,
                        mfg_date=date.today(), disposition="QUARANTINE")
    session.add(lot)
    session.flush()
    session.add(MaterialContainer(batch_id=lot.id, container_no=1, quantity=total))
    inventory.post(session, txn_type="OUTPUT", batch=lot, quantity=total, to_location_id=quarantine_location.id, ref_doc_type="PLASMA_POOL", ref_doc_id=pool_no)
    pool = PlasmaPool(pool_no=pool_no, total_volume_l=total, material_batch_id=lot.id, created_by_id=user.id)
    session.add(pool)
    session.flush()
    for b in bleeds:
        b.pool_id = pool.id
    return pool


def genealogy(session: Session, pool: PlasmaPool) -> dict:
    out = []
    for b in session.execute(select(BleedRecord).where(BleedRecord.pool_id == pool.id)).scalars():
        a = session.get(Animal, b.animal_id)
        out.append({"bleed_no": b.bleed_no, "bled_on": b.bled_on.isoformat(), "volume_l": float(b.volume_l), "animal_tag": a.animal_tag})
    return {"pool_no": pool.pool_no, "total_volume_l": float(pool.total_volume_l), "lot_id": pool.material_batch_id, "bleeds": out}
