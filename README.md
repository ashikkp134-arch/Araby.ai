# AI Coding Workspace

Production-oriented AI coding platform with isolated JavaScript, Python, and Website Builder workspaces. Users authenticate, manage multi-file projects, edit code in Monaco, and chat with an OpenAI-powered assistant that can read and modify project files.

## Architecture

```text
AI-Coding-Workspace/
├── backend/          # FastAPI + Motor + Redis + AI pipeline
├── frontend/         # React + Vite + TypeScript + Tailwind
├── docker-compose.yml
└── README.md
```

### Backend flow

```text
Router → Service → Repository → MongoDB
```

### AI pipeline

```text
Router → AI Service → Prompt Builder → Context Builder → LLM Provider → Response Parser → File Modifier
```

## Prerequisites

- Python 3.12
- Node.js 20+
- MongoDB 7
- Redis 7
- OpenAI API key

> Tip: Prefer `docker compose up -d` for MongoDB and Redis. On older Linux hosts (glibc < 2.32), the frontend is pinned to Vite 4 for compatibility.

## Quick start

### 1. Infrastructure

```bash
docker compose up -d
```

This starts MongoDB on `27017` and Redis on `6379`.

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
| `OPENAI_MODEL` | Model name (default `gpt-4o-mini`) |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible base URL (empty = OpenAI) |
| `LLM_PROVIDER` | Provider key (`openai`, stubs for others) |
| `ACCESS_TOKEN_EXPIRE` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE` | Refresh token lifetime in minutes |
| `CORS_ORIGINS` | Comma-separated allowed origins |

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
- Provider abstraction for OpenAI (Anthropic/Gemini/Ollama/Azure stubs)
- Isolated evaluation harness scaffolding (RAGAS/DeepEval-ready)

## Security notes

- Never commit `.env` files
- Access tokens are not stored in `localStorage`
- Users can only access their own projects
- Filenames and paths are sanitized against traversal

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
