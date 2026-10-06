from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORM, Reasoned


class CompanyOut(ORM):
    id: int
    name: str
    app_display_name: str
    address: str | None
    gst_no: str | None
    manufacturing_licence_no: str | None
    drug_licence_no: str | None
    contact_person: str | None
    email: str | None
    phone: str | None
    website: str | None
    logo_document_id: int | None
    document_header: str | None
    document_footer: str | None
    report_format: str | None
    label_format: str | None
    date_format: str
    time_format: str


class CompanyUpdateIn(Reasoned):
    name: str | None = Field(default=None, max_length=200)
    app_display_name: str | None = None
    address: str | None = None
    gst_no: str | None = None
    manufacturing_licence_no: str | None = None
    drug_licence_no: str | None = None
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    document_header: str | None = None
    document_footer: str | None = None
    report_format: str | None = None
    label_format: str | None = None
    date_format: str | None = None
    time_format: str | None = None


class NumberRegistryOut(ORM):
    id: int
    plant_id: int
    doc_type: str
    prefix: str
    format: str
    reset_policy: str


class NumberRegistryIn(Reasoned):
    prefix: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    format: str = Field(max_length=100)
    reset_policy: str = Field(pattern="^(YEARLY|NEVER)$")


class ConfigOut(ORM):
    config_key: str
    value: str
    description: str | None


class ConfigIn(Reasoned):
    value: str = Field(max_length=2000)


class StepIn(BaseModel):
    seq: int
    name: str
    role_code: str
    min_approvals: int = Field(default=1, ge=1, le=10)
    esig_required: bool = True
    meaning: str = "APPROVED_BY"
    sla_hours: int | None = Field(default=None, ge=1)
    reject_to_seq: int | None = None


class WorkflowCreateIn(Reasoned):
    process_code: str = Field(pattern=r"^[a-z0-9_.]{3,60}$")
    name: str
    steps: list[StepIn]


class SignIn(Reasoned):
    password: str


class NotificationOut(ORM):
    id: int
    category: str
    title: str
    body: str | None
    ref_entity: str | None
    ref_id: str | None
    created_at: datetime
    read_at: datetime | None
