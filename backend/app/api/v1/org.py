from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_user, get_db, require
from app.api.helpers import use_reason
from app.core.errors import NotFound
from app.models.org import Company, Plant
from app.models.platform import Document, NumberRegistry, SystemConfiguration
from app.schemas.platform import (CompanyOut, CompanyUpdateIn, ConfigIn, ConfigOut, NumberRegistryIn,
                                  NumberRegistryOut)
from app.services import documents

router = APIRouter(tags=["organization"])


def _company(s: Session) -> Company:
    c = s.execute(select(Company).order_by(Company.id)).scalars().first()
    if c is None:
        raise NotFound("Company is not configured")
    return c


@router.get("/company/branding")
def branding(s: Session = Depends(get_db)):
    """Public (pre-login) branding: name + logo only."""
    c = s.execute(select(Company).order_by(Company.id)).scalars().first()
    if c is None:
        return {"name": "GMP-MERP", "app_display_name": "GMP Material & Manufacturing ERP", "logo_url": None}
    return {"name": c.name, "app_display_name": c.app_display_name,
            "logo_url": "/api/v1/company/logo" if c.logo_document_id else None}


@router.get("/company/logo")
def logo(s: Session = Depends(get_db)):
    c = _company(s)
    if not c.logo_document_id:
        raise NotFound("No logo configured")
    doc = s.get(Document, c.logo_document_id)
    data = documents.read(s, doc)
    return Response(content=data, media_type=doc.mime_type, headers={"Cache-Control": "public, max-age=300"})


@router.get("/company", response_model=CompanyOut)
def get_company(p: Principal = Depends(require("org.company.read")), s: Session = Depends(get_db)):
    return _company(s)


@router.put("/company", response_model=CompanyOut)
def update_company(body: CompanyUpdateIn, p: Principal = Depends(require("org.company.update")),
                   s: Session = Depends(get_db)):
    use_reason(body.reason)
    c = _company(s)
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(c, k, v)
    s.commit()
    return c


@router.post("/company/logo")
async def upload_logo(reason: str, file: UploadFile = File(...), p: Principal = Depends(require("org.company.update")),
                      s: Session = Depends(get_db)):
    use_reason(reason)
    data = await file.read()
    doc = documents.store(s, file.filename or "logo.png", data, allowed_ext={".png", ".jpg", ".jpeg"})
    c = _company(s)
    c.logo_document_id = doc.id
    s.commit()
    return {"document_id": doc.id, "sha256": doc.sha256}


@router.get("/plants")
def plants(p: Principal = Depends(require("org.plant.read")), s: Session = Depends(get_db)):
    return [{"id": x.id, "plant_code": x.plant_code, "name": x.name, "timezone": x.timezone, "is_active": x.is_active}
            for x in s.execute(select(Plant).order_by(Plant.plant_code)).scalars()]


@router.get("/numbering", response_model=list[NumberRegistryOut])
def numbering(p: Principal = Depends(require("config.numbering.read")), s: Session = Depends(get_db)):
    return s.execute(select(NumberRegistry).order_by(NumberRegistry.doc_type)).scalars().all()


@router.put("/numbering/{doc_type}", response_model=NumberRegistryOut)
def update_numbering(doc_type: str, body: NumberRegistryIn, p: Principal = Depends(require("config.numbering.update")),
                     s: Session = Depends(get_db)):
    use_reason(body.reason)
    reg = s.execute(select(NumberRegistry).where(NumberRegistry.doc_type == doc_type)).scalar_one_or_none()
    if reg is None:
        raise NotFound("Unknown document type")
    try:  # validate the format template before accepting it
        body.format.format(prefix="X", year=2026, yy=26, seq=1)
    except Exception:  # noqa: BLE001
        from app.core.errors import ValidationFailed
        raise ValidationFailed("Format must use only {prefix} {year} {yy} {seq[:0Nd]}")
    reg.prefix, reg.format, reg.reset_policy = body.prefix, body.format, body.reset_policy
    s.commit()
    return reg


@router.get("/config", response_model=list[ConfigOut])
def list_config(p: Principal = Depends(require("config.system.read")), s: Session = Depends(get_db)):
    return s.execute(select(SystemConfiguration).order_by(SystemConfiguration.config_key)).scalars().all()


@router.put("/config/{key}", response_model=ConfigOut)
def set_config(key: str, body: ConfigIn, p: Principal = Depends(require("config.system.update")),
               s: Session = Depends(get_db)):
    use_reason(body.reason)
    row = s.execute(select(SystemConfiguration).where(SystemConfiguration.config_key == key)).scalar_one_or_none()
    if row is None:
        raise NotFound("Unknown configuration key")
    row.value = body.value
    s.commit()
    return row
