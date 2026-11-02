# Deployment Runbook & Operating Guide

This runbook establishes standard operating procedures for the CS252 Group 04 project team and evaluators: from spinning up local development via Docker Compose to staging deployments on the cloud.

---

## 1. Service & Port Matrix

### Local Environment

| Service | Technology | Host Port | Verification Endpoint (Health check / URL) | Notes |
| --- | --- | --- | --- | --- |
| **API Backend** | FastAPI (Python 3.11) | `8000` | `http://127.0.0.1:8000/api/v1/health` | OpenAPI docs available at `/docs` |
| **Database** | PostgreSQL 16 | `5432` | `docker compose ps` (`healthy`) | Persistent volume `pgdata` |
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
5. Set **Health Check Path**: `/api/v1/health`.
6. Click **Create Web Service**. Render builds the image, executes database migrations, and exposes an endpoint such as `https://study-companion-api.onrender.com`.

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
