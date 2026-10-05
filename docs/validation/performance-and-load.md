# Performance and Load Test Notes

## Targets (from the validation strategy)
50 concurrent users; 100 000+ ledger/audit rows; interactive response (p95 < 3 s for lists/dashboards/search); no errors under load; report exports complete in a minute.

## Tooling
* `scripts/load_test.py` — dependency-light (threads + httpx) weighted task mix (dashboard, lists, search, report preview/export, trace, notifications, audit page) with per-endpoint p50/p95/p99 and error rate; exit code 1 on slow endpoints or > 1 % errors.
* `tests/performance/locustfile.py` — the same profile for Locust (optional) for longer or distributed runs.
* `tests/workflows/test_reports.py::test_report_performance_with_large_ledger` — automated smoke test: 5 000 ledger rows, preview/CSV/XLSX time limits.

## Supplier run (development evidence — NOT the site's PQ)
| Item | Value |
|---|---|
| Database | SQL Server 2022 (Docker, same host), migrations 0001–0009, demo data (`database/seeds/demo_data.py`) |
| Application | uvicorn, **2 worker processes**, pool 25 + 35 overflow per worker |
| Load | 50 virtual users for 120 s, 4 786 requests (**39.6 req/s**), 0 login failures, **0 % errors** |
| Host | Single shared container (application, SQL Server and the load generator on one machine) — therefore latencies are pessimistic |

| Endpoint | n | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|
| audit trail page | 253 | 620 | 1 274 | 1 681 |
| dashboard summary | 1 228 | 1 088 | 1 633 | 1 883 |
| global search | 479 | 976 | 1 642 | 2 070 |
| list batches | 337 | 688 | 1 150 | 1 323 |
| list deviations | 340 | 691 | 1 264 | 1 523 |
| list lots | 495 | 1 141 | 1 940 | 2 153 |
| list stock | 452 | 1 222 | 2 055 | 2 432 |
| list vendors | 352 | 602 | 1 052 | 1 251 |
| notifications | 233 | 542 | 961 | 1 226 |
| report: stock status | 385 | 754 | 1 348 | 1 582 |
| report: ledger XLSX export | 117 | 745 | 1 850 | 1 991 |
| trace lot | 115 | 1 224 | 2 289 | 2 565 |

All p95 values were below 3 s. Raw output: `evidence/load-test-sqlserver.txt`.

## Findings from the load runs (all fixed in this release)
1. **Simultaneous logins of one account failed with 409** (`CONCURRENT_MODIFICATION`: optimistic `row_version` on the user row). 40 of 50 logins failed in the first run. Fix: login bookkeeping (counters, last login, session revocation) uses core `UPDATE`s; regression test `test_concurrent_logins_of_the_same_account_do_not_conflict` (server databases).
2. **Connection-pool starvation** (`QueuePool limit of size 10 overflow 20 reached`) with 50 active users produced 60 s time-outs. Fix: pool size/overflow/timeout are settings (`MERP_DB_POOL_SIZE` 25, `MERP_DB_MAX_OVERFLOW` 35, `MERP_DB_POOL_TIMEOUT` 30); guidance: `pool_size + overflow ≥ worker threads (40)`.
3. Out-of-range numeric identifiers (e.g. `/lots/99999999999999999999`) caused a 500 — now 422 (found by the hardening tests).

## What the site must still do (PQ-P1…P4)
Repeat on production-class hardware with a **separate** database server, ≥ 100 000 ledger/audit rows, 10-minute run, and record results in the PQ protocol. Expect lower latency than the single-host figures above; if the report exports on the large dataset exceed targets, schedule them outside peak hours or restrict date ranges.

## Capacity notes
* Stateless application: scale by adding workers/instances behind the reverse proxy.
* The audit-chain head is a single row lock: audit writes serialise; keep transactions short (they are — one user action per transaction).
* `inventory_transaction` and `audit_trail` grow monotonically; plan storage and index maintenance; use the retention/archive tooling for reporting extracts rather than deleting.
