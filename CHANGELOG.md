# Changelog

All notable changes to OpenBeavs are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- A2A (Agent-to-Agent) protocol integration: JSON-RPC 2.0 over HTTP with `/.well-known/agent.json` discovery
- Agent registry UI (`front/src/lib/components/workspace/Agents.svelte`) — browse, install, and manage agents
- Public agent registry API (`/api/registry`) — submit, update, and delete registry entries
- Local agent CRUD + A2A message relay (`/api/agents`)
- Support ticket system (`/api/tickets`)
- Microsoft SSO (MSAL) authentication
- Standalone example agents: Cyrano-de-Bergerac, oregon-state-expert, oregon-state-scraper, weather-expert-agent, claude-agent, chatgpt-agent, gemini-agent
- Unified Docker build: SvelteKit frontend + Python backend in one image
- GCP Cloud Run deployment via `cloudbuild.yaml` (auto-deploy on merge to `main`)
- Makefile convenience commands for Docker workflows
- Pre-commit hooks for lint enforcement

---

## How to Cut a Release

1. Merge all intended PRs to `main`.
2. Determine the next version per SemVer (`MAJOR.MINOR.PATCH`).
3. Move items from `[Unreleased]` to a new versioned section:
   ```markdown
   ## [1.2.0] — YYYY-MM-DD
   ```
4. Commit: `docs(changelog): release v1.2.0`
5. Tag the commit: `git tag v1.2.0 && git push origin v1.2.0`
6. The Cloud Build pipeline deploys automatically.
