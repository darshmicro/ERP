from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORM, Reasoned


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str | None
    designation: str | None
    department_id: int | None
    plant_id: int | None
    auth_source: str
    is_active: bool
    must_change_password: bool
    access_expiry: date | None
    locked_until: datetime | None
    last_login_at: datetime | None


class MeOut(BaseModel):
    user: UserOut
    roles: list[str]
    permissions: list[str]
    csrf_token: str | None = None


class UserCreateIn(Reasoned):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=150)
    designation: str | None = None
    department_id: int | None = None
    plant_id: int | None = None
    auth_source: str = Field(default="LOCAL", pattern="^(LOCAL|LDAP)$")
    access_expiry: date | None = None
    initial_role_codes: list[str] = []


class UserUpdateIn(Reasoned):
    full_name: str | None = Field(default=None, max_length=150)
    email: str | None = None
    designation: str | None = None
    department_id: int | None = None
    plant_id: int | None = None
    access_expiry: date | None = None


class ActiveIn(Reasoned):
    active: bool


class RoleAssignIn(Reasoned):
    role_code: str
    valid_to: date | None = None


class RoleOut(ORM):
    id: int
    role_code: str
    name: str
    description: str | None
    is_system: bool
    is_admin_role: bool
    is_active: bool


class RoleCreateIn(Reasoned):
    role_code: str = Field(pattern=r"^[A-Z0-9_]{3,50}$")
    name: str
    description: str | None = None
    is_admin_role: bool = False


class RolePermissionsIn(Reasoned):
    permissions: list[str]


class TrainingIn(Reasoned):
    user_id: int
    training_code: str
    document_version: str | None = None
    trained_on: date
    valid_until: date | None = None
