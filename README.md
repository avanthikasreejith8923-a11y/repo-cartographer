# repo-cartographer

> **AI Developer Productivity Platform**: Connect GitHub repositories, analyze commits, PRs, and issues, and answer questions about the codebase using RAG with citations.

---

## 🗺️ Architecture Overview

```mermaid
graph TD
    Client[Browser Client] <-->|Port 5173 / Cookies| Frontend[React + TypeScript + Vite]
    Frontend <-->|Port 8000 / Reverse Proxy| Backend[FastAPI + SQLAlchemy 2.0 Async]
    
    subgraph Infrastructure
        Backend <-->|Port 5432| DB[(PostgreSQL 16 + pgvector)]
        Backend <-->|Port 6379| Redis[(Redis 7 Cache / Queue)]
        Backend <-->|HTTPS OAuth| GitHub[(GitHub API)]
    end
```

---

## 🚀 Phase Checklist

- [x] **Phase 1: Foundation + GitHub OAuth** (Current)
  - Monorepo structure with FastAPI, React Vite TS, and Docker Compose
  - PostgreSQL 16 with `pgvector` extension and initial Alembic migration
  - Secure GitHub OAuth 2.0 web application flow with Fernet token encryption at rest
  - Signed CSRF state verification and `httpOnly`, `SameSite=Lax` session management
  - Health check endpoint (`/health`) validating DB and Redis connectivity
  - Pytest async suite with Respx mocks and Ruff linting in GitHub Actions CI
- [ ] **Phase 2: Repository Ingestion & ARQ Worker**
  - Redis-backed ARQ worker pool for background task processing
  - GitHub repo connection, commit history parsing, PR and issue metadata ingestion
- [ ] **Phase 3: AST Parsing & Codebase Graph Construction**
  - AST analysis and symbol relationship extraction (classes, functions, imports)
  - Codebase dependency and knowledge graph generation
- [ ] **Phase 4: Embeddings & pgvector Storage**
  - Chunking strategies for source code and metadata
  - Vector embedding generation and pgvector similarity index setup
- [ ] **Phase 5: Hybrid RAG Engine with Citations**
  - Graph + vector hybrid retrieval pipeline
  - LLM synthesis answering architectural questions with exact file and line citations
- [ ] **Phase 6: Interactive Cartographer UI**
  - Codebase graph visualization
  - Interactive copilot chat interface with deep-linked citations

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and configure the following variables:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | string | `development` | Runtime environment (`development`, `production`, `test`) |
| `DEBUG` | boolean | `true` | Enable debug logs and interactive FastAPI `/docs` |
| `BACKEND_HOST` | string | `0.0.0.0` | Bind host for FastAPI server |
| `BACKEND_PORT` | integer | `8000` | Port for FastAPI backend |
| `FRONTEND_URL` | string | `http://localhost:5173` | Public frontend URL for OAuth redirects |
| `CORS_ORIGINS` | JSON list | `["http://localhost:5173"]` | Allowed origins for CORS with credentials |
| `SECRET_KEY` | string | *required* | Secret key for signing session JWTs and OAuth states |
| `FERNET_KEY` | string | *required* | 32-byte base64 Fernet key to encrypt GitHub tokens at rest |
| `ALGORITHM` | string | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | integer | `10080` (7 days) | Session duration in minutes |
| `SESSION_COOKIE_NAME` | string | `rc_session` | Name of the session JWT cookie |
| `OAUTH_STATE_COOKIE_NAME` | string | `rc_oauth_state` | Name of the short-lived signed state cookie |
| `POSTGRES_USER` | string | `postgres` | PostgreSQL username |
| `POSTGRES_PASSWORD` | string | `postgres` | PostgreSQL password |
| `POSTGRES_DB` | string | `repo_cartographer` | Database name |
| `POSTGRES_HOST` | string | `postgres` | Database host (or `localhost` for local dev) |
| `POSTGRES_PORT` | integer | `5432` | Database port |
| `DATABASE_URL` | string | *derived* | Full asyncpg connection string |
| `REDIS_HOST` | string | `redis` | Redis host |
| `REDIS_PORT` | integer | `6379` | Redis port |
| `REDIS_URL` | string | `redis://redis:6379/0` | Redis connection URL |
| `GITHUB_CLIENT_ID` | string | *required* | GitHub OAuth App Client ID |
| `GITHUB_CLIENT_SECRET` | string | *required* | GitHub OAuth App Client Secret |
| `GITHUB_REDIRECT_URI` | string | `http://localhost:8000/auth/github/callback` | OAuth redirect URI configured in GitHub |

---

## 🛠️ Local Quickstart with Docker Compose

### 1. Prerequisites
- Docker Engine & Docker Compose (or Docker Desktop)
- A GitHub OAuth App configured at [GitHub Developer Settings](https://github.com/settings/developers) with:
  - **Homepage URL**: `http://localhost:5173`
  - **Authorization callback URL**: `http://localhost:8000/auth/github/callback`

### 2. Configure Environment
```bash
# Copy template and fill in your GitHub OAuth App credentials
cp .env.example .env
```

To generate a new Fernet encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Start Services
```bash
docker compose up --build
```

The services will initialize:
- **Frontend**: [http://localhost:5173](http://localhost:5173)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL (pgvector)**: `localhost:5432`
- **Redis**: `localhost:6379`

Alembic migrations run automatically on container startup to enable the `vector` extension and create the `users` table.

---

## 💻 Manual Local Development (Without Docker)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run Alembic migrations (requires Postgres running locally)
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Testing & Linting

### Running Backend Tests
```bash
cd backend
pytest -v
```

### Running Linter
```bash
cd backend
ruff check .
```

### Running Frontend Build Verification
```bash
cd frontend
npm run build
```
