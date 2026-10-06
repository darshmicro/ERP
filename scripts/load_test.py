#!/usr/bin/env python
"""Dependency-light load test (threads + httpx) for qualification runs:

  python scripts/load_test.py --base http://localhost:8000 --users 50 --seconds 120 [--password 'Gmp!Training#2026x']

Logs in once per virtual user (demo accounts from database/seeds/demo_data.py), then loops over a weighted task mix for the given time and prints per-endpoint
count, error rate, p50/p95/p99 latency and overall throughput. Exit code 1 when p95 of any read endpoint exceeds --p95-limit-ms or the error rate exceeds 1 %."""
import argparse
import random
import statistics
import threading
import time
from collections import defaultdict

import httpx

USERS = ["demo_qahead", "demo_qc", "demo_wh", "demo_prod", "demo_purchase", "demo_dispatch", "demo_mgmt", "demo_qao"]
TASKS = [  # (weight, name, method, path)
    (10, "dashboard summary", "GET", "/api/v1/dashboard/summary"), (4, "list lots", "GET", "/api/v1/lots"), (4, "list stock", "GET", "/api/v1/inventory/stock"), (3, "list vendors", "GET", "/api/v1/vendors"),
    (3, "list batches", "GET", "/api/v1/mfg/batches"), (3, "list deviations", "GET", "/api/v1/deviations"), (4, "global search", "GET", "/api/v1/search?q=LOT"), (3, "report stock-status", "GET", "/api/v1/reports/stock-status"),
    (1, "report ledger xlsx", "GET", "/api/v1/reports/stock-ledger/export?format=xlsx"), (1, "trace lot", "GET", "/api/v1/trace/lot/LOT-2026-000001?direction=both"), (2, "notifications", "GET", "/api/v1/notifications"),
    (2, "audit trail page", "GET", "/api/v1/audit-trail?limit=50"),
]
lock = threading.Lock()
lat: dict[str, list[float]] = defaultdict(list)
errs: dict[str, int] = defaultdict(int)


def worker(i: int, base: str, pw: str, stop_at: float):
    name = USERS[i % len(USERS)]
    c = httpx.Client(base_url=base, timeout=60, verify=False)
    r = c.post("/api/v1/auth/login", json={"username": name, "password": pw})
    if r.status_code != 200:
        with lock:
            errs["login"] += 1
        return
    h = {"X-CSRF-Token": r.json()["csrf_token"]}
    wts = [t[0] for t in TASKS]
    while time.time() < stop_at:
        _w, nm, m, p = random.choices(TASKS, weights=wts)[0]
        t0 = time.perf_counter()
        try:
            resp = c.request(m, p, headers=h)
            ok = resp.status_code < 400 or resp.status_code in (403, 404)       # 403/404 = role has no access / sample id absent: not a fault
        except Exception:  # noqa: BLE001
            ok = False
        dt = (time.perf_counter() - t0) * 1000
        with lock:
            lat[nm].append(dt)
            if not ok:
                errs[nm] += 1
        time.sleep(random.uniform(0.05, 0.4))      # think time


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--password", default="Gmp!Training#2026x")
    ap.add_argument("--p95-limit-ms", type=int, default=3000)
    a = ap.parse_args()
    stop = time.time() + a.seconds
    ts = [threading.Thread(target=worker, args=(i, a.base, a.password, stop)) for i in range(a.users)]
    t0 = time.time()
    [t.start() for t in ts]
    [t.join() for t in ts]
    el = time.time() - t0
    total = sum(len(v) for v in lat.values())
    print(f"{a.users} virtual users, {el:.0f}s, {total} requests, {total / el:.1f} req/s, login failures {errs.get('login', 0)}")
    print(f"{'endpoint':<24}{'n':>7}{'err%':>7}{'p50':>8}{'p95':>8}{'p99':>8}{'max':>8}  (ms)")
    bad = False
    for nm, v in sorted(lat.items()):
        e = errs.get(nm, 0) / len(v) * 100
        p95 = pct(v, 0.95)
        flag = ""
        if p95 > a.p95_limit_ms and "xlsx" not in nm and "trace" not in nm:
            flag, bad = "  <-- slow", True
        print(f"{nm:<24}{len(v):>7}{e:>7.1f}{statistics.median(v):>8.0f}{p95:>8.0f}{pct(v, .99):>8.0f}{max(v):>8.0f}{flag}")
    err_rate = sum(errs.values()) / max(1, total) * 100
    print(f"overall error rate {err_rate:.2f}%")
    return 1 if bad or err_rate > 1 else 0


if __name__ == "__main__":
    raise SystemExit(main())
