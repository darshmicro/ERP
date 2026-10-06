# Software Bill of Materials (SBOM)

Generated 2026-10-05 by `scripts/gen_validation_docs.py`. Use with `pip-audit` / `npm audit` for vulnerability review (SEC-04).

## Backend (Python) — runtime dependency closure

| Package | Version | License |
|---|---|---|
| alembic | 1.20.0 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.7.0 | MIT License |
| anyio | 4.14.1 | MIT |
| argon2-cffi | 25.1.0 | MIT |
| argon2-cffi-bindings | 26.1.0 | MIT |
| cffi | 2.1.0 | MIT-0 |
| charset-normalizer | 3.4.9 | MIT |
| click | 8.4.2 | BSD-3-Clause |
| colorama | 0.4.6 | BSD License |
| et-xmlfile | 2.0.0 | MIT |
| fastapi | 0.142.2 | MIT |
| h11 | 0.16.0 | MIT |
| idna | 3.18 | BSD-3-Clause |
| ldap3 | 2.9.1 | LGPL v3 |
| mako | 1.4.3 | MIT |
| markupsafe | 3.0.3 | BSD-3-Clause |
| openpyxl | 3.1.5 | MIT |
| opentelemetry-api | 1.45.0 | Apache-2.0 |
| pillow | 12.3.0 | MIT-CMU |
| pyasn1 | 0.6.4 | BSD-2-Clause |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| pydantic-core | 2.46.4 | MIT |
| pydantic-settings | 2.14.2 | MIT |
| pyodbc | 5.3.0 | MIT |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| reportlab | 5.0.1 | BSD license (see license.txt for details |
| sqlalchemy | 2.1.3 | MIT |
| starlette | 1.3.1 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.2 | MIT |
| uvicorn | 0.50.2 | BSD-3-Clause |

## Frontend (npm) — production dependencies

| Package | Version |
|---|---|
| @popperjs/core | 2.11.8 |
| @remix-run/router | 1.23.4 |
| bootstrap | 5.3.8 |
| bootstrap-icons | 1.13.1 |
| js-tokens | 4.0.0 |
| loose-envify | 1.4.0 |
| react | 18.3.1 |
| react-dom | 18.3.1 |
| react-router | 6.30.6 |
| react-router-dom | 6.30.6 |
| scheduler | 0.23.2 |

## Runtime and tooling

* Python 3.11+, Node 18+ (build only), SQL Server 2019/2022 + ODBC Driver 18, optional PostgreSQL 14+, Caddy 2 (reverse proxy sample).
* Build/test tooling (not deployed): pytest, vite, TypeScript, Playwright (UI smoke tests), locust (optional).
