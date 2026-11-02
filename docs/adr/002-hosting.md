# ADR 002 — Hosting Strategy & Staging Deployment Infrastructure

- **Status**: Accepted
- **Date**: 2026-10-29
- **Proposer**: Le Hong Dang (DevOps)
- **Related**: Issue #18, ADR 001, APP_SPECIFICATION sections 6.3 & 13

## Context

The Pathly Study Companion project requires an operational staging environment that satisfies the course objectives:

1. **Zero-Cost ($0 Free Tier)**: Suitable for academic coursework and team prototyping without incurring recurring infrastructure expenses.
2. **Continuous Deployment (CD)**: Automatically triggered upon merging Pull Requests into the `main` branch (deployment turnaround < 10 minutes).
3. **Isolation and Security**: Sensitive operational secrets (`DATABASE_URL`, `JWT_SECRET`, `LLM_API_KEY`) must reside securely on cloud service provider dashboards, never committed to Git.
4. **Decoupled Architecture**:
   - Frontend: Single Page Application (SPA) built with React, Vite, and TypeScript.
   - Backend: RESTful API built with FastAPI (Python 3.11) backed by PostgreSQL 16.

## Decision

### 1. Deployment Architecture

The team has agreed on a decoupled staging infrastructure comprising three independent tiers:

```text
[ User / Browser ]
        │
        ├─────────────────────────────┐
        ▼                             ▼
  [ Frontend UI ]              [ Backend API ]
   Vercel (Edge CDN)            Render / Railway (Docker)
        │                             │
        │ API Requests                ▼
        └──────────────────────► [ Database ]
                                  PostgreSQL 16 (Managed)
```

1. **Frontend UI -> Vercel**:
   - Native optimization for Vite/React SPA.
   - Automatic builds from the `ui/` subdirectory with build command `npm run build` and output directory `dist/`.
   - Offers preview deployments per Pull Request and free automated TLS certificates.

2. **Backend API -> Render (or Railway / Fly.io)**:
   - Built directly from the standardized `Dockerfile` created in Issue #18.
   - Native health-check support targeting `/api/v1/health`.
   - Secure environment variable injection and automatic deploy triggers on `main` branch merges.

3. **Database -> Managed PostgreSQL 16 (Render / Supabase / Neon)**:
   - PostgreSQL 16 guarantees 100% parity with Alembic migrations and the canonical schema (inheriting ADR 001).
   - Secure connection strings injected via `DATABASE_URL` using the modern `postgresql+psycopg://...` driver.

---

### 2. Alternatives Considered

| Component | Selected Platform | Alternative Considered | Rationale for Rejection |
| --- | --- | --- | --- |
| **Frontend** | **Vercel** | Netlify, GitHub Pages | GitHub Pages requires hacky workarounds for client-side routing fallbacks; Netlify is capable, but Vercel offers faster Vite build caching and seamless GitHub integration. |
| **Backend** | **Render (Docker)** | AWS EC2 / Lightsail | Raw EC2 instances require manual system administration (OS patching, reverse proxy Nginx configuration, Certbot SSL rotation), increasing operational overhead and risks of unexpected billing. |
| **Database** | **Render Postgres / Neon** | Self-hosted Postgres on VM | Self-hosting database instances introduces data loss risks, lacks automated managed backups, and demands database administrator maintenance. |

---

## Security & Architectural Constraints

1. **Secret Management**:
   - All production/staging credentials (`DATABASE_URL`, `JWT_SECRET`, `LLM_API_KEY`) must only be configured on the hosting dashboard.
   - Local `.env` files are strictly excluded from version control and verified in CI via `python dev.py db scan-secrets`.
2. **CORS Restrictions**:
   - The backend `CORS_ORIGINS` variable is restricted to the Vercel staging domain (e.g. `https://group04-study.vercel.app`) alongside local development origins.
3. **Non-Root Execution**:
   - The backend container runs under an unprivileged user `appuser` (UID 1000) to adhere to container security best practices.

---

## Consequences & Trade-offs

- **Positive**:
  - Fully functional, zero-cost ($0) end-to-end staging pipeline.
  - Complete automation from commit to deployment on both frontend and backend.
  - Clear separation of concerns allowing the UI and API to be evolved and released independently.
- **Negative (Free Tier Limitations)**:
  - Free-tier web services on Render spin down after 15 minutes of inactivity. Initial wake-up requests (Cold Start) can take 30–50 seconds.
  - *Mitigation*: Acceptable for staging/evaluation purposes; `docs/DEPLOYMENT.md` documents procedures for pre-warming instances before grading presentations.
