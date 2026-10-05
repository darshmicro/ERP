"""Locust load profile (optional; `pip install locust`).  Run against a deployed test instance loaded with database/seeds/demo_data.py:

    locust -f tests/performance/locustfile.py --host https://merp.test.local --users 50 --spawn-rate 5 --run-time 10m --headless

Task mix reflects an operating day: mostly lookups and lists, regular reports, occasional controlled writes."""
import random

from locust import HttpUser, between, task

USERS = ["demo_qahead", "demo_qc", "demo_wh", "demo_prod", "demo_purchase", "demo_dispatch", "demo_mgmt", "demo_qao"]
PASSWORD = "Gmp!Training#2026x"          # demo password; override via LOCUST_PASSWORD for a real test system


class MerpUser(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        self.name = random.choice(USERS)
        r = self.client.post("/api/v1/auth/login", json={"username": self.name, "password": PASSWORD}, name="login")
        self.h = {"X-CSRF-Token": r.json().get("csrf_token", "")}

    @task(10)
    def dashboards(self):
        self.client.get("/api/v1/dashboard/summary", name="dashboard summary")

    @task(8)
    def lists(self):
        for p in ("/api/v1/lots", "/api/v1/inventory/stock", "/api/v1/vendors", "/api/v1/mfg/batches", "/api/v1/deviations"):
            self.client.get(p, name="list " + p.split("/")[-1])

    @task(4)
    def search(self):
        self.client.get("/api/v1/search?q=LOT", name="global search")

    @task(3)
    def report_preview(self):
        self.client.get("/api/v1/reports/stock-status", name="report stock-status")

    @task(1)
    def report_export(self):
        self.client.get("/api/v1/reports/stock-ledger/export?format=xlsx", name="export ledger xlsx")

    @task(1)
    def trace(self):
        self.client.get("/api/v1/trace/lot/LOT-2026-000001?direction=both", name="trace lot")
