#!/usr/bin/env python
"""Generate the machine-derived validation documents from the code base (so they cannot drift from the system).

  python scripts/gen_validation_docs.py [--junit docs/validation/evidence/junit.xml]

Writes:
  docs/validation/urs.md                      User Requirements Specification (from scripts/validation_requirements.py)
  docs/validation/rtm.md                      Requirements Traceability Matrix (URS <-> rules <-> tests <-> last result); fails on missing tests
  docs/validation/configuration-specification.md  roles, permissions, SoD, workflows, numbering, configuration keys (read from a freshly seeded database)
  docs/validation/access-control-matrix.md    role x module permission matrix
  docs/architecture/12-data-dictionary.md     every table/column/constraint
  docs/architecture/13-er-diagram.md          Mermaid ER diagrams per module
"""
import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("MERP_AUDIT_HMAC_KEY", "validation-doc-generation-key-0123456789")
os.environ.setdefault("MERP_SECRET_KEY", "validation-doc-generation-secret-0123456789")
os.environ.setdefault("MERP_ENVIRONMENT", "development")

IMPACT = {"C": "Critical", "M": "Major", "N": "Minor"}


def collect_tests() -> set[str]:
    out = subprocess.run([sys.executable, "-m", "pytest", "tests", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True).stdout
    return {line.strip() for line in out.splitlines() if "::" in line and not line.startswith(" ")}


def read_junit(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    res = {}
    for tc in ET.parse(path).getroot().iter("testcase"):
        cls = tc.get("classname", "")
        node = cls.replace(".", "/") + ".py::" + tc.get("name", "")
        st = "PASS"
        if tc.find("failure") is not None or tc.find("error") is not None:
            st = "FAIL"
        elif tc.find("skipped") is not None:
            st = "SKIP"
        res[node] = st
    return res


def gen_urs_rtm(collected: set[str], results: dict[str, str], results2: dict[str, str] | None = None) -> tuple[int, int, int]:
    results2 = results2 or {}
    from validation_requirements import REQS
    missing, rows, urs = [], [], []
    mapped = set()
    by_area = collections.OrderedDict()
    for rid, area, text, impact, rules, tests in REQS:
        by_area.setdefault(area, []).append((rid, text, impact, rules, tests))
        for t in tests:
            mapped.add(t)
            if t not in collected:
                missing.append((rid, t))
    if missing:
        print("MISSING TESTS:\n" + "\n".join(f"  {r}: {t}" for r, t in missing))
        raise SystemExit(2)
    # URS
    lines = ["# User Requirements Specification (URS)", "",
             "> Derived from the master requirements (prompt §1–§100) and the architecture pack (`docs/architecture/`). GMP impact: **Critical** = direct effect on product quality, patient safety or data integrity; **Major**; **Minor**.",
             "> Generated from `scripts/validation_requirements.py` — edit that file, not this one.", "",
             f"Total requirements: **{len(REQS)}** ({sum(1 for r in REQS if r[3] == 'C')} critical, {sum(1 for r in REQS if r[3] == 'M')} major, {sum(1 for r in REQS if r[3] == 'N')} minor).", ""]
    for area, items in by_area.items():
        lines += [f"## {area}", "", "| ID | Requirement | GMP impact | Business rules |", "|---|---|---|---|"]
        lines += [f"| {rid} | {text} | {IMPACT[imp]} | {rules or '—'} |" for rid, text, imp, rules, _t in items]
        lines.append("")
    (ROOT / "docs/validation/urs.md").write_text("\n".join(lines), encoding="utf-8")
    # RTM
    ran = bool(results)
    lines = ["# Requirements Traceability Matrix (RTM)", "",
             f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from `scripts/validation_requirements.py` and the automated test inventory. "
             + ("Result columns = outcome in `docs/validation/evidence/junit.xml` (SQLite development database) and `junit-sqlserver-*.xml` (SQL Server 2022)." if ran else "No execution evidence was supplied (run with `--junit`)."), "",
             "URS → business rule → automated test (OQ evidence) → result. Every referenced test was verified to exist by collection; the generator aborts otherwise.", ""]
    total_tests = 0
    totals = collections.Counter()
    for area, items in by_area.items():
        lines += [f"## {area}", "", "| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |", "|---|---|---|---|---|---|"]
        for rid, text, imp, rules, tests in items:
            for i, t in enumerate(tests):
                r = results.get(t, "not run" if not ran else "n/a")
                r2 = results2.get(t, "not run" if results2 else "—")
                totals[r] += 1
                total_tests += 1
                lines.append(f"| {rid if i == 0 else ''} | {IMPACT[imp] if i == 0 else ''} | {rules if i == 0 else ''} | `{t}` | {r} | {r2} |")
        lines.append("")
    orphans = sorted(t for t in collected if t not in mapped)
    lines += ["## Summary", "", f"* Requirements: **{len(REQS)}**; all have at least one automated test: **{all(r[5] for r in REQS)}**", f"* Mapped test references: **{total_tests}** (distinct tests: **{len(mapped)}**)",
              "* Results of mapped tests (SQLite): " + ", ".join(f"{k}: {v}" for k, v in sorted(totals.items())) + (f"; SQL Server: {dict(collections.Counter(results2.get(t, 'not run') for _r in REQS for t in _r[5]))}" if results2 else ""), "* SQL Server column: the two `tests/integration/test_migrations.py` tests spawn SQLite subprocesses and are deselected there; the migration chain is verified on SQL Server separately (`docs/validation/sqlserver-verification.md`: 0001→0009 up/down/up, 110 tables, 17 triggers).", f"* Collected automated tests in total: **{len(collected)}**; not referenced by a requirement (supporting/unit tests): **{len(orphans)}**", ""]
    lines += ["### The 15 mandatory critical tests (prompt §77)", "", "| # | Rule | Test |", "|---|---|---|"]
    crit = [("1", "Expired vendor qualification blocks PO", "tests/workflows/test_purchase_rules.py::test_crit_01_expired_vendor_cannot_create_po"), ("2", "Unapproved vendor blocks PO", "tests/workflows/test_purchase_rules.py::test_crit_02_unapproved_vendor_cannot_purchase"),
            ("3", "Vendor not approved for material blocks PO", "tests/workflows/test_purchase_rules.py::test_crit_03_wrong_vendor_material_combination"), ("4", "Quarantine material cannot be issued", "tests/workflows/test_warehouse.py::test_crit_04_quarantine_material_cannot_be_issued"),
            ("5", "Rejected material cannot be issued", "tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued"), ("6", "Unreleased FG cannot be dispatched", "tests/workflows/test_dispatch.py::test_crit_06_unreleased_fg_cannot_be_dispatched"),
            ("7", "Expired material cannot be issued", "tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued"), ("8", "Quality hold blocks issue/use/dispatch", "tests/validation/test_critical_15.py::test_crit_08_quality_hold_blocks_issue_use_and_dispatch"),
            ("9", "Audit trail cannot be modified/deleted", "tests/validation/test_critical_15.py::test_crit_09_audit_trail_cannot_be_modified_or_deleted"), ("10", "E-signature required for configured actions", "tests/validation/test_critical_15.py::test_crit_10_electronic_signature_required_and_bound_to_the_record"),
            ("11", "Creator cannot approve own transaction", "tests/validation/test_critical_15.py::test_crit_11_creator_cannot_approve_own_transaction"), ("12", "Historical GMP records never overwritten", "tests/validation/test_critical_15.py::test_crit_12_historical_gmp_records_are_never_overwritten"),
            ("13", "Every movement creates an inventory transaction", "tests/validation/test_critical_15.py::test_crit_13_every_stock_movement_creates_an_inventory_transaction"), ("14", "Issued material linked to production batch", "tests/validation/test_critical_15.py::test_crit_14_issued_material_is_always_linked_to_lot_and_production_batch"),
            ("15", "Reconciliation discrepancy highlighted", "tests/validation/test_critical_15.py::test_crit_15_reconciliation_discrepancy_is_highlighted_and_blocks_progress")]
    for n, rule, t in crit:
        assert t in collected, t
        lines.append(f"| {n} | {rule} | `{t}` — SQLite: {results.get(t, 'not run')}; SQL Server: {results2.get(t, 'not run' if results2 else '—')} |")
    lines += ["", "### Supporting tests not mapped to a specific requirement", "", "<details><summary>show list</summary>", ""] + [f"* `{t}`" for t in orphans] + ["", "</details>", ""]
    (ROOT / "docs/validation/rtm.md").write_text("\n".join(lines), encoding="utf-8")
    return len(REQS), len(mapped), len(orphans)


# ---------------------------------------------------------------------------------------------------- code-derived configuration
def seeded_session():
    from app.audit import hooks
    from app.audit.context import AuditContext, audit_context
    from app.core import db
    from app.core.db import Base
    import app.models  # noqa: F401
    tmp = tempfile.mkdtemp()
    db.configure(f"sqlite:///{tmp}/docs.db")
    hooks.install()
    Base.metadata.create_all(db.get_engine())
    from app.services import seed
    s = db.new_session()
    with audit_context(AuditContext(user_name="DOCGEN", reason="documentation generation")):
        seed.seed_baseline(s)
        s.commit()
    return s


def gen_configuration(s) -> None:
    from sqlalchemy import select
    from app.models import NumberRegistry, Permission, Role, RolePermission, SodRule, SystemConfiguration, WorkflowDefinition, WorkflowStep
    roles = s.execute(select(Role).order_by(Role.role_code)).scalars().all()
    perms = {p.id: p for p in s.execute(select(Permission)).scalars()}
    rp = collections.defaultdict(set)
    for r in s.execute(select(RolePermission)).scalars():
        rp[r.role_id].add(perms[r.permission_id].perm_code)
    L = ["# Configuration Specification (CS)", "", f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} from a freshly seeded database (`seed_baseline`). This is the *as-delivered* configuration; the site documents its own changes through change control.", "",
         "## 1. Roles", "", "| Role | Name | Admin role | Permissions |", "|---|---|---|---|"]
    for r in roles:
        L.append(f"| {r.role_code} | {r.name} | {'yes' if r.is_admin_role else 'no'} | {len(rp[r.id])} |")
    L += ["", f"Permission catalogue: **{len(perms)}** permission codes across **{len({p.module for p in perms.values()})}** modules.", "", "## 2. Segregation-of-duties rules", "",
          "| ID | Action | Conflicts with (same record) | Enforcement | Description |", "|---|---|---|---|---|"]
    for r in s.execute(select(SodRule).order_by(SodRule.sod_id)).scalars():
        L.append(f"| {r.sod_id} | `{r.action_code}` | `{r.conflicts_with_action_code}` | {r.enforcement} | {r.description or ''} |")
    L += ["", "## 3. Approval workflows (baseline)", ""]
    for d in s.execute(select(WorkflowDefinition).order_by(WorkflowDefinition.process_code)).scalars():
        L += [f"**{d.process_code}** — {d.name} (v{d.version_no}, {d.status})", "", "| Step | Name | Role | E-signature | Meaning | SLA h |", "|---|---|---|---|---|---|"]
        for st in s.execute(select(WorkflowStep, Role.role_code).join(Role, Role.id == WorkflowStep.role_id).where(WorkflowStep.definition_id == d.id).order_by(WorkflowStep.seq)).all():
            w, rc = st
            L.append(f"| {w.seq} | {w.name} | {rc} | {'yes' if w.esig_required else 'no'} | {w.meaning} | {w.sla_hours} |")
        L.append("")
    L += ["## 4. Numbering registry", "", "| Document type | Prefix | Reset | Format |", "|---|---|---|---|"]
    for n in s.execute(select(NumberRegistry).order_by(NumberRegistry.doc_type)).scalars():
        L.append(f"| {n.doc_type} | {n.prefix} | {n.reset_policy} | `{n.format}` |")
    L += ["", "## 5. System configuration keys (defaults)", "", "| Key | Default | Meaning |", "|---|---|---|"]
    from app.services.config_service import DEFAULTS
    for k, (v, d) in sorted(DEFAULTS.items()):
        L.append(f"| `{k}` | `{v}` | {d} |")
    L += ["", "## 6. Retention policy defaults", "", "| Record type | Years | Basis |", "|---|---|---|"]
    from app.services.retention import SOURCES
    for k, (label, _m, _c, years, basis) in SOURCES.items():
        L.append(f"| {label} (`{k}`) | {years} | {basis} |")
    L += ["", "## 7. Environment settings", "", "See `docs/manuals/configuration.md` and `.env.example` (all `MERP_*` variables, secure defaults, production fail-fast checks).", ""]
    (ROOT / "docs/validation/configuration-specification.md").write_text("\n".join(L), encoding="utf-8")
    # access control matrix
    mods = sorted({p.module for p in perms.values()})
    ABBR = {"create": "C", "read": "R", "update": "U", "approve": "A", "delete": "D", "submit": "S", "release": "Rel", "export": "X", "sign": "Sg"}
    L = ["# Access-Control Matrix", "", "Role × module. Letters per module: the actions the role holds (full action names for non-obvious ones). The automated protocol `tests/security/test_access_matrix.py` verifies **every API route × every role** against the live permission catalogue (", f"{len(perms)} permissions).", ""]
    L += ["| Module | " + " | ".join(r.role_code for r in roles) + " |", "|---|" + "---|" * len(roles)]
    for m in mods:
        row = []
        for r in roles:
            mine = sorted({p.perm_code.split(".")[-1] for p in perms.values() if p.module == m and p.perm_code in rp[r.id]})
            row.append(", ".join(ABBR.get(a, a) for a in mine) or "—")
        L.append(f"| {m} | " + " | ".join(row) + " |")
    (ROOT / "docs/validation/access-control-matrix.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def gen_data_dictionary() -> None:
    from app.core.db import Base
    import app.models  # noqa: F401
    by_mod = collections.defaultdict(list)
    table_mod = {}
    for m in Base.registry.mappers:
        mod = m.class_.__module__.split(".")[-1]
        t = m.local_table
        table_mod[t.name] = mod
    for t in Base.metadata.sorted_tables:
        by_mod[table_mod.get(t.name, "other")].append(t)
    L = ["# Data Dictionary", "", f"Generated from the SQLAlchemy metadata on {datetime.now(timezone.utc).strftime('%Y-%m-%d')} — **{len(Base.metadata.tables)} tables**. Append-only tables are protected by database triggers (`app/audit/immutability.py`).", ""]
    from app.audit.immutability import APPEND_ONLY_TABLES
    for mod in sorted(by_mod):
        L += [f"## Module `{mod}`", ""]
        for t in sorted(by_mod[mod], key=lambda x: x.name):
            ao = " — **append-only**" if t.name in APPEND_ONLY_TABLES else ""
            L += [f"### `{t.name}`{ao}", "", "| Column | Type | Null | Key / default | Notes |", "|---|---|---|---|---|"]
            for c in t.columns:
                key = []
                if c.primary_key:
                    key.append("PK")
                for fk in c.foreign_keys:
                    key.append(f"FK → {fk.column.table.name}.{fk.column.name}")
                if c.default is not None and getattr(c.default, "arg", None) is not None and not callable(c.default.arg):
                    key.append(f"default {c.default.arg}")
                typ = str(c.type).split("(")[0] if "UTCDateTime" not in str(type(c.type)) else "DATETIME (UTC)"
                L.append(f"| {c.name} | {c.type if 'UTC' not in str(type(c.type)) else typ} | {'yes' if c.nullable else 'no'} | {'; '.join(key)} | {c.comment or ''} |")
            cons = [f"{type(c).__name__}: {c.name or ''} {str(getattr(c, 'sqltext', '')) if hasattr(c, 'sqltext') else ''}".strip() for c in t.constraints if type(c).__name__ in ("UniqueConstraint", "CheckConstraint")]
            if cons:
                L += ["", "Constraints: " + "; ".join(f"`{x}`" for x in cons)]
            L.append("")
    (ROOT / "docs/architecture/12-data-dictionary.md").write_text("\n".join(L), encoding="utf-8")
    # ER diagrams per module
    L = ["# ER Diagrams", "", "Foreign-key relationships per module (Mermaid). Cross-module references are shown as dashed groups by naming the foreign table.", ""]
    for mod in sorted(by_mod):
        L += [f"## {mod}", "", "```mermaid", "erDiagram"]
        shown = set()
        for t in sorted(by_mod[mod], key=lambda x: x.name):
            for c in t.columns:
                for fk in c.foreign_keys:
                    ft = fk.column.table.name
                    edge = (ft, t.name, c.name)
                    if edge in shown:
                        continue
                    shown.add(edge)
                    L.append(f'  {ft} ||--o{{ {t.name} : "{c.name}"')
        for t in sorted(by_mod[mod], key=lambda x: x.name):
            if not any(t.name in e[:2] for e in shown):
                L.append(f"  {t.name} {{ int id }}")
        L += ["```", ""]
    (ROOT / "docs/architecture/13-er-diagram.md").write_text("\n".join(L), encoding="utf-8")


def gen_sbom() -> None:
    """Software bill of materials: backend runtime closure (installed versions) and frontend production dependencies (package-lock)."""
    import json
    import re
    from importlib import metadata
    req = [re.split(r"[<>=!~\[; ]", l.strip())[0] for l in (ROOT / "backend/requirements.txt").read_text().splitlines() if l.strip() and not l.startswith(("#", "-"))]
    seen: dict[str, str] = {}
    todo = [r.lower().replace("_", "-") for r in req]
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        try:
            d = metadata.distribution(n)
        except metadata.PackageNotFoundError:
            continue
        seen[n] = d.version
        for r in d.requires or []:
            if "extra ==" in r:
                continue
            todo.append(re.split(r"[<>=!~\[; ]", r.strip())[0].lower().replace("_", "-"))
    L = ["# Software Bill of Materials (SBOM)", "", f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} by `scripts/gen_validation_docs.py`. Use with `pip-audit` / `npm audit` for vulnerability review (SEC-04).", "",
         "## Backend (Python) — runtime dependency closure", "", "| Package | Version | License |", "|---|---|---|"]
    for n in sorted(seen):
        d = metadata.distribution(n)
        lic = (d.metadata.get("License-Expression") or d.metadata.get("License") or "").split("\n")[0][:40] or next((c.split("::")[-1].strip() for c in d.metadata.get_all("Classifier") or [] if c.startswith("License ::")), "")
        L.append(f"| {n} | {seen[n]} | {lic} |")
    lock = ROOT / "frontend/package-lock.json"
    L += ["", "## Frontend (npm) — production dependencies", "", "| Package | Version |", "|---|---|"]
    if lock.exists():
        pk = json.loads(lock.read_text()).get("packages", {})
        rows = sorted((k.split("node_modules/")[-1], v.get("version", "")) for k, v in pk.items() if k and not v.get("dev"))
        L += [f"| {n} | {v} |" for n, v in rows]
    L += ["", "## Runtime and tooling", "", "* Python 3.11+, Node 18+ (build only), SQL Server 2019/2022 + ODBC Driver 18, optional PostgreSQL 14+, Caddy 2 (reverse proxy sample).",
          "* Build/test tooling (not deployed): pytest, vite, TypeScript, Playwright (UI smoke tests), locust (optional).", ""]
    (ROOT / "docs/validation/sbom.md").write_text("\n".join(L), encoding="utf-8")


def gen_openapi() -> None:
    """Committed copy of the API contract (docs/api/openapi.json) so reviewers can diff API changes between releases."""
    import json
    from app.main import create_app
    spec = create_app(configure_db=False).openapi()
    (ROOT / "docs/api").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/api/openapi.json").write_text(json.dumps(spec, indent=1, sort_keys=True), encoding="utf-8")
    (ROOT / "docs/api/README.md").write_text(f"# API contract\n\n`openapi.json` — OpenAPI 3 export of all **{sum(len(v) for v in spec['paths'].values())} operations** on **{len(spec['paths'])} paths**, regenerated by `scripts/gen_validation_docs.py`. Interactive docs are served at `/api/docs` on non-production systems.\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", default=str(ROOT / "docs/validation/evidence/junit.xml"))
    ap.add_argument("--junit-mssql", nargs="*", default=sorted(str(x) for x in (ROOT / "docs/validation/evidence").glob("junit-sqlserver-*.xml")))
    ap.add_argument("--skip-collect", action="store_true")
    a = ap.parse_args()
    collected = collect_tests()
    results = read_junit(Path(a.junit))
    for extra in sorted((ROOT / "docs/validation/evidence").glob("junit-sqlite-*.xml")):      # later targeted re-runs override
        results.update(read_junit(extra))
    results2: dict[str, str] = {}
    for f in a.junit_mssql:
        results2.update(read_junit(Path(f)))
    n, mapped, orphans = gen_urs_rtm(collected, results, results2)
    s = seeded_session()
    gen_configuration(s)
    gen_data_dictionary()
    gen_sbom()
    gen_openapi()
    print(f"URS {n} requirements; {mapped} mapped tests; {orphans} supporting tests; {len(collected)} collected; results for {len(results)} tests")


if __name__ == "__main__":
    main()
