-- GMP-MERP SQL Server least-privilege setup (run once by a DBA; review before use).
-- Replace passwords via your secret store; do NOT commit real values.
-- Accounts: merp_migrator (DDL, used only at deployment), merp_app (runtime DML), merp_report_ro (reporting).
-- No account used by the application holds db_owner.

CREATE LOGIN merp_migrator WITH PASSWORD = '<<SET-SECRET>>', CHECK_POLICY = ON;
CREATE LOGIN merp_app      WITH PASSWORD = '<<SET-SECRET>>', CHECK_POLICY = ON;
CREATE LOGIN merp_report_ro WITH PASSWORD = '<<SET-SECRET>>', CHECK_POLICY = ON;
GO
USE MERP;
CREATE USER merp_migrator FOR LOGIN merp_migrator;
CREATE USER merp_app FOR LOGIN merp_app;
CREATE USER merp_report_ro FOR LOGIN merp_report_ro;
ALTER ROLE db_ddladmin ADD MEMBER merp_migrator;
ALTER ROLE db_datareader ADD MEMBER merp_migrator;
ALTER ROLE db_datawriter ADD MEMBER merp_migrator;
GRANT ALTER ANY SCHEMA TO merp_migrator;   -- needed for triggers created by migrations
GO
-- Run AFTER `alembic upgrade head`:
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO merp_app;   -- baseline for mutable tables
-- Append-only GMP tables: INSERT + SELECT only (defence in depth; triggers also block UPDATE/DELETE)
DENY UPDATE, DELETE ON dbo.audit_trail        TO merp_app;
DENY UPDATE, DELETE ON dbo.e_signature        TO merp_app;
DENY UPDATE, DELETE ON dbo.security_event     TO merp_app;
DENY UPDATE, DELETE ON dbo.gmp_status_history TO merp_app;
DENY UPDATE, DELETE ON dbo.record_action      TO merp_app;
DENY UPDATE, DELETE ON dbo.workflow_transaction TO merp_app;
DENY ALTER ANY SCHEMA TO merp_app; DENY CREATE TABLE TO merp_app;
-- audit_chain_head must stay updatable (hash-chain head); it is intentionally NOT denied.
-- Reporting account: read-only
GRANT SELECT ON SCHEMA::dbo TO merp_report_ro;
DENY SELECT ON dbo.users(password_hash) TO merp_report_ro;
DENY SELECT ON dbo.password_history TO merp_report_ro;
DENY SELECT ON dbo.user_session TO merp_report_ro;
GO
