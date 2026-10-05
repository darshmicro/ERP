"""One-time bootstrap: baseline reference data + first System Administrator.

Credentials come from environment variables (MERP_BOOTSTRAP_ADMIN_USERNAME / _PASSWORD); there is no
default or hidden account. The user must change the password at first login. Run once, then remove
the variables from the environment.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import select  # noqa: E402

from app.audit import hooks  # noqa: E402
from app.audit.context import AuditContext, audit_context  # noqa: E402
from app.core import db  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models import Role, User, UserRole  # noqa: E402
from app.services import auth_service, seed  # noqa: E402


def main() -> int:
    username = os.environ.get("MERP_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.environ.get("MERP_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username or not password:
        print("Set MERP_BOOTSTRAP_ADMIN_USERNAME and MERP_BOOTSTRAP_ADMIN_PASSWORD", file=sys.stderr)
        return 2
    db.configure(get_settings().database_url)
    hooks.install()
    s = db.new_session()
    try:
        with audit_context(AuditContext(user_name="BOOTSTRAP", reason="Initial system bootstrap")):
            seed.seed_baseline(s)
            if s.execute(select(User).where(User.username == username)).scalar_one_or_none():
                print("Admin user already exists; nothing to do.")
                s.commit()
                return 0
            u = User(username=username, full_name="System Administrator", auth_source="LOCAL")
            s.add(u)
            s.flush()
            auth_service.set_password(s, u, password, must_change=True, enforce_history=False)
            role = s.execute(select(Role).where(Role.role_code == "SYSTEM_ADMIN")).scalar_one()
            s.add(UserRole(user_id=u.id, role_id=role.id, valid_from=date.today(), reason="bootstrap"))
            s.commit()
        print(f"Created System Administrator '{username}'. Password change required at first login.")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    raise SystemExit(main())
