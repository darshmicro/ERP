# Backup / Restore Qualification

**Objective:** show that a backup of the production database can be restored to a separate database, that the restored data is complete, that the **audit-trail hash chain verifies on the restored copy**, and that the recovery time meets the site's RTO. Re-run at least every 180 days (the backup status page alerts otherwise) and after any change to the backup tooling.

## Procedure (automated by `scripts/restore_test.py`)
1. Connect with an **administrative** login (BACKUP/RESTORE rights) via `MERP_MIGRATION_DATABASE_URL` — never the application login.
2. `BACKUP DATABASE … WITH CHECKSUM, COMPRESSION` → `RESTORE VERIFYONLY … WITH CHECKSUM`.
3. `RESTORE DATABASE <db>_restore_test … WITH MOVE …, REPLACE` into a scratch database (`RESTORE FILELISTONLY` provides the logical files).
4. Compare the row count of **every table** between source and restored copy.
5. Run the audit-trail HMAC chain verification against the restored copy (the HMAC key in force when the rows were written must be configured).
6. Record elapsed time (RTO evidence), drop the scratch database, print a JSON evidence record; optionally POST it to `/api/v1/backup/records` as a `RESTORE_TEST` entry (append-only, shown on the backup status page).
7. Document-store check (manual): restore the document directory to a scratch location; open three documents through the application's download (hash verification must pass — `BR-DOC-001`).

## Site protocol
| # | Step | Expected | Actual | P/F |
|---|---|---|---|---|
| BR-01 | Run `scripts/restore_test.py` on the validation environment with production-like data | Exit code 0; `result: SUCCESS` | | |
| BR-02 | `count_differences` | `{}` | | |
| BR-03 | `audit_chain_restored.ok` | `true`, `checked` = number of audit rows | | |
| BR-04 | `restore_seconds` / `elapsed_seconds_total` | within the site RTO (record both) | | |
| BR-05 | Backup page shows the restore test (type RESTORE_TEST, chain verified, RTO) and no alerts | | | |
| BR-06 | Negative test: corrupt a copy of the backup file and run `RESTORE VERIFYONLY` | Fails (CHECKSUM) | | |
| BR-07 | Document-store restore and three hash-verified downloads | OK | | |
| BR-08 | Point-in-time recovery drill (full + log restore to a given time) per DR plan | Data as of the time; hash chain valid up to that time | | |

## Supplier development evidence (SQL Server 2022 in Docker, 2026-10-05)
See `evidence/restore-test-sqlserver.json` (produced by the script against a database loaded with the demo data, migrations 0001–0009): backup with CHECKSUM, VERIFYONLY OK, restore to a scratch database, all table counts equal, audit chain verified on the restored copy. This is developer evidence, not a substitute for the site's qualification on its own infrastructure.
