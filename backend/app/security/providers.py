"""Authentication providers (spec 3): local (Argon2id) and Active Directory / LDAP."""
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import app_log
from app.models.iam import User
from app.security.passwords import verify_password


class AuthProvider(Protocol):
    name: str

    def verify(self, user: User, password: str) -> bool: ...


class LocalProvider:
    name = "LOCAL"

    def verify(self, user: User, password: str) -> bool:
        return verify_password(user.password_hash, password)


class LdapProvider:
    """Binds as the user against the directory. Empty passwords are refused (anonymous-bind trap)."""

    name = "LDAP"

    def verify(self, user: User, password: str) -> bool:
        s = get_settings()
        if not s.ldap_enabled or not s.ldap_server_uri or not password:
            return False
        try:
            import ldap3
            server = ldap3.Server(s.ldap_server_uri, get_info=ldap3.NONE,
                                  connect_timeout=s.ldap_timeout_seconds,
                                  use_ssl=s.ldap_server_uri.lower().startswith("ldaps"))
            principal = s.ldap_bind_format.format(username=user.username)
            conn = ldap3.Connection(server, user=principal, password=password, auto_bind=False,
                                    receive_timeout=s.ldap_timeout_seconds)
            ok = bool(conn.bind())
            try:
                conn.unbind()
            except Exception:  # noqa: BLE001
                pass
            return ok
        except Exception as exc:  # noqa: BLE001 - directory down must fail closed
            app_log.warning("LDAP authentication error: %s", type(exc).__name__)
            return False


def provider_for(user: User) -> AuthProvider:
    return LdapProvider() if user.auth_source == "LDAP" else LocalProvider()
