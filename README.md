# OpenBeavs

An AI Agent Registry Platform for Oregon State University — a customized fork of [Open WebUI](https://github.com/open-webui/open-webui) v0.6.5.

OpenBeavs adds agent discovery, registration, and Agent-to-Agent (A2A) communication to the Open WebUI workspace. Users can browse a shared registry of AI agents, install them into their workspace, and let agents collaborate via the A2A JSON-RPC 2.0 protocol to produce richer responses.

**CS Capstone Team #043**

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Frontend | SvelteKit 2, Svelte 4, TypeScript 5, Tailwind CSS 4, Vite 5 |
| Backend (A2A hub) | FastAPI, Pydantic, jsonrpcserver, Python 3.11+ |
| Backend (Open WebUI) | FastAPI, SQLAlchemy, LangChain, ChromaDB |
| Auth | Azure MSAL (Microsoft SSO) |
| Infrastructure | Docker, Google Cloud Run, Cloud Build, Artifact Registry |

## Architecture Overview

OpenBeavs is split into three main parts:

- **`front/`** — SvelteKit UI (forked from Open WebUI). Contains the frontend app and the bundled Open WebUI Python backend. Handles workspace management, agent browsing, and chat.
- **`back/`** — Lightweight FastAPI service that acts as the A2A hub. Manages agent registration, discovery, and routes JSON-RPC 2.0 messages between agents.
- **`agents/`** — Example agents (Cyrano-de-Bergerac, oregon-state-expert, etc.) that demonstrate how to build and deploy A2A-compatible agents.

Communication between agents uses the **A2A protocol**: JSON-RPC 2.0 over HTTP with discovery via `/.well-known/agent.json` endpoints. The flow is: Browser -> Open WebUI Backend -> JSON-RPC -> External Agents.

## Project Structure

```
OpenBeavs/
├── front/              # SvelteKit frontend (Open WebUI fork)
│   ├── src/            # Svelte components, routes, stores, API clients
│   ├── backend/        # Open WebUI Python backend (bundled)
│   ├── cypress/        # E2E tests
│   ├── test/           # Unit tests (Vitest)
│   └── static/         # Static assets
├── back/               # FastAPI backend — A2A hub
│   ├── main.py         # All routes, models, in-memory DB
│   └── tests/          # pytest tests
├── agents/             # Example A2A agents
├── docs/               # Architecture docs, ADRs, schemas
├── Dockerfile          # Unified multi-stage build (Node 20 → Python 3.11)
├── cloudbuild.yaml     # GCP Cloud Build pipeline
├── deploy.sh           # Manual deployment script
├── docker-compose.yaml # Local Docker setup
└── Makefile            # Docker convenience commands
```

## Prerequisites

- [Docker](https://www.docker.com/)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- [Node.js and npm](https://nodejs.org/) (Node 20+)
- [Python 3.11+](https://www.python.org/)

## Local Development

### Backend (`back/`)

```bash
cd back
pip install -r requirements.txt
uvicorn main:app --reload  # http://localhost:8000
```

### Frontend (`front/`)

```bash
cd front
npm install
npm run pyodide:fetch   # one-time: download WASM Python runtime
npm run dev             # http://localhost:5173
```

### Docker

```bash
make install   # docker-compose up -d
make start     # start existing containers
make stop      # stop containers
```

## Testing

### Backend

```bash
cd back && pytest tests/ -v
```

### Frontend

```bash
cd front
npm run test:frontend     # Vitest unit tests
npm run cy:open           # Cypress E2E (interactive)
```

## Linting & Formatting

### Frontend

```bash
cd front
npm run lint              # ESLint + type check + backend lint
npm run lint:frontend     # ESLint only
npm run format            # Prettier
```

Prettier config: tabs, single quotes, 100 char width, no trailing commas.

### Backend

```bash
cd back
ruff check .    # lint
ruff format     # format
```

## Deployment

### Automated (primary)

Merging to `main` triggers automatic deployment via `cloudbuild.yaml`:

1. Pull cached Docker image from Artifact Registry
2. Build unified image (Node 20 frontend + Python 3.11 backend)
3. Push to `us-west1-docker.pkg.dev/osu-genesis-hub/cloud-run-source-deploy/openbeavs-frontend`
4. Deploy to Cloud Run (`openbeavs-deploy-test`, us-west1, 4 CPU / 8 GiB RAM)

### Manual

Requires a `.env` file with `GCP_PROJECT_ID` and `GCP_REGION`.

```bash
gcloud auth login
gcloud auth configure-docker
./deploy.sh
```

## Team Roster/Contacts

James Smith
#: 5037138776
email: smitjam2@oregonstate.edu , galavantinggeckoguy@gmail.com
GH: gitJamoo

Minsu Kim
#: 971-297-4257
Email: kimminsu@oregonstate.edu , minsteww26@gmail.com
GH: minkim26

Rohan Thapliyal
#: 5035236168
email: thapliyr@oregonstate.edu , rohanthapliyal2020@gmail.com
GH: Rohanthap

Long Tran
#: 541 207 5609
email: tranlon@oregonstate.edu
GH: longtran921

John Sweet
#: 2135456760
email: john.sweet@oregonstate.edu
GH: jsweet8258

## Contributing & Documentation

- [Contributing Guide](./CONTRIBUTING.md)
- [Architecture & ADRs](./docs/)
- A2A documentation:
  - [A2A Quickstart](./front/A2A_QUICKSTART.md)
  - [A2A Implementation Summary](./front/A2A_IMPLEMENTATION_SUMMARY.md)
  - [A2A Code Changes](./front/A2A_CODE_CHANGES.md)

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE) for details.
