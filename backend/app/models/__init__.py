"""Import all models so metadata is complete (Alembic, create_all)."""
from app.models.audit import (AuditChainHead, AuditTrail, ErrorLog, ESignature, RecordAction,  # noqa: F401
                              SecurityEvent, StatusHistory)
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin  # noqa: F401
from app.models.iam import (PasswordHistory, Permission, Role, RolePermission, SodRule,  # noqa: F401
                            TrainingRecord, User, UserRole, UserSession)
from app.models.org import Company, Department, Plant  # noqa: F401
from app.models.platform import (Document, NumberRegistry, NumberSequence, Notification,  # noqa: F401
                                 SystemConfiguration, WorkflowDefinition, WorkflowInstance,
                                 WorkflowStep, WorkflowTransaction)
