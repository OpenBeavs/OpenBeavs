<div align="center">
  <img src="https://github.com/OpenBeavs/.github/raw/main/profile/Banner.png" width="100%" alt="OpenBeavs — AI Agent Platform for Oregon State University" />
</div>

<div align="center">

# OpenBeavs

**An AI agent platform that brings specialized AI assistants directly into the OSU community — no extra accounts, no friction.**

[![CI](https://github.com/OpenBeavs/OpenBeavs/actions/workflows/ci.yml/badge.svg)](https://github.com/OpenBeavs/OpenBeavs/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](./LICENSE)
[![Built with SvelteKit](https://img.shields.io/badge/Built%20with-SvelteKit-FF3E00?logo=svelte&logoColor=white)](https://kit.svelte.dev/)
[![Deployed on GCP](https://img.shields.io/badge/Deployed%20on-Google%20Cloud%20Run-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/run)

<!-- PLACEHOLDER: Add your live Cloud Run URL below (appears twice in this file).
     Find it: GCP Console → Cloud Run → service "openbeavs-deploy-test" (us-west1) → copy the URL. -->
[**→ Try OpenBeavs Live**](https://genesis.dev.oregonstate.edu/genesis-hub/embed-demo) &nbsp;·&nbsp;
[View on GitHub](https://github.com/OpenBeavs/OpenBeavs) &nbsp;·&nbsp;
[Report a Bug](https://github.com/OpenBeavs/OpenBeavs/issues)

</div>

---

## What is OpenBeavs?

Oregon State University students and faculty rely on dozens of different AI tools — and none of them know anything about OSU. OpenBeavs fixes that.

It's a shared AI workspace where you **sign in with your OSU account** and instantly access a registry of specialized AI agents: an OSU knowledge-base assistant that answers questions about classes, departments, and campus life; a writing coach; a weather agent; and more. Agents can even collaborate with each other behind the scenes to give you richer answers.

**The so-what:** Instead of every team or department building their own AI integration from scratch, OpenBeavs provides a single, OSU-authenticated hub where agents are discoverable, installable, and interoperable — using an open protocol anyone can build on.

---

## Key Features

### For Students & Faculty

- **Sign in with your OSU account** — Microsoft SSO means no new passwords; your existing OSU credentials work out of the box.
- **Browse and install AI agents from a shared registry** — find agents built by other OSU teams, install them into your workspace, and start chatting immediately.
- **Ask the OSU knowledge base anything** — a continuously-updated RAG agent crawls `*.oregonstate.edu` to answer real questions about admissions, financial aid, courses, and more.
- **Agents that collaborate** — specialized agents pass tasks to each other automatically; a single question can route through multiple experts and come back as one coherent answer.

### For Developers

- **Build your own agent in minutes** — any HTTP service that serves a `/.well-known/agent.json` card can register with the hub. Language and framework are your choice.
- **Open protocol (A2A)** — agents communicate over JSON-RPC 2.0; the spec is public and the example agents are in this repo under [`agents/`](./agents/).

---

## Demo

<!-- The demo.gif lives at front/demo.gif — no changes needed to this path. -->
<div align="center">
  <img
    src="./front/demo.gif"
    width="90%"
    alt="Screen recording showing a user chatting with GPT 4."
  />
  <p><em>Browsing the agent registry and chatting with the OSU knowledge-base agent.</em></p>
</div>

  <iframe 
    id="kaltura_player" 
    src="https://media.oregonstate.edu/p/1285941/sp/128594100/embedIframeJs/uiconf_id/28628201/partner_id/1285941?iframeembed=true&entry_id=1_2qvehzir" 
    width="608" 
    height="402" 
    allowfullscreen 
    webkitallowfullscreen 
    mozAllowFullScreen 
    allow="autoplay *; fullscreen *; encrypted-media *" 
    frameborder="0"
    title="Demo video of the Oregon State Agent assistant">
  </iframe>

<!-- PLACEHOLDER: Add 1-2 static screenshots below for more context.
     Suggested shots:
       1. The agent registry grid (Browse Agents view)
       2. The chat interface with multiple agents active
     Steps: take screenshots while the app is running, save to docs/assets/, then uncomment:
       <img src="./docs/assets/screenshot-registry.png" width="45%" alt="Agent registry showing available OSU agents" />
       <img src="./docs/assets/screenshot-chat.png" width="45%" alt="Chat interface with the OSU knowledge-base agent" />
-->

---

## Try It

| Option | Details |
|--------|---------|
| **Live deployment** | [**→ Open the app**](https://genesis.dev.oregonstate.edu/genesis-hub/embed-demo) — sign in with your OSU Microsoft account |
| **Run locally** | See [Local Setup](#local-setup) below |
| **OSU RAG Pipeline** | [github.com/OpenBeavs/OSU-RAG-Pipeline](https://github.com/OpenBeavs/OSU-RAG-Pipeline) |

**Platform requirements:** Modern browser (Chrome, Firefox, Safari). OSU Microsoft account required for the live deployment. Local Docker setup has no auth requirement.

---

## Local Setup

```bash
# Clone the repo
git clone https://github.com/OpenBeavs/OpenBeavs.git
cd OpenBeavs

# Run the full stack with Docker (recommended)
make install   # docker-compose up -d — app at http://localhost:3000
```

**Prerequisites:** [Docker](https://www.docker.com/) (recommended) · Node 20+ · Python 3.11+

For per-service setup, API key configuration, and deployment docs:

- [Backend dev guide](./back/README.md) · [Frontend dev guide](./front/README.md)
- [API key setup (Claude, ChatGPT, Gemini)](./apikeyconfig.md)
- [A2A Quickstart](./front/A2A_QUICKSTART.md)
- [Architecture & ADRs](./docs/)
- [Contributing Guide](./CONTRIBUTING.md)

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                      OpenBeavs Hub                       │
│  SvelteKit UI  →  FastAPI Backend  →  Agent Registry     │
│           ↕ A2A (JSON-RPC 2.0 over HTTP)                 │
│   OSU Expert · Cyrano · Weather · Your Agent Here...     │
└──────────────────────┬──────────────────────────────────┘
                       │ vector queries
┌──────────────────────▼──────────────────────────────────┐
│                   OSU RAG Pipeline                       │
│  BFS Crawler → Embeddings → Firestore Vector Store       │
│  (crawls *.oregonstate.edu on a cron schedule)           │
└─────────────────────────────────────────────────────────┘
```

The hub routes user messages to registered agents using the **A2A protocol** — an open JSON-RPC 2.0 standard with `/.well-known/agent.json` discovery cards. Agents can call other agents, enabling multi-step pipelines with no extra glue code.

---

## Team

**CS Capstone Team #043 · Oregon State University**

| Name | Role | GitHub | Contact |
|------|------|--------|---------|
| James Smith | Developer / PM | [@gitJamoo](https://github.com/gitJamoo) | smitjam2@oregonstate.edu |
| Minsu Kim | Developer | [@minkim26](https://github.com/minkim26) | kimminsu@oregonstate.edu |
| Rohan Thapliyal | Developer / CI-CD | [@Rohanthap](https://github.com/Rohanthap) | thapliyr@oregonstate.edu |
| Long Tran | Developer / QA | [@longtran921](https://github.com/longtran921) | tranlon@oregonstate.edu |
| John Sweet | Project Sponsor | [@jsweet8258](https://github.com/jsweet8258) | john.sweet@oregonstate.edu |

**Questions or feedback?** [Open a GitHub Issue](https://github.com/OpenBeavs/OpenBeavs/issues) or email any team member above.

---

## License

This project is licensed under the MIT License — see [LICENSE](./LICENSE) for details.
