# Deployment Runbook & Operating Guide

This runbook establishes standard operating procedures for the CS252 Group 04 project team and evaluators: from spinning up local development via Docker Compose to staging deployments on the cloud.

---

## 1. Service & Port Matrix

### Local Environment

| Service | Technology | Host Port | Verification Endpoint (Health check / URL) | Notes |
| --- | --- | --- | --- | --- |
| **API Backend** | FastAPI (Python 3.11) | `8000` | `http://127.0.0.1:8000/api/v1/health` | OpenAPI docs available at `/docs` |
| **Database** | PostgreSQL 16 | `5432` | `docker compose ps` (`healthy`) | Persistent volume `pgdata` |
| **Worker** | Python (same image as the API) | — | `docker compose logs worker` (`worker started`) | Runs background jobs; starts after the API is healthy (migrations applied) |
| **UI Frontend** | Vite + React + TS | `5173` | `http://127.0.0.1:5173` | Node.js dev server |

---

## 2. Local Runbook (Docker Compose)

### Prerequisites

- **Docker Desktop** installed and running.
- **Git** installed.

### A. Starting Services (Daily Workflow)

#### 🖥️ For PowerShell (Windows)

```powershell
# 1. Build images and start containers in detached mode
docker compose up --build -d

# 2. Check container status
docker compose ps

# 3. Verify backend health
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/health
```

#### 🐧 For Git Bash / macOS / Linux

```bash
# 1. Build images and start containers in detached mode
docker compose up --build -d

# 2. Check container status
docker compose ps

# 3. Verify backend health
curl -s http://127.0.0.1:8000/api/v1/health
```

*Expected Output:* Status `200 OK` with JSON payload:

```json
{"status": "ok", "ai_provider": "offline"}
```

---

### B. Troubleshooting & Logs

- **Inspect Backend API logs in real-time**:
  - PowerShell / Bash: `docker logs -f study_api`
- **Inspect background worker logs** (jobs, daily link check):
  - PowerShell / Bash: `docker compose logs -f worker`
- **Inspect queued and failed jobs**:
  - PowerShell / Bash: `docker compose exec db psql -U study_user -d study -c "select kind, status, attempts, error from jobs order by created_at desc limit 20;"`
- **Inspect PostgreSQL Database logs**:
  - PowerShell / Bash: `docker logs -f study_db`
- **Run Alembic migrations manually (if needed)**:
  - PowerShell / Bash: `docker compose exec api alembic upgrade head`

---

### C. Stopping Services

- Stop containers while **preserving database data**:

  ```bash
  docker compose down
  ```

- Stop containers and **wipe database clean** (reset volume):

  ```bash
  docker compose down -v
  ```

---

## 3. Staging Deployment Guide (Cloud)

In accordance with **ADR 002**, the staging infrastructure decouples frontend hosting on **Vercel** and backend services on **Render** (or Railway).

```text
          [ GitHub Repo: Rokieroo/Group04-CS252-VirtualAssistant ]
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
        [ Vercel (Frontend) ]                   [ Render (Backend API) ]
        - Root: `ui`                            - Docker Environment
        - Env: VITE_API_BASE_URL                - Env: DATABASE_URL, JWT_SECRET
```

### Step 1: Deploy PostgreSQL Managed Database

1. Navigate to the [Render Dashboard](https://dashboard.render.com).
2. Create: **New +** -> **PostgreSQL**.
3. Configuration:
   - **Name**: `study-companion-db`
   - **Database**: `study`
   - **User**: `study_user`
   - **Plan**: `Free`
4. Once provisioned, copy the **Internal Database URL** (or External URL if connecting remotely).

---

### Step 2: Deploy Backend API on Render

1. On Render Dashboard: **New +** -> **Web Service**.
2. Connect repository: `Rokieroo/Group04-CS252-VirtualAssistant`.
3. Configuration:
   - **Name**: `study-companion-api`
   - **Runtime**: **Docker** (Render automatically picks up the root `Dockerfile`).
   - **Branch**: `main`
   - **Instance Type**: `Free`
4. Configure **Environment Variables** (Secret - never commit to Git):
   - `DATABASE_URL`: Connection string from Step 1 (must use `postgresql+psycopg://...`).
   - `CORS_ORIGINS`: `https://<your-vercel-app>.vercel.app,http://localhost:5173`
   - `JWT_SECRET`: Random 32+ character secure secret string.
   - `LLM_PROVIDER`: `gemini` (or `fake` for mock responses).
   - `LLM_API_KEY`: Google Gemini API Key.
   - `YOUTUBE_API_KEY`: YouTube Data API key for the resource finder (optional; empty disables the provider).
   - `SEARCH_API_KEY`: Web search provider key for the resource finder (optional; empty disables the provider).
5. Set **Health Check Path**: `/api/v1/health`.
6. Click **Create Web Service**. Render builds the image, executes database migrations, and exposes an endpoint such as `https://study-companion-api.onrender.com`.

### Step 2b: Deploy the Background Worker on Render

Slow work (syllabus parsing, resource search) and the daily link check run in the worker, never inside an HTTP request. The queue is the `jobs` table in the same database, so there is no broker to provision.

1. On Render Dashboard: **New +** -> **Background Worker**, same repository and branch, **Runtime: Docker**.
2. **Docker Command**: `python -m assistant.backend.worker`.
3. **Environment Variables**: the same values as the API (at least `DATABASE_URL`, plus `LLM_*`, `YOUTUBE_API_KEY`, `SEARCH_API_KEY`). An Environment Group shared by both services keeps them in one place.
4. Deploy the API first: it applies migrations, the worker does not.
5. Scale by adding instances; workers claim jobs atomically, and the daily link check is enqueued once per day however many run.

---

### Step 3: Deploy Frontend on Vercel

1. Navigate to the [Vercel Dashboard](https://vercel.com).
2. Click **Add New...** -> **Project** -> Select `Rokieroo/Group04-CS252-VirtualAssistant`.
3. Project Configuration:
   - **Framework Preset**: `Vite`
   - **Root Directory**: Click `Edit` and select **`ui`**
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Environment Variables:
   - `VITE_API_BASE_URL`: The backend URL created in Step 2 (e.g., `https://study-companion-api.onrender.com`).
5. Click **Deploy**. Vercel provisions a production domain: `https://<project-name>.vercel.app`.

---

### Step 4: Verification & Smoke Testing

1. Test API health: `curl https://<api-service>.onrender.com/api/v1/health` should return `200 OK`.
2. Access the frontend URL on browser: Verify registration, login flow, and course creation.
3. Validate Continuous Deployment: Merging a PR into `main` automatically updates both frontend and backend within 10 minutes.

### Step 5: Cost & Quota Dashboard (admins)

Every resource search the worker runs (job `search_resources`) is logged: one `resource_searches` row per node search (queries, candidates, kept sources, LLM and search cost, duration) and one `search_runs` row per provider call (latency, cost). Admins read it at `GET /api/v1/admin/costs?days=7`, or in the app at `https://<frontend>/#costs`.

1. Promote an operator once (SQL console of the staging database):
   ```sql
   UPDATE users SET role = 'admin' WHERE email = '<operator email>';
   ```
2. Sign in as that user and open `#costs`. Other users get `403 admin_only`.
3. Watch `LLM calls today` against the Gemini free tier (about 20 requests per model per day) and each provider's `Today` column against its quota.
