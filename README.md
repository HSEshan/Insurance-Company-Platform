# Insurance Management Platform

Full-stack insurance back-office app for quoting, underwriting, policies, claims,
billing, documents, and compliance.

**Core tech:** FastAPI · React · PostgreSQL · Redis · MinIO · Docker

**Live demo:** _coming soon_ — placeholder link

**Tests:** backend **108/108** · Playwright E2E **9/9** · frontend typecheck + build clean

---

## Overview

InsureCo is a working insurance management platform used to practice and present
common carrier workflows: rate → quote → bind, endorsements, claims adjudication,
premium schedules, document handling, audit logging, and role-based access.

It is designed to be easy to run locally with Docker Compose and seeded demo
accounts for each role (customer, agent, adjuster, manager, super admin).

## Features

| Area | What you can try |
|---|---|
| Auth & RBAC | Customer self-register; staff created by Super Admin; JWT + refresh |
| Quotes & rating | Auto / home / life quotes with itemized premium factors |
| Policies | Bind, endorse, cancel, reinstate; schedules and documents |
| Claims | Submit → investigate → approve/reject → payout; fraud scoring |
| Billing | Premium installments, payments, overdue / lapse jobs |
| Documents | MinIO uploads + generated PDFs (policy / decision letters) |
| Notifications | In-app bell + email via MailHog locally |
| Reporting & audit | Manager KPIs, CSV exports, queryable audit log |
| Staff admin | Invite, role changes, deactivate with reassignment guards |
| Live chat | FAQ assistant + simulated handoff (landing + customer dashboard) |

## Tech stack

| Layer | Choices |
|---|---|
| API | FastAPI, async SQLAlchemy 2.0, Alembic, Pydantic |
| Auth / security | PyJWT, bcrypt, Fernet PII encryption, RBAC deps |
| Data | PostgreSQL 16, Redis |
| Jobs | Celery worker + beat |
| Files | MinIO (S3-compatible) |
| Frontend | React 19, TypeScript, Vite, Tailwind 4, TanStack Query, Zustand |
| Quality | Ruff, pytest, `tsc`, Playwright |
| Ops | Docker Compose, GitHub Actions CI, Nginx (SPA + reverse-proxy example) |

## Project structure

```
backend/          FastAPI app (models → schemas → services → api)
frontend/         React SPA (+ Playwright e2e/)
deploy/nginx/     Production reverse-proxy example
docker-compose.yml
```

## Quick start

```bash
docker compose up --build -d
docker compose exec backend python -m scripts.seed
```

| Service | URL |
|---|---|
| App | http://localhost:5173 |
| API docs | http://localhost:8000/api/docs |
| MailHog | http://localhost:8025 |
| MinIO console | http://localhost:9001 (`minioadmin` / `minioadmin`) |

### Demo accounts (after seed)

| Role | Email | Password |
|---|---|---|
| Super Admin | admin@insureco.com | Admin123! |
| Manager | manager@insureco.com | Manager123! |
| Agent | agent@insureco.com | Agent123! |
| Adjuster | adjuster@insureco.com | Adjuster123! |
| Customer | customer@insureco.com | Customer123! |

The landing page also offers one-click demo logins when `DEMO_MODE_ENABLED=true`.

### Local (without Compose for app code)

Backend needs Postgres + Redis (Compose or your own). Then:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## Testing

```bash
# Backend
cd backend
.venv\Scripts\ruff.exe check app scripts alembic tests   # Windows
.venv\Scripts\python.exe -m pytest -q

# Frontend
cd frontend
npm run typecheck
npm run build

# Playwright (stack must be up + seeded)
cd frontend
npx playwright install chromium   # first time
npm run test:e2e
```

Playwright covers landing, auth (form + demo login), customer policies/claims
navigation, staff customers/quotes/reports/audit, and the chat launcher — smoke
paths against the running demo, not every workflow edge case.

## Production notes

- SPA image uses [`frontend/nginx.conf`](./frontend/nginx.conf) (gzip, SPA fallback, security headers).
- VPS deploy helpers: [`docker-compose.prod.yml`](./docker-compose.prod.yml), [`deploy/nginx/insureco.conf.example`](./deploy/nginx/insureco.conf.example), [`backend/.env.production.example`](./backend/.env.production.example).
- Turn off demo surfaces for a locked-down deploy: `DEMO_MODE_ENABLED=false`, `CHAT_WIDGET_ENABLED=false`, and rotate `SECRET_KEY` / `ENCRYPTION_KEY`.

## Docs

- [`specs.md`](./specs.md) — domain model, APIs, phases
- [`timeline.md`](./timeline.md) — what was built and why
- [`AGENTS.md`](./AGENTS.md) — coding conventions
