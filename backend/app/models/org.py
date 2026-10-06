from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base
from app.models.base import AuditedMixin


class Company(AuditedMixin, Base):
    __tablename__ = "company"
    __audit_module__ = "org"
    __reason_required__ = True

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    app_display_name: Mapped[str] = mapped_column(String(100), default="GMP Material & Manufacturing ERP")
    address: Mapped[str | None] = mapped_column(Text)
    gst_no: Mapped[str | None] = mapped_column(String(30))
    manufacturing_licence_no: Mapped[str | None] = mapped_column(String(60))
    drug_licence_no: Mapped[str | None] = mapped_column(String(60))
    contact_person: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(150))
    logo_document_id: Mapped[int | None] = mapped_column(PK, ForeignKey("document.id"))
    document_header: Mapped[str | None] = mapped_column(Text)
    document_footer: Mapped[str | None] = mapped_column(Text)
    report_format: Mapped[str | None] = mapped_column(String(50))
    label_format: Mapped[str | None] = mapped_column(String(50))
    date_format: Mapped[str] = mapped_column(String(30), default="DD-MMM-YYYY")
    time_format: Mapped[str] = mapped_column(String(30), default="HH:mm")


class Plant(AuditedMixin, Base):
    __tablename__ = "plant"
    __audit_module__ = "org"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("plant_code"),)

    company_id: Mapped[int] = mapped_column(PK, ForeignKey("company.id"), nullable=False)
    plant_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    site_name: Mapped[str | None] = mapped_column(String(150))
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Kolkata")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Department(AuditedMixin, Base):
    __tablename__ = "department"
    __audit_module__ = "org"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("plant_id", "code"),)

    plant_id: Mapped[int] = mapped_column(PK, ForeignKey("plant.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
