"""Model mixins: audited masters, append-only (AO) records, status-controlled records."""
from datetime import datetime

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow


class AuditedMixin:
    """Every INSERT/UPDATE is captured field-by-field in audit_trail inside the same transaction.

    Class options:
      __audit_module__          module label in the audit trail
      __audit_exclude__         volatile/technical fields not audited
      __audit_sensitive__       fields audited but values redacted
      __reason_required__       UPDATE of audited fields requires a reason (GMP masters)
    Physical DELETE of an audited record is refused by the ORM (A-04).
    """

    __audit_module__ = "core"
    __audit_exclude__: frozenset = frozenset()
    __audit_sensitive__: frozenset = frozenset()
    __reason_required__ = False

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    # actor ids are plain integers (no FK): avoids circular DDL and survives any user lifecycle
    created_by_id: Mapped[int | None] = mapped_column(PK, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(PK, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls):  # optimistic concurrency -> StaleDataError -> 409
        return {"version_id_col": cls.row_version}


class AppendOnlyMixin:
    """Append-only record: ORM and DB triggers both refuse UPDATE/DELETE."""

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)


class StatefulMixin:
    """Marks a status column controlled by the status engine (BR-SEC-001).

    Subclasses set __status_field__ = "status". Direct assignment after creation is refused
    unless inside workflows.state_machine.transition_context().
    """

    __status_field__ = "status"


__all__ = ["AuditedMixin", "AppendOnlyMixin", "StatefulMixin", "Base"]


class VersionedMixin(StatefulMixin):
    """Controlled, versioned master (spec 60, BR-HIS-001).

    Lifecycle DRAFT -> UNDER_REVIEW -> APPROVED -> SUPERSEDED. Only DRAFT rows may be edited; the
    content of APPROVED/SUPERSEDED rows is immutable (enforced in audit/hooks.py). A change = new
    version row (service `versioning.new_version`) that supersedes the current one when approved.
    Concrete classes add: version_no, status, effective_from, effective_to, supersedes_id,
    approved_signature_id, change_reason and a business-number column named in __version_key__.
    """

    __version_key__ = "doc_no"
    __editable_statuses__ = ("DRAFT",)


class VersionChildMixin:
    """Row owned by a VersionedMixin parent; editable only while the parent is DRAFT."""

    __version_parent_model__ = ""   # dotted name resolved lazily, e.g. "Specification"
    __version_parent_fk__ = ""      # column name holding the parent id
