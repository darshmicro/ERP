import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.db import Base


def test_alembic_upgrade_matches_models_and_installs_triggers(tmp_path):
    url = f"sqlite:///{tmp_path/'m.db'}"
    env = {**os.environ, "MERP_MIGRATION_DATABASE_URL": url}
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    r = subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
                       cwd=root, env={**env, "PYTHONPATH": "backend"}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    eng = create_engine(url)
    insp = inspect(eng)
    assert {t for t in Base.metadata.tables if not t.startswith("demo_")} <= set(insp.get_table_names())
    with eng.begin() as c:
        triggers = {row[0] for row in c.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))}
    assert "trg_audit_trail_no_update" in triggers and "trg_e_signature_no_delete" in triggers
    # downgrade then upgrade again
    for cmd in ("downgrade base", "upgrade head"):
        r = subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", *cmd.split()],
                           cwd=root, env={**env, "PYTHONPATH": "backend"}, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_ddl_generated_for_all_dialects():
    from app.audit.immutability import trigger_statements
    for d in ("sqlite", "postgresql", "mssql"):
        assert trigger_statements(d)
    with pytest.raises(NotImplementedError):
        trigger_statements("oracle")
