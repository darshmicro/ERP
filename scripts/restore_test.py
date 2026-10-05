#!/usr/bin/env python
"""Backup / restore qualification helper (Validation Strategy §2, 'Backup/Restore qualification').

  python scripts/restore_test.py [--keep] [--record-url http://host --user U --password P]

SQL Server:  BACKUP DATABASE (CHECKSUM) -> RESTORE VERIFYONLY -> RESTORE to a scratch database -> compare row counts of every table
             -> run the audit-trail hash-chain verification against the restored copy -> measure elapsed time (RTO evidence) -> drop the scratch database.
SQLite:      file copy + the same count / hash-chain checks (development only).
Prints a JSON evidence record; with --record-url the result is POSTed to /api/v1/backup/records as a RESTORE_TEST entry (needs backup.status.record).
The account in MERP_DATABASE_URL needs BACKUP/RESTORE rights (use an administrative account for the qualification run only, never the application login)."""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def table_counts(engine) -> dict[str, int]:
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    out = {}
    with engine.connect() as c:
        for t in sorted(insp.get_table_names()):
            out[t] = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
    return out


def run_ddl(conn, sql: str):
    """BACKUP/RESTORE emit informational result sets; the statement only completes when they are consumed (pyodbc)."""
    cur = conn.connection.cursor()
    cur.execute(sql)
    while True:
        try:
            if not cur.nextset():
                break
        except Exception:  # noqa: BLE001
            break
    cur.close()


def chain_ok(url: str) -> dict:
    from app.audit import service as audit
    from app.core import db
    db.configure(url)
    s = db.new_session()
    try:
        return audit.verify_chain(s)
    finally:
        s.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the restored scratch database")
    ap.add_argument("--record-url")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--backup-dir", default=None, help="directory on the DB server for the .bak (SQL Server)")
    a = ap.parse_args()
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from app.core.config import get_settings
    url = os.environ.get("MERP_MIGRATION_DATABASE_URL") or get_settings().database_url
    u = make_url(url)
    ev: dict = {"started_at": datetime.now(timezone.utc).isoformat(), "dialect": u.get_backend_name(), "database": u.database}
    t0 = time.perf_counter()
    if u.get_backend_name() == "mssql":
        db = u.database
        scratch = f"{db}_restore_test"
        bak = f"{(a.backup_dir or '/var/opt/mssql/data').rstrip('/')}/{db}_{int(time.time())}.bak"
        master = create_engine(u.set(database="master"), isolation_level="AUTOCOMMIT")
        with master.connect() as c:
            run_ddl(c, f"BACKUP DATABASE [{db}] TO DISK = N'{bak}' WITH INIT, CHECKSUM, COMPRESSION, NAME = N'merp-qualification'")
            ev["backup_file"] = bak
            run_ddl(c, f"RESTORE VERIFYONLY FROM DISK = N'{bak}' WITH CHECKSUM")
            ev["verifyonly"] = "OK"
            files = c.execute(text(f"RESTORE FILELISTONLY FROM DISK = N'{bak}'")).fetchall()
            data_dir = c.execute(text("SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(300))")).scalar() or "/var/opt/mssql/data/"
            moves = ", ".join(f"MOVE N'{f[0]}' TO N'{data_dir}{scratch}_{i}{'.ldf' if f[2] == 'L' else '.mdf'}'" for i, f in enumerate(files))
            t_restore = time.perf_counter()
            run_ddl(c, f"IF DB_ID(N'{scratch}') IS NOT NULL BEGIN ALTER DATABASE [{scratch}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{scratch}]; END")
            run_ddl(c, f"RESTORE DATABASE [{scratch}] FROM DISK = N'{bak}' WITH {moves}, REPLACE, CHECKSUM")
            ev["restore_seconds"] = round(time.perf_counter() - t_restore, 2)
        src, dst = create_engine(u), create_engine(u.set(database=scratch))
        restored_url = u.set(database=scratch).render_as_string(hide_password=False)
    else:
        src_path = u.database
        tmp = tempfile.mkdtemp()
        dst_path = os.path.join(tmp, "restored.db")
        shutil.copy2(src_path, dst_path)
        src, dst = create_engine(u), create_engine(f"sqlite:///{dst_path}")
        restored_url = f"sqlite:///{dst_path}"
    cs, cd = table_counts(src), table_counts(dst)
    diff = {t: (cs[t], cd.get(t)) for t in cs if cs[t] != cd.get(t)}
    ev["tables"] = len(cs)
    ev["rows_source"] = sum(cs.values())
    ev["rows_restored"] = sum(cd.values())
    ev["count_differences"] = diff
    ev["audit_chain_restored"] = chain_ok(restored_url)
    ev["elapsed_seconds_total"] = round(time.perf_counter() - t0, 2)
    ev["rto_minutes_measured"] = max(1, round(ev["elapsed_seconds_total"] / 60))
    ev["result"] = "SUCCESS" if not diff and ev["audit_chain_restored"].get("ok") else "FAILED"
    if u.get_backend_name() == "mssql" and not a.keep:
        with create_engine(u.set(database="master"), isolation_level="AUTOCOMMIT").connect() as c:
            run_ddl(c, f"ALTER DATABASE [{scratch}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{scratch}]")
        ev["scratch_dropped"] = True
    print(json.dumps(ev, indent=2, default=str))
    if a.record_url and a.user and a.password:
        import urllib.request
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        r = json.load(op.open(urllib.request.Request(f"{a.record_url}/api/v1/auth/login", json.dumps({"username": a.user, "password": a.password}).encode(), {"Content-Type": "application/json"})))
        body = {"backup_type": "RESTORE_TEST", "performed_at": datetime.now(timezone.utc).isoformat(), "result": ev["result"], "location": ev.get("backup_file") or "file copy",
                "audit_chain_verified": bool(ev["audit_chain_restored"].get("ok")), "rto_minutes": ev["rto_minutes_measured"], "tool": "scripts/restore_test.py", "notes": f"{ev['tables']} tables, {ev['rows_restored']} rows, diff={len(diff)}"}
        op.open(urllib.request.Request(f"{a.record_url}/api/v1/backup/records", json.dumps(body).encode(), {"Content-Type": "application/json", "X-CSRF-Token": r["csrf_token"]}))
        print("recorded in /backup/records")
    return 0 if ev["result"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
