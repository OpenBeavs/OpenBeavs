# CLAUDE.md — OpenBeavs (GENESIS-AI-Hub)

> **For AI coding assistants (Claude Code, Copilot, Cursor, etc.):**
> Read this entire file before touching any code. This is the authoritative
> reference for architecture, conventions, and required patterns. PRs that
> violate these rules will be rejected.

---

## 1. Project Identity

| Field       | Value                                                       |
|-------------|-------------------------------------------------------------|
| **Name**    | GENESIS-AI-Hub / OpenBeavs                                  |
| **Team**    | Oregon State University CS Capstone — Team #043             |
| **Sponsor** | John V. Sweet (john.sweet@oregonstate.edu)                  |
| **GitHub**  | [github.com/OpenBeavs](https://github.com/OpenBeavs/)       |
| **Stack**   | SvelteKit 2 + FastAPI + Google Cloud Run                    |

**Mission:** A decentralized platform for discovering, registering, and
communicating with AI agents via the **A2A (Agent-to-Agent) protocol** — JSON-RPC
2.0 over HTTP with `/.well-known/agent.json` discovery cards.

---

## 2. Repository Layout

```
GENESIS-AI-Hub/
├── back/                        # Lightweight prototype FastAPI backend (in-memory)
│   ├── main.py                  # Routes, models, JSON-RPC handler
│   ├── requirements.txt
│   └── tests/
│
├── front/                       # PRIMARY application (Open WebUI fork)
│   ├── backend/                 # Production Python backend (SQLite/Peewee)
│   │   └── open_webui/
│   │       ├── main.py          # FastAPI app entrypoint
│   │       ├── config.py        # All environment variable config
│   │       ├── env.py           # Env var loading
│   │       ├── routers/         # 27+ API route handlers
│   │       ├── models/          # Peewee ORM models + Pydantic schemas
│   │       ├── utils/           # Auth helpers, misc utilities
│   │       ├── migrations/      # Alembic DB migrations
│   │       └── retrieval/       # RAG / vector search
│   └── src/                     # SvelteKit frontend
│       └── lib/
│           └── components/workspace/
│               ├── Agents.svelte   # Agent registry UI
│               └── ...
│
├── agents/                      # Standalone deployable ADK agents
│   ├── Cyrano-de-Bergerac/
│   ├── oregon-state-expert/
│   ├── oregon-state-scraper/
│   └── weather-expert-agent/
│
├── docs/                        # Architecture docs and ADRs
├── .github/
│   ├── pull_request_template.md
│   └── workflows/               # CI/CD GitHub Actions
├── Dockerfile                   # Unified multi-stage build
├── cloudbuild.yaml              # GCP Cloud Build pipeline
├── deploy.sh                    # Manual deployment helper
└── Makefile                     # Docker convenience commands
```

> **Critical distinction:** `back/` is a prototype. All new feature work belongs
> in the production backend at `front/backend/open_webui/`.

---

## 3. Tech Stack

### Frontend (`front/src/`)
| Concern     | Technology                              |
|-------------|-----------------------------------------|
| Framework   | SvelteKit 2, Svelte 4                   |
| Language    | TypeScript 5 (strict — no untyped JS)  |
| Styling     | Tailwind CSS 4 / scoped `<style>`       |
| Build       | Vite 5                                  |
| Lint/Format | ESLint + Prettier                       |
| State       | Svelte stores                           |

### Production Backend (`front/backend/open_webui/`)
| Concern          | Technology                              |
|------------------|-----------------------------------------|
| Framework        | FastAPI (async)                         |
| Language         | Python 3.11+ with full type hints       |
| ORM              | Peewee (SQLite)                         |
| Schema/Validation| Pydantic v2 (`BaseModel`)               |
| Auth             | JWT via `open_webui.utils.auth`         |
| Lint/Format      | Ruff                                    |
| Web Server       | Uvicorn                                 |
| Migrations       | Alembic                                 |

### Prototype Backend (`back/`)
| Concern     | Technology                        |
|-------------|-----------------------------------|
| Framework   | FastAPI                           |
| Storage     | In-memory Python dicts            |
| JSON-RPC    | `jsonrpcserver` library           |

### Standalone Agents (`agents/`)
| Concern     | Technology                                    |
|-------------|-----------------------------------------------|
| Framework   | Google Agent Development Kit (ADK)            |
| Protocol    | A2A — JSON-RPC 2.0                            |
| Models      | Google Gemini (via `GEMINI_API_KEY`)           |
| Serving     | Uvicorn on per-agent ports                    |

### Infrastructure
| Concern   | Technology                      |
|-----------|---------------------------------|
| Cloud     | Google Cloud Platform (GCP)     |
| Compute   | Google Cloud Run                |
| Build     | Cloud Build (`cloudbuild.yaml`) |
| Auth      | Azure MSAL (Microsoft SSO)      |
| Containers| Docker                          |

---

## 4. Local Development

### Production Backend
```bash
cd front/
pip install -r backend/requirements.txt

# Run dev server (port 8080)
PORT=8080 uvicorn open_webui.main:app \
  --port 8080 --host 0.0.0.0 \
  --forwarded-allow-ips "*" --reload

# Or via the helper script
bash backend/dev.sh
```

### Prototype Backend
```bash
cd back/
pip install -r requirements.txt
uvicorn main:app --reload   # http://localhost:8000
```

### Frontend
```bash
cd front/
npm install
npm run pyodide:fetch       # one-time: download WASM Python runtime
npm run dev                 # http://localhost:5173
```

### Docker (full stack)
```bash
make install   # docker-compose up -d
make start     # start existing containers
make stop      # stop containers
```

---

## 5. The A2A Protocol

A2A is the core of this project. Every agent — including the hub — must comply.

### Discovery Card (`/.well-known/agent.json`)
```json
{
  "name": "My Agent",
  "description": "What this agent does",
  "url": "https://myagent.example.com",
  "version": "1.0.0",
  "capabilities": { "streaming": true },
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    {
      "id": "skill_id",
      "name": "Skill Name",
      "description": "What this skill does",
      "tags": ["tag1"],
      "examples": ["example query"]
    }
  ]
}
```

### Message Format (JSON-RPC 2.0 over HTTP POST)
```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "messageId": "<uuid>",
      "role": "user",
      "parts": [{ "text": "Hello agent", "type": "text" }]
    }
  },
  "id": 1
}
```

The hub routes these in:
- `front/backend/open_webui/routers/agents.py` → `send_message_to_agent()`
- `back/main.py` → `generate_agent_response()`

> **Gotcha:** When registering by URL, `agents.py` may receive the full
> `/.well-known/agent.json` URL directly, while `back/main.py` appends the path
> automatically. Be aware of this inconsistency when modifying registration logic.

---

## 6. Key API Routers

All under `front/backend/open_webui/routers/`:

| File           | Prefix           | Purpose                              |
|----------------|------------------|--------------------------------------|
| `agents.py`    | `/api/agents`    | Local agent CRUD + A2A message relay |
| `registry.py`  | `/api/registry`  | Public registry: submit/update/delete|
| `auths.py`     | `/api/auths`     | Authentication (MS SSO, local)       |
| `chats.py`     | `/api/chats`     | Chat thread management               |
| `models.py`    | `/api/models`    | LLM model listing                    |
| `tickets.py`   | `/api/tickets`   | Support tickets                      |
| `knowledge.py` | `/api/knowledge` | RAG knowledge base management        |
| `ollama.py`    | `/api/ollama`    | Ollama model proxy                   |
| `openai.py`    | `/api/openai`    | OpenAI-compatible API proxy          |

---

## 7. Required Backend Patterns

### Authentication (every endpoint)
```python
from open_webui.utils.auth import get_admin_user, get_verified_user

@router.get("/my-endpoint")
async def my_endpoint(user=Depends(get_verified_user)):
    ...

# Admin-only
@router.delete("/{id}")
async def delete(id: str, user=Depends(get_admin_user)):
    ...
```

### Ownership check (all mutating operations)
```python
if user.role != "admin" and resource.user_id != user.id:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=ERROR_MESSAGES.UNAUTHORIZED,
    )
```

### Error handling
```python
from open_webui.constants import ERROR_MESSAGES

raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT())
raise HTTPException(status_code=401, detail=ERROR_MESSAGES.UNAUTHORIZED)
```

### Well-formed route (full example)
```python
@router.post("/register", response_model=AgentModel)
async def register_agent(
    form_data: RegisterAgentForm,
    user=Depends(get_verified_user),
) -> AgentModel:
    """Register a new A2A agent manually."""
    agent_id = str(uuid.uuid4())
    agent = Agents.insert_new_agent(id=agent_id, user_id=user.id, ...)
    if agent:
        return agent
    raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT())
```

---

## 8. Database Models

Custom models added on top of the Open WebUI base — in
`front/backend/open_webui/models/`:

| File          | Key Classes                                                        | Table Purpose              |
|---------------|--------------------------------------------------------------------|----------------------------|
| `agents.py`   | `AgentModel`, `AgentResponse`, `RegisterAgentForm`, `Agents`       | Locally installed agents   |
| `registry.py` | `RegistryAgentModel`, `SubmitRegistryAgentForm`, `RegistryAgents`  | Public agent registry      |
| `tickets.py`  | `TicketModel`, `Tickets`                                           | Support ticket system      |

**Key `AgentModel` fields:**
- `id` (UUID str), `name`, `description`
- `endpoint` — A2A JSON-RPC POST URL ← use this for message routing
- `url` — base homepage URL (fallback when `endpoint` is absent)
- `version`, `capabilities` (dict), `skills` (list)
- `default_input_modes`, `default_output_modes`
- `profile_image_url`, `user_id`, `is_active`, `created_at`

> **Registry vs Agents:** `registry` = public discovery showcase. `agents` =
> installed-and-active agents within a specific hub instance.

---

## 9. Code Conventions

### Python
- **Always** add type hints on all parameters and return types.
- **Always** add docstrings to every route function and class method.
- Use **Pydantic v2** — `.model_dump()` not `.dict()` (deprecated).
- Use **Ruff** for lint and format — not Black or isort.
- Use `uuid.uuid4()` for ID generation; IDs are always `str`.
- Import order: stdlib → third-party → local (`open_webui.*`).
- **Never** use `print()` — use the `logging` module.
- **Never** hardcode secrets — load from env via `open_webui.config`.

### TypeScript / Svelte
- Strict TypeScript — no untyped JS in `.svelte` or `.ts` files.
- Use **Svelte stores** for shared state — no deep prop-drilling.
- Component filenames are **PascalCase** (e.g., `MyComponent.svelte`).
- API calls go through `$lib/apis/` — do not call `fetch()` directly in components.
- No inline styles — use CSS classes or scoped `<style>` blocks.
- Run `npm run lint` before every commit.

---

## 10. Linting & Formatting

### Frontend (from `front/`)
```bash
npm run lint            # ESLint + type check + backend lint
npm run lint:frontend   # ESLint only
npm run format          # Prettier
```

Prettier config: **tabs**, **single quotes**, **100-char width**, no trailing commas.

### Backend (Python)
```bash
ruff check .    # lint
ruff format     # format
```

---

## 11. Testing

### Backend
```bash
cd back/ && pytest tests/ -v
# or
cd front/ && pytest backend/open_webui/test/ -v
```

### Frontend
```bash
cd front/
npm run test:frontend   # Vitest unit tests
npm run cy:open         # Cypress E2E (interactive)
```

All new API routes must have unit tests. All PRs must pass all tests before merge.

---

## 12. Commit Messages (Conventional Commits)

Format: `<type>(<scope>): <subject ≤50 chars, imperative>`

| Type        | When to Use                                   |
|-------------|-----------------------------------------------|
| `feat`      | New user-facing feature                       |
| `fix`       | Bug fix                                       |
| `chore`     | Build, deps, tooling — no production change   |
| `docs`      | Documentation only                            |
| `style`     | Formatting, whitespace — no logic change      |
| `refactor`  | Restructure without fixing or adding features |

**Examples:**
```
feat(agents): add A2A message relay endpoint
fix(registry): handle duplicate agent URL on registration
chore(deps): update fastapi to 0.111.0
docs(readme): add Docker quickstart section
```

To close a GitHub issue, add `Closes #<number>` in the commit body/footer.

---

## 13. Git Workflow & PR Rules

- **Branching:** GitFlow — branch off `main` for every feature or fix.
- **Branch names:** `kebab-case`, descriptive — e.g., `feature/agent-card-ui`, `bugfix/registry-404`.
- **PR template:** Mandatory — use `.github/pull_request_template.md`.
  Must include: Description, Related Issues, Testing Notes, Screenshots (for UI).
- **PR size:** Target ≤ 400–500 lines of diff. Break large work into smaller PRs.
- **Approval:** 1 team-member approval required. You cannot approve your own PR.
- **Status checks:** All unit tests + linter must pass before merge.
- **Merge strategy:** Merge commits by default; rebase only for large upstream syncs.
- **After merge:** Delete the feature branch.
- **Versioning:** SemVer (`MAJOR.MINOR.PATCH`). Tag every production deployment.

---

## 14. CI/CD Pipeline

Merging to `main` auto-triggers `cloudbuild.yaml` on GCP:

1. **Pull cache** — pulls `openbeavs-frontend:latest` from Artifact Registry.
2. **Unified build** — compiles SvelteKit frontend + bundles Python backend into
   one Docker image.
3. **Push** — tags image with commit SHA + `latest`, pushes to Artifact Registry
   (`us-west1`).
4. **Deploy** — rolls out to Cloud Run service `openbeavs-deploy-test`
   (us-west1, 4 CPU / 8 GiB RAM).

For rollbacks, use the Cloud Run revisions dashboard in the GCP Console.

### Manual Deploy
```bash
gcloud auth login
gcloud auth configure-docker
./deploy.sh   # reads GCP_PROJECT_ID and GCP_REGION from .env
```

---

## 15. Environment Variables

| Variable               | Purpose                                    |
|------------------------|--------------------------------------------|
| `DATABASE_URL`         | SQLite/PostgreSQL connection string        |
| `SECRET_KEY`           | JWT signing key                            |
| `GEMINI_API_KEY`       | Gemini model access (agents + hub)         |
| `CHRIS_MODEL`          | Gemini model ID for Cyrano's Chris agent   |
| `CYRANO_MODEL`         | Gemini model ID for Cyrano agent           |
| `PORT`                 | Backend server port (default: `8080`)      |
| `OPENAI_API_KEY`       | Optional OpenAI proxy support              |
| `OLLAMA_BASE_URL`      | Optional Ollama proxy support              |

Full list: `front/backend/open_webui/config.py` and `env.py`.

**Security rules (non-negotiable):**
- Never commit `.env` files — they are gitignored.
- Use `.env.example` in agent directories to document required vars.
- In production, use GCP Secret Manager.
- Run `npm audit` at the start of every sprint.

---

## 16. Standalone Agents (`agents/`)

Each agent is independently deployable and must comply with A2A.

### Adding a New Agent
1. Create `agents/<agent-name>/` with: `agent.py`, `requirements.txt`,
   `.env.example`, `README.md`.
2. Expose `/.well-known/agent.json` for discovery.
3. Register with the hub: `POST /api/agents/register-by-url`.

### Cyrano de Bergerac (example multi-agent pipeline)
```bash
uvicorn orchestrator.agent:a2a_app --host localhost --port 8001
# Verify: http://localhost:8001/.well-known/agent-card.json
```
Pipeline: **chris** (tone analysis) → **cyrano** (eloquent response) via `SequentialAgent`.

---

## 17. Common Gotchas

1. **Two backends.** `back/main.py` = prototype. Production = `front/backend/open_webui/`. New work goes in the production backend.

2. **`agents/` vs local agents.** `agents/` = standalone deployable services. Local agents = DB records managed via `/api/agents`.

3. **Registry vs Agents.** `/api/registry` = public showcase. `/api/agents` = installed agents on a hub instance.

4. **`agent.endpoint` vs `agent.url`.** `endpoint` = A2A JSON-RPC POST URL. `url` = base homepage. The code uses `agent.endpoint or agent.url` — keep both accurate.

5. **Pydantic v2.** Use `.model_dump()`, not `.dict()`. Use `model_dump(exclude_unset=True)` for PATCH payloads.

6. **CORS.** The prototype uses `allow_origins=["*"]`. Production must restrict origins — never copy that pattern.

7. **`/.well-known` inconsistency.** `agents.py` may receive the full well-known URL; `back/main.py` appends the path automatically. Understand which you're touching.

---

## 18. Documentation Standards

| Artifact          | Requirement                                                  |
|-------------------|--------------------------------------------------------------|
| `README.md`       | Project overview, prerequisites, local dev, deployment       |
| `CONTRIBUTING.md` | Code style, workflow, PR rules, release process              |
| `AGENTS.md`       | AI agent context (architecture, patterns, gotchas)           |
| `CLAUDE.md`       | This file — AI coding assistant reference                    |
| `docs/`           | Long-form architecture docs and ADRs                         |
| `CHANGELOG.md`    | Generated from `feat`/`fix` commits per release             |
| Docstrings        | All Python functions/classes must have docstrings            |
| JSDoc/TSDoc       | Complex TS functions should be documented                    |
| Swagger/OpenAPI   | Auto-generated at `/docs` by FastAPI                         |

---

## 19. Team Contacts

| Name              | Role                    | Email                          | GitHub       |
|-------------------|-------------------------|--------------------------------|--------------|
| James Smith       | Developer / PM          | smitjam2@oregonstate.edu       | gitJamoo     |
| Minsu Kim         | Developer               | kimminsu@oregonstate.edu       | minkim26     |
| Rohan Thapliyal   | Developer / CI-CD       | thapliyr@oregonstate.edu       | Rohanthap    |
| Long Tran         | Developer / QA          | tranlon@oregonstate.edu        | longtran921  |
| John Sweet        | Sponsor / Stakeholder   | john.sweet@oregonstate.edu     | jsweet8258   |
