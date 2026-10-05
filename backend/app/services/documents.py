"""Controlled document storage: allow-listed types, magic-byte check, SHA-256, write-once (BR-DOC-001)."""
import hashlib
import os
import uuid

from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import get_context
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.models.platform import Document

ALLOWED = {  # ext -> (mime, magic prefixes)
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b"PK\x03\x04",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b"PK\x03\x04",)),
}


def store(session: Session, filename: str, data: bytes, *, allowed_ext: set[str] | None = None,
          doc_no: str | None = None, version: str = "1", supersedes_id: int | None = None) -> Document:
    cfg = get_settings()
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED or (allowed_ext and ext not in allowed_ext):
        raise ValidationFailed(f"File type '{ext}' is not allowed")
    if len(data) == 0 or len(data) > cfg.max_upload_mb * 1024 * 1024:
        raise ValidationFailed(f"File must be between 1 byte and {cfg.max_upload_mb} MB")
    mime, magics = ALLOWED[ext]
    if not any(data.startswith(m) for m in magics):
        raise ValidationFailed("File content does not match its extension")
    sha = hashlib.sha256(data).hexdigest()
    key = f"{sha[:2]}/{uuid.uuid4().hex}"  # random name, outside web root
    path = os.path.join(cfg.file_storage_path, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "xb") as fh:  # 'x' => never overwrite
        fh.write(data)
    safe_name = os.path.basename(filename)[:255]
    doc = Document(original_name=safe_name, mime_type=mime, size_bytes=len(data), sha256=sha,
                   storage_key=key, doc_no=doc_no, version=version, supersedes_id=supersedes_id,
                   uploaded_by_id=get_context().user_id)
    session.add(doc)
    session.flush()
    audit.log_event(session, module="document", entity="document", record_id=doc.id, action="UPLOAD",
                    new=f"{safe_name} sha256={sha}")
    return doc


def read(session: Session, doc: Document) -> bytes:
    cfg = get_settings()
    with open(os.path.join(cfg.file_storage_path, doc.storage_key), "rb") as fh:
        data = fh.read()
    if hashlib.sha256(data).hexdigest() != doc.sha256:
        raise ValidationFailed("Stored document failed its integrity (SHA-256) check", code="DOC_INTEGRITY")
    audit.log_event(session, module="document", entity="document", record_id=doc.id, action="DOWNLOAD")
    return data


def read_raw(doc: Document) -> bytes:
    """Integrity-checked read without an audit event (internal use, e.g. embedding the company logo)."""
    cfg = get_settings()
    with open(os.path.join(cfg.file_storage_path, doc.storage_key), "rb") as fh:
        data = fh.read()
    if hashlib.sha256(data).hexdigest() != doc.sha256:
        raise ValidationFailed("Stored document failed its integrity (SHA-256) check", code="DOC_INTEGRITY")
    return data
