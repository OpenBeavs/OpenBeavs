# AGENTS.md — GENESIS-AI-Hub Context File

> **For AI Agents:** Read this entire file before making any changes to the codebase.
> This is the single source of truth for understanding the project's architecture,
> conventions, and rules. Violating these guidelines will produce rejected PRs.

---

## 1. Project Identity

**Name:** GENESIS-AI-Hub (also referred to as "OpenBeavs")
**Team:** Oregon State University CS Capstone — Team #043
**Sponsor:** John V. Sweet (john.sweet@oregonstate.edu)
**GitHub Org:** [OpenBeavs](https://github.com/OpenBeavs/)

**Mission:** A decentralized platform for discovering, registering, and communicating
with AI agents. It implements the **Agent-to-Agent (A2A) protocol** built on
JSON-RPC 2.0, allowing standardized inter-agent communication through
`/.well-known/agent.json` discovery cards.

---

## 2. High-Level Architecture

The repository contains **two distinct backends** and **one frontend**. Do not
confuse them.

```
GENESIS-AI-Hub/
├── back/                        # Lightweight/prototype FastAPI backend (in-memory)
│   ├── main.py                  # Full app: chats, agents, JSON-RPC endpoint
│   ├── requirements.txt
│   └── tests/
│
├── front/                       # PRIMARY application (Open WebUI fork + custom additions)
│   ├── backend/                 # Production Python backend (SQLite/Peewee ORM)
│   │   └── open_webui/
│   │       ├── main.py          # FastAPI app entrypoint (production)
│   │       ├── config.py        # All environment variable configuration (large file)
│   │       ├── env.py           # Environment variable loading
│   │       ├── routers/         # All API route handlers (27 routers)
│   │       ├── models/          # Database models (Peewee ORM) + Pydantic schemas
│   │       ├── utils/           # Auth, helpers, misc utilities
│   │       ├── migrations/      # Alembic DB migrations
│   │       └── retrieval/       # RAG / vector search logic
│   └── src/                     # SvelteKit frontend
│       └── lib/
│           └── components/
│               └── workspace/
│                   ├── Agents.svelte   # Agent registry UI
│                   └── ...
│
├── agents/                      # Standalone deployable agents (Google ADK)
│   ├── Cyrano-de-Bergerac/      # Two-agent system (Chris + Cyrano + orchestrator)
│   ├── oregon-state-expert/
│   ├── oregon-state-scraper/
│   └── weather-expert-agent/
│
├── docs/                        # Long-form project documentation
├── .github/
│   ├── pull_request_template.md
│   └── workflows/               # CI/CD GitHub Actions
├── deploy.sh                    # GCP Cloud Run deployment script
├── cloudbuild.yaml              # GCP Cloud Build configuration
├── Dockerfile                   # Root-level container build
└── CONTRIBUTING.md              # Full team contribution guide (read this too)
```

---

## 3. Tech Stack

### Frontend (`front/src/`)
| Concern         | Technology                          |
|-----------------|-------------------------------------|
| Framework       | **SvelteKit** (Svelte 5)            |
| Language        | **TypeScript**                      |
| Styling         | **Vanilla CSS** (no Tailwind)       |
| Build Tool      | **Vite**                            |
| Linting         | **ESLint**                          |
| Formatting      | **Prettier**                        |
| State           | Svelte stores                       |

### Production Backend (`front/backend/open_webui/`)
| Concern         | Technology                          |
|-----------------|-------------------------------------|
| Framework       | **FastAPI** (async)                 |
| Language        | **Python 3.x** with full type hints |
| ORM             | **Peewee** (SQLite)                 |
| Schema/Validation | **Pydantic v2** (`BaseModel`)     |
| Auth            | JWT via `open_webui.utils.auth`     |
| Formatting/Lint | **Ruff**                            |
| Web Server      | **Uvicorn**                         |
| Migrations      | **Alembic**                         |

### Prototype Backend (`back/`)
| Concern         | Technology                    |
|-----------------|-------------------------------|
| Framework       | **FastAPI**                   |
| Storage         | In-memory Python dicts        |
| JSON-RPC        | `jsonrpcserver` library       |

### Standalone Agents (`agents/`)
| Concern         | Technology                     |
|-----------------|--------------------------------|
| Framework       | **Google Agent Development Kit (ADK)** |
| Protocol        | **A2A** (Agent-to-Agent) — JSON-RPC 2.0 |
| Models          | Google Gemini (via `GEMINI_API_KEY`) |
| Serving         | **Uvicorn** on custom ports    |

### Infrastructure
| Concern         | Technology                    |
|-----------------|-------------------------------|
| Cloud           | **Google Cloud Platform (GCP)** |
| Compute         | **Google Cloud Run**          |
| Build           | **Cloud Build** (`cloudbuild.yaml`) |
| Containers      | **Docker**                    |

---

## 4. The A2A Protocol (Critical Concept)

The A2A (Agent-to-Agent) protocol is the core of this project. **Every agent,
including the hub itself**, must comply with it.

### Agent Discovery Card (`/.well-known/agent.json`)
An A2A-compliant agent must serve a JSON card at this endpoint:
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
      "tags": ["tag1", "tag2"],
      "examples": ["example query 1"]
    }
  ]
}
```

### Message Communication (JSON-RPC 2.0)
All inter-agent messages use JSON-RPC 2.0 over HTTP POST:
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
The hub sends these requests in `front/backend/open_webui/routers/agents.py`
`send_message_to_agent()` and `back/main.py`'s `generate_agent_response()`.

---

## 5. Key Backend API Routers (`front/backend/open_webui/routers/`)

These are the custom additions to the Open WebUI base. Pay close attention to
these files when touching agent functionality:

| Router File       | Prefix         | Purpose                                          |
|-------------------|----------------|--------------------------------------------------|
| `agents.py`       | `/api/agents`  | Local agent CRUD + A2A message relay             |
| `registry.py`     | `/api/registry`| Public registry: submit, update, delete entries  |
| `auths.py`        | `/api/auths`   | Authentication (MS SSO, local)                   |
| `chats.py`        | `/api/chats`   | Chat thread management                           |
| `models.py`       | `/api/models`  | LLM model listing                                |
| `tickets.py`      | `/api/tickets` | Support tickets                                  |
| `knowledge.py`    | `/api/knowledge`| RAG knowledge base management                   |
| `ollama.py`       | `/api/ollama`  | Ollama model proxy                               |
| `openai.py`       | `/api/openai`  | OpenAI-compatible API proxy                      |

### Auth Pattern (REQUIRED for all new routes)
Every endpoint **must** use one of these FastAPI dependencies:
- `get_verified_user` — any authenticated user
- `get_admin_user` — admin role required

```python
from open_webui.utils.auth import get_admin_user, get_verified_user

@router.get("/my-endpoint")
async def my_endpoint(user=Depends(get_verified_user)):
    ...
```

### Permission Pattern (REQUIRED for mutating operations)
Always check ownership before updating or deleting:
```python
if user.role != "admin" and resource.user_id != user.id:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=ERROR_MESSAGES.UNAUTHORIZED,
    )
```

### Error Handling Pattern
Always use `ERROR_MESSAGES` constants and raise `HTTPException`:
```python
from open_webui.constants import ERROR_MESSAGES

raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND)
raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT())
raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.UNAUTHORIZED)
```

---

## 6. Database Models (`front/backend/open_webui/models/`)

Custom models added to the base Open WebUI:

| Model File    | Class(es)                                            | Table Purpose              |
|---------------|------------------------------------------------------|----------------------------|
| `agents.py`   | `AgentModel`, `AgentResponse`, `RegisterAgentForm`, `Agents` | Local installed agents |
| `registry.py` | `RegistryAgentModel`, `SubmitRegistryAgentForm`, `RegistryAgents` | Public agent registry |
| `tickets.py`  | `TicketModel`, `Tickets`                             | Support ticket system      |

**Key fields on `AgentModel`:**
- `id` (UUID string), `name`, `description`
- `endpoint` — A2A JSON-RPC endpoint URL
- `url` — Agent's base URL (fallback for `endpoint`)
- `version`, `capabilities` (dict), `skills` (list)
- `default_input_modes`, `default_output_modes`
- `profile_image_url`
- `user_id` — owner
- `is_active` boolean
- `created_at` timestamp

---

## 7. Standalone Agents (`agents/`)

Each agent in this directory is independently deployable and should comply with
the A2A protocol. They are built with the **Google ADK**.

### Cyrano de Bergerac (`agents/Cyrano-de-Bergerac/`)
A multi-agent pipeline using `SequentialAgent`:
1. **chris** — tone analysis, classifies user input
2. **cyrano** — wordsmith, crafts the eloquent response
3. **orchestrator** — `SequentialAgent` that chains chris → cyrano

Run the A2A server:
```bash
uvicorn orchestrator.agent:a2a_app --host localhost --port 8001
```
Verify discovery: `http://localhost:8001/.well-known/agent-card.json`

### Adding a New Agent
1. Create a subdirectory under `agents/<agent-name>/`
2. Follow the standard ADK pattern: `agent.py`, `requirements.txt`, `.env.example`, `README.md`
3. Expose `/.well-known/agent.json` for A2A discovery
4. Register with the hub via `POST /api/agents/register-by-url`

---

## 8. Running Locally

### Production Backend (`front/backend/`)
```bash
cd front/
# Install deps (first time)
pip install -r backend/requirements.txt

# Run dev server (default port: 8080)
PORT=8080 uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 --forwarded-allow-ips "*" --reload

# Or use the dev script
bash backend/dev.sh
```

### Prototype Backend (`back/`)
```bash
cd back/
pip install -r requirements.txt
uvicorn main:app --reload
# Available at http://localhost:8000
```

### Frontend (`front/`)
```bash
cd front/
npm install
npm run dev
```

### Linting & Formatting
```bash
# Frontend (from front/)
npm run lint           # Lint everything (frontend + types + backend)
npm run lint:frontend  # ESLint only
npm run format         # Prettier format

# Backend (Python)
ruff check             # Lint check
ruff format            # Format Python code
```

---

## 9. Deployment (GCP Cloud Run)

```bash
# Authenticate
gcloud auth login
gcloud auth configure-docker

# Deploy (fills in project ID and region from deploy.sh)
./deploy.sh
```

The `cloudbuild.yaml` defines the CI/CD pipeline. Every merged PR to `main`
should trigger a build.

---

## 10. Code Conventions & Rules

### Python (Backend)
- **Always use type hints** on all function parameters and return types.
- **Always add docstrings** to every route function and class method.
- **Use `Pydantic v2` `BaseModel`** for all request/response schemas.
- **Use `Ruff`** for linting and formatting — do not use Black or isort separately.
- **Use `uuid.uuid4()`** for all ID generation; IDs are always `str`.
- **Import organization:** stdlib → third-party → local (`open_webui.*`).
- **Never use `print()`** — use Python's standard `logging` module.
- Do **not** hardcode secrets; rely on env vars loaded via `open_webui.config`.

**Example well-formed route:**
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
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT())
```

### TypeScript/Svelte (Frontend)
- Use **TypeScript** — no untyped JS in `.svelte` or `.ts` files.
- Use **Svelte stores** for shared state — do not prop-drill deeply.
- Component files are **PascalCase** (e.g., `Agents.svelte`).
- Use **Prettier** for formatting.
- Use **ESLint** for linting — run `npm run lint` before committing.
- No inline styles — use CSS classes or scoped `<style>` blocks.
- API calls go through the existing `$lib/apis/` utility layer — do not call
  `fetch()` directly in components.

### Commit Messages (Conventional Commits)
```
<type>(<scope>): <subject (≤50 chars, imperative)>
```
| `<type>` | When |
|----------|------|
| `feat`   | New user-facing feature |
| `fix`    | Bug fix |
| `chore`  | Build, deps, tooling |
| `docs`   | Documentation only |
| `style`  | Formatting, no logic change |
| `refactor` | Refactor (not a fix, not a feature) |

**Examples:**
- `feat(agents): add A2A message relay endpoint`
- `fix(registry): handle duplicate agent URL registration`
- `chore(deps): update fastapi to 0.111.0`

---

## 11. Git Workflow & PR Rules

- **Branch model:** GitFlow — branch off `main` for each feature/fix.
- **Branch naming:** `kebab-case` describing the change, e.g. `agent-registration-hub-not-found-fix`.
- **PRs:** Use the `.github/pull_request_template.md`. Must include Description,
  Related Issues, Testing Notes, and Screenshots (for UI changes).
- **PR size:** Target ≤ 400–500 lines of diff. Break larger work into smaller PRs.
- **Approval:** Requires **1 approval** from a team member (not yourself).
- **Status checks must pass:** All unit tests + linter.
- **After merge:** Delete the feature branch.
- **Merging:** Default is `merge`; use `rebase` only when bringing in a large
  number of upstream changes.
- **Versioning:** SemVer (`MAJOR.MINOR.PATCH`). Tag every production deployment.

---

## 12. Security Rules (Non-Negotiable)

- **NEVER hardcode secrets** — no API keys, DB credentials, or SSO secrets in code.
- **All secrets** via environment variables loaded from a `.env` file (gitignored)
  or **GCP Secret Manager** in production.
- **`.env` files are never committed.** There is an `.env.example` in agent dirs
  to document required variables.
- **Run `npm audit`** or check Dependabot alerts at the start of every sprint.
- Report security vulnerabilities via **private GitHub Issue** + email to the team.

---

## 13. Environment Variables

Key variables for the production backend (see `front/backend/open_webui/config.py`
and `env.py` for the full list):

| Variable             | Purpose                                |
|----------------------|----------------------------------------|
| `DATABASE_URL`       | SQLite/PostgreSQL connection string    |
| `SECRET_KEY`         | JWT signing key                        |
| `GEMINI_API_KEY`     | Used by standalone agents (ADK)        |
| `CHRIS_MODEL`        | Gemini model ID for Chris agent        |
| `CYRANO_MODEL`       | Gemini model ID for Cyrano agent       |
| `PORT`               | Backend server port (default: `8080`)  |
| `OPENAI_API_KEY`     | Optional OpenAI proxy support          |
| `OLLAMA_BASE_URL`    | Optional Ollama proxy support          |

---

## 14. Testing

- Backend tests live in `back/tests/` and `front/backend/open_webui/test/`.
- Run backend tests:
  ```bash
  cd back/
  pytest
  ```
- All new API routes should have corresponding unit tests.
- All PRs require **all tests to pass** before merge.

---

## 15. Documentation Standards

| Artifact        | Requirement                                                      |
|-----------------|------------------------------------------------------------------|
| `README.md`     | Project overview, prerequisites, local dev, deployment           |
| `CONTRIBUTING.md` | Code style, workflow, PR rules, release process                |
| `docs/`         | Long-form architecture docs, ADR (Architecture Decision Records) |
| `AGENTS.md`     | *(this file)* — AI agent context                                 |
| `CHANGELOG.md`  | Generated from `feat` and `fix` commits per release             |
| Docstrings      | **All** Python functions/classes must have docstrings            |
| JSDoc/TSDoc     | Complex TS functions should be documented                        |
| API Docs        | Auto-generated via FastAPI/Swagger at `/docs`                    |

---

## 16. Team Contacts

| Name           | Role              | Email                          | GitHub       |
|----------------|-------------------|--------------------------------|--------------|
| James Smith    | Developer/PM      | smitjam2@oregonstate.edu       | gitJamoo     |
| Minsu Kim      | Developer         | kimminsu@oregonstate.edu       | minkim26     |
| Rohan Thapliyal | Developer / CI-CD | thapliyr@oregonstate.edu      | Rohanthap    |
| Long Tran      | Developer / QA    | tranlon@oregonstate.edu        | longtran921  |
| John Sweet     | Sponsor/Stakeholder | john.sweet@oregonstate.edu   | jsweet8258   |

---

## 17. Common Gotchas for AI Agents

1. **Two backends exist.** `back/main.py` is the lightweight prototype. The
   production code is `front/backend/open_webui/`. Most new work should go into
   the production backend.

2. **`agents/` vs local agents.** The `agents/` dir contains *standalone*
   deployable agent services. Local agents registered into the hub are stored in
   the DB via `front/backend/open_webui/models/agents.py`.

3. **Registry vs Agents.** "Registry" (`/api/registry`) = public showcase of
   agents others can discover. "Agents" (`/api/agents`) = agents *installed* into
   the local hub instance for active use.

4. **`agent.endpoint` vs `agent.url`.**  `endpoint` = the A2A JSON-RPC POST URL.
   `url` = the agent's base homepage URL. When sending a message, the code uses
   `agent.endpoint or agent.url` as a fallback.

5. **Pydantic v2 usage.** Use `.model_dump()` not `.dict()` (deprecated).
   Use `model_dump(exclude_unset=True)` for partial update payloads (PATCH).

6. **Never open-code CORS `allow_origins=["*"]` in production.** The prototype
   backend does this for simplicity. Production must restrict origins.

7. **A2A `.well-known` path.** When registering an agent by URL, the endpoint
   provided by the user may *be* the `/.well-known/agent.json` URL directly
   (as seen in `front/backend/open_webui/routers/agents.py`), or the base URL
   (as in `back/main.py` which appends `/.well-known/agent.json` automatically).
   Be aware of this inconsistency when modifying registration logic.
