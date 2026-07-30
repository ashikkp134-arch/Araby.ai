# AI Coding Workspace

Production-oriented AI coding platform with isolated JavaScript, Python, and Website Builder workspaces. Users authenticate, manage multi-file projects, edit code in Monaco, and chat with an OpenAI-powered assistant that can read and modify project files.

## Architecture

```text
AI-Coding-Workspace/
├── backend/             # FastAPI + Motor + Redis + AI pipeline (+ Dockerfile)
├── frontend/            # React + Vite + nginx production image (+ Dockerfile)
├── docker-compose.yml   # Mongo + Redis + backend + frontend
└── README.md
```

### Backend flow

```text
Router → Service → Repository → MongoDB
```

### AI pipeline

```text
Router → Request Router (light vs coding) → Workspace System Prompt
      → Context Builder → LLM (stream/complete) → Response Parser → File Modifier
```

Hybrid routing uses `OPENAI_MODEL_LIGHT` (default `gpt-4o-mini`) for explanations/docs
and `OPENAI_MODEL_CODING` (default `gpt-4o`) for website generation, multi-file edits,
and automatic preview repairs. Both fall back to `OPENAI_MODEL` when explicitly left
empty. Chat streams over `/ws/chat/{project_id}` with structured
```file path=… action=…``` blocks applied automatically.

## Prerequisites

- Docker + Docker Compose (recommended for one-command production run)
- **Or** for local dev: Python 3.12, Node.js 20+, MongoDB 7, Redis 7
- OpenAI API key

> On older Linux hosts (glibc < 2.32), the frontend is pinned to Vite 4 for compatibility.

## Production run (single Docker command)

### 0. Install Docker (Ubuntu) — only if `docker` is missing

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker "$USER"
# Log out/in (or run: newgrp docker) so group membership applies
docker --version
docker-compose --version
```

Prefer the Compose V2 plugin if available (`docker compose` without hyphen). Both work with this repo.

### 1. Configure backend secrets

```bash
cd ~/araby_codeai
cp backend/.env.example backend/.env
# Edit backend/.env — set at least:
#   OPENAI_API_KEY=sk-...
#   JWT_SECRET=<32+ random chars>
#   JWT_REFRESH_SECRET=<32+ different random chars>
```

Compose overrides `MONGO_URI` / `REDIS_URL` to use Docker service names automatically.

### 2. Build and start everything

```bash
docker compose up -d --build
# If that fails on older installs:
# docker-compose up -d --build
```

This starts **MongoDB + Redis + Phoenix (traces) + FastAPI backend + nginx frontend**.

### 3. Open the app

- App: [http://localhost](http://localhost)/3000/
- API health: [http://localhost/health](http://localhost/health)
- Phoenix traces: https://app.phoenix.arize.com/s/AI-Coding-Workspace

### Useful commands

```bash
docker compose ps
docker compose logs -f
docker compose down          # stop
docker compose down -v       # stop + wipe DB volumes
```

## Local development (without containerising the app)

### 1. Infrastructure only

```bash
docker compose up -d mongodb redis phoenix
```

### 2. Backend

```bash
cd backend
cp .env.example .env
# Edit .env and set OPENAI_API_KEY, JWT secrets, etc.

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

App: [http://localhost:5173](http://localhost:5173)

## Environment variables

### Backend (`backend/.env`)

| Variable | Description |
| --- | --- |
| `MONGO_URI` | MongoDB connection URI |
| `DATABASE_NAME` | MongoDB database name |
| `REDIS_URL` | Redis connection URL |
| `JWT_SECRET` | Access token signing secret (min 32 chars) |
| `JWT_REFRESH_SECRET` | Refresh token signing secret (min 32 chars) |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Default / fallback model (default `gpt-4o-mini`) |
| `OPENAI_MODEL_LIGHT` | Fast model for explanations/docs (default `gpt-4o-mini`) |
| `OPENAI_MODEL_CODING` | Stronger model for website generation, edits, and preview repair (default `gpt-4o`) |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible base URL (empty = OpenAI) |
| `LLM_PROVIDER` | Provider key (`openai`, stubs for others) |
| `ACCESS_TOKEN_EXPIRE` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE` | Refresh token lifetime in minutes |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `OTEL_ENABLED` | Enable OpenTelemetry + OpenInference tracing (default `true`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP traces URL (Phoenix: `http://localhost:6006/v1/traces`) |
| `OTEL_SERVICE_NAME` | Service name in traces |
| `GUARDRAILS_ENABLED` | Run LLM input/output guardrails (default `true`) |
| `GUARDRAILS_BLOCK_ON_INPUT` | Block prompt-injection style inputs |
| `GUARDRAILS_BLOCK_ON_OUTPUT` | Block unsafe model output / file applies |

### Frontend (`frontend/.env`)

| Variable | Description |
| --- | --- |
| `VITE_API_BASE_URL` | Leave empty to use the Vite `/api` proxy (recommended). Absolute URLs can break refresh cookies across `localhost` vs `127.0.0.1`. |

## API overview

All REST endpoints are versioned under `/api/v1` and return:

```json
{
  "success": true,
  "message": "",
  "data": {},
  "error": null
}
```

| Area | Prefix |
| --- | --- |
| Auth | `/api/v1/auth` |
| Projects | `/api/v1/projects` |
| Files | `/api/v1/files` |
| Chat | `/api/v1/chat` |
| Workspaces | `/api/v1/workspaces` |
| AI stream | `/ws/chat/{project_id}` |

Authentication uses JWT access tokens (in-memory on the client) plus HTTP-only refresh cookies with rotation. Passwords are bcrypt hashed. JWT blacklist and rate limits use Redis.

## Features

- Signup / login with secure sessions
- Three workspaces: JavaScript, Python, Website Builder
- Nested folders and multi-file projects persisted in MongoDB
- Monaco editor with tabs, autosave, and manual save
- Project-scoped AI chat with context-aware file edits
- Website Builder live preview (HTML/CSS/JS + Tailwind CDN)
- Provider abstraction for OpenAI 
- Isolated evaluation harness scaffolding 

## Security notes

- Never commit `.env` files
- Access tokens are not stored in `localStorage`
- Users can only access their own projects
- Filenames and paths are sanitized against traversal

https://github.com/ashikkp134-arch/Araby.ai/blob/main/Demo/python-ws.mp4

## Development tips

- Backend working directory must be `backend/` so `app.main:app` resolves
- Use Python 3.12 (`pyenv local 3.12.3` if needed)
- Refresh tokens are rotated on `/api/v1/auth/refresh`
- AI file edits use fenced blocks:

````text
```file path=index.html action=update
...contents...
```
````
