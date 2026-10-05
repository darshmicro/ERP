"""Database-level immutability for append-only tables (defence in depth, C-06).

Even if application code or a compromised app account tries UPDATE/DELETE, the DB refuses.
The app DB login additionally has no UPDATE/DELETE grant on these tables (docs/architecture).
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

APPEND_ONLY_TABLES = ("audit_trail", "e_signature", "security_event", "gmp_status_history",
                      "record_action", "workflow_transaction", "inventory_transaction", "material_label",
                      "storage_temperature_log", "coa", "material_issue", "ipc_result", "immunisation_record", "sop_acknowledgement",
                      "report_run", "archive_batch", "backup_record")
MSG = "Append-only GMP record: UPDATE/DELETE is not permitted"


def trigger_statements(dialect: str, tables=APPEND_ONLY_TABLES) -> list[str]:
    stmts: list[str] = []
    if dialect == "sqlite":
        for t in tables:
            for op in ("UPDATE", "DELETE"):
                stmts.append(f"CREATE TRIGGER IF NOT EXISTS trg_{t}_no_{op.lower()} BEFORE {op} ON {t} "
                             f"BEGIN SELECT RAISE(ABORT, '{MSG}'); END")
    elif dialect == "postgresql":
        stmts.append("CREATE OR REPLACE FUNCTION merp_block_mutation() RETURNS trigger AS $$ "
                     f"BEGIN RAISE EXCEPTION '{MSG}'; END; $$ LANGUAGE plpgsql")
        for t in tables:
            stmts.append(f"DROP TRIGGER IF EXISTS trg_{t}_immutable ON {t}")
            stmts.append(f"CREATE TRIGGER trg_{t}_immutable BEFORE UPDATE OR DELETE ON {t} "
                         "FOR EACH ROW EXECUTE FUNCTION merp_block_mutation()")
    elif dialect == "mssql":
        for t in tables:
            stmts.append(f"CREATE OR ALTER TRIGGER trg_{t}_immutable ON {t} INSTEAD OF UPDATE, DELETE AS "
                         f"BEGIN RAISERROR('{MSG}', 16, 1); END")
    else:
        raise NotImplementedError(dialect)
    return stmts


def install_triggers(bind: Engine | Connection, tables=APPEND_ONLY_TABLES) -> None:
    dialect = bind.dialect.name
    conn_ctx = bind.begin() if isinstance(bind, Engine) else _Passthrough(bind)
    with conn_ctx as conn:
        for stmt in trigger_statements(dialect, tables):
            conn.execute(text(stmt))


class _Passthrough:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *a):
        return False


def drop_statements(dialect: str, tables=APPEND_ONLY_TABLES) -> list[str]:
    out = []
    for t in tables:
        if dialect == "sqlite":
            out += [f"DROP TRIGGER IF EXISTS trg_{t}_no_update", f"DROP TRIGGER IF EXISTS trg_{t}_no_delete"]
        elif dialect == "postgresql":
            out.append(f"DROP TRIGGER IF EXISTS trg_{t}_immutable ON {t}")
        elif dialect == "mssql":
            out.append(f"DROP TRIGGER IF EXISTS trg_{t}_immutable")
    return out


def drop_triggers(bind, tables=APPEND_ONLY_TABLES) -> None:
    for stmt in drop_statements(bind.dialect.name, tables):
        bind.execute(text(stmt))
