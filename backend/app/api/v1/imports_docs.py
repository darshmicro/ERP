"""Controlled Excel import endpoints and generic document access."""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.crud import to_dict
from app.api.deps import Principal, get_db, require
from app.api.helpers import use_reason
from app.core.errors import NotFound, PermissionDenied
from app.models.importing import ImportJob
from app.models.platform import DocLink, Document
from app.schemas.common import Reasoned
from app.services import documents, importing

router = APIRouter()


class SignedAction(Reasoned):
    password: str


@router.get("/imports/templates/{entity}", tags=["Import"])
def template(entity: str, p: Principal = Depends(require("import.job.create"))):
    return Response(importing.template_xlsx(entity),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{entity}_import_template.xlsx"'})


@router.post("/imports", status_code=201, tags=["Import"])
async def upload(entity: str = Form(...), file: UploadFile = File(...), p: Principal = Depends(require("import.job.create")),
                 s: Session = Depends(get_db)):
    use_reason(f"Import upload ({entity})")
    data = await file.read()
    job = importing.upload(s, entity, file.filename or "import.xlsx", data, p.user)
    s.commit()
    return to_dict(job)


@router.get("/imports", tags=["Import"])
def list_jobs(p: Principal = Depends(require("import.job.read")), s: Session = Depends(get_db)):
    return [to_dict(j) for j in s.execute(select(ImportJob).order_by(ImportJob.id.desc()).limit(100)).scalars()]


@router.get("/imports/{job_id}", tags=["Import"])
def preview(job_id: int, errors_only: bool = False, limit: int = 200, p: Principal = Depends(require("import.job.read")),
            s: Session = Depends(get_db)):
    r = importing.preview(s, job_id, min(limit, 1000), errors_only)
    return {"job": to_dict(r["job"]), "rows": r["rows"]}


@router.get("/imports/{job_id}/error-report", tags=["Import"])
def error_report(job_id: int, p: Principal = Depends(require("import.job.read")), s: Session = Depends(get_db)):
    importing._job(s, job_id)
    return Response(importing.error_report_xlsx(s, job_id),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="import_{job_id}_errors.xlsx"'})


@router.post("/imports/{job_id}/submit", tags=["Import"])
def submit(job_id: int, p: Principal = Depends(require("import.job.create")), s: Session = Depends(get_db)):
    importing.submit(s, importing._job(s, job_id), p.user)
    s.commit()
    return {"ok": True}


class DecisionIn(SignedAction):
    approve: bool = True


@router.post("/imports/{job_id}/decision", tags=["Import"])
def decide(job_id: int, body: DecisionIn, p: Principal = Depends(require("import.job.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    importing.decide(s, importing._job(s, job_id), p.user, body.password, body.approve, body.reason or "")
    s.commit()
    return {"ok": True}


@router.post("/imports/{job_id}/execute", tags=["Import"])
def execute(job_id: int, p: Principal = Depends(require("import.job.create")), s: Session = Depends(get_db)):
    job = importing._job(s, job_id)
    res = importing.execute(s, job, p.user)
    s.commit()
    return res


# ---- documents
@router.get("/documents/{doc_id}/download", tags=["Documents"])
def download(doc_id: int, p: Principal = Depends(require("doc.document.read")), s: Session = Depends(get_db)):
    doc = s.get(Document, doc_id)
    if doc is None:
        raise NotFound("Document not found")
    data = documents.read(s, doc)  # verifies SHA-256, audits the download
    s.commit()
    return Response(data, media_type=doc.mime_type,
                    headers={"Content-Disposition": f'attachment; filename="{doc.original_name}"'})


class LinkIn(Reasoned):
    entity: str
    record_id: str


@router.post("/documents", status_code=201, tags=["Documents"])
async def upload_linked(entity: str = Form(...), record_id: str = Form(...), doc_no: str | None = Form(None),
                        version: str = Form("1"), file: UploadFile = File(...),
                        p: Principal = Depends(require("doc.document.create")), s: Session = Depends(get_db)):
    """Attach a controlled document to a record. Documents are write-once: to replace one, upload a new version."""
    if entity not in {"material", "specification", "stp", "equipment", "customer", "vendor"}:
        raise PermissionDenied("Attachments are not enabled for this record type")
    use_reason(f"Document attached to {entity} {record_id}")
    doc = documents.store(s, file.filename or "document", await file.read(), doc_no=doc_no, version=version)
    s.add(DocLink(document_id=doc.id, entity=entity, record_id=record_id, linked_by_id=p.user.id))
    s.commit()
    return {"document_id": doc.id, "sha256": doc.sha256}


@router.get("/documents", tags=["Documents"])
def list_linked(entity: str, record_id: str, p: Principal = Depends(require("doc.document.read")), s: Session = Depends(get_db)):
    rows = s.execute(select(DocLink, Document).join(Document, Document.id == DocLink.document_id)
                     .where(DocLink.entity == entity, DocLink.record_id == record_id).order_by(Document.id.desc())).all()
    return [{"document_id": d.id, "filename": d.original_name, "doc_no": d.doc_no, "version": d.version,
             "sha256": d.sha256, "uploaded_at": d.uploaded_at.isoformat(), "size_bytes": d.size_bytes} for _l, d in rows]
