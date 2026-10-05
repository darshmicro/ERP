# SQL Server verification record (development environment, 2026-10-05)

Executed against **SQL Server 2022 (RTM-CU27) in Docker**, ODBC Driver 18, pyodbc. This is *developer* evidence, not a substitute for your IQ/OQ on the target server.

| Check | Result |
|---|---|
| `alembic upgrade head` → `downgrade base` → `upgrade head` on empty database | Pass (50 tables incl. `alembic_version`) |
| Append-only `INSTEAD OF UPDATE, DELETE` triggers created on 6 tables | Pass (verified in `sys.triggers`) |
| Full automated suite on SQL Server (`MERP_TEST_DATABASE_URL`) | **89 passed** (the 2 SQLite-subprocess migration tests deselected; migrations verified manually above) — 9 min 37 s |
| Least-privilege script: `merp_app` can INSERT into `audit_trail`; UPDATE/DELETE → *permission denied*; `CREATE TABLE` → *permission denied* | Pass |

## Defects found by this verification (all fixed)
1. `column IS 0` boolean predicates are invalid T-SQL → use `== false()/true()`.
2. Column named `rule` is a T-SQL reserved word → renamed `sampling_rule`.
3. `DATETIME` rounds to 1/300 s, which broke audit **hash-chain verification** → all UTC columns are `DATETIME2(6)` on SQL Server.
4. `audit_chain_head.id` became an IDENTITY column → `autoincrement=False`.

## How to repeat
`docker compose -f docker/docker-compose.test.yml up -d`, then run pytest with `MERP_TEST_DATABASE_URL` (see compose file). The fixture rolls back leaked sessions and recreates the schema before each test (≈6 s/test on a laptop).
Not yet covered: concurrency/lock behaviour under load, PostgreSQL, TDE/backup tooling.

## Update — Phase 3 (2026-10-05)
Full suite on SQL Server 2022: **115 passed** (Phase 3 included); migrations 0001→0003 up/down/up on a clean database (55 tables). Tests that build a full purchasing "world" take 30–60 s each on SQL Server; for CI use a pre-seeded template database.
**Design note found while testing:** security events and failed-login counters are written in an *independent* transaction. If the request transaction already holds locks when that write happens, SQLite blocks (and SQL Server could wait on contended rows). Rule adopted: **perform authentication / SoD / gate checks before any write in a request** (applied in PO approval and cancellation).
