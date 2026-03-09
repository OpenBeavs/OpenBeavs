# API Key Configuration

This guide explains how to configure API keys so that Claude, ChatGPT, and Gemini are available as agents in OpenBeavs.

Each provider runs as a standalone A2A agent server. Keys go into each agent's own `.env` file. Once the server is running, install the agent through the Workspace > Agents page.

---

## Anthropic (Claude)

### 1. Get Your API Key
1. Go to [console.anthropic.com](https://console.anthropic.com) and sign in.
2. In the left sidebar, click **API Keys**.
3. Click **Create Key**, give it a name (e.g. `openbeavs-local`), and click **Create API Key**.
4. Copy the key — it starts with `sk-ant-`. **You will not be able to see it again after closing the dialog.**

### 2. Add to `agents/claude-agent/.env`
```
ANTHROPIC_API_KEY='sk-ant-YOUR_KEY_HERE'
```

### 3. Start the Agent Server
```bash
cd agents/claude-agent
conda run -n open-webui python agent.py
```
The server runs on **port 8002**.

### 4. Install in OpenBeavs
Go to **Workspace > Agents** → click **+** → enter `http://localhost:8002` → click **Add**.

### Available Models
Default: `claude-sonnet-4-6`. Also supported: `claude-opus-4-6`, `claude-haiku-4-5-20251001`, `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`.

---

## OpenAI (ChatGPT)

### 1. Get Your API Key
1. Go to [platform.openai.com](https://platform.openai.com) and sign in.
2. In the left sidebar, click **API keys**.
3. Click **Create new secret key**, give it a name, and click **Create secret key**.
4. Copy the key — it starts with `sk-`. **You will not be able to see it again after closing the dialog.**

### 2. Add to `agents/chatgpt-agent/.env`
```
CHATGPT_API_KEY='sk-YOUR_KEY_HERE'
```

### 3. Start the Agent Server
```bash
cd agents/chatgpt-agent
conda run -n open-webui python agent.py
```
The server runs on **port 8003**.

### 4. Install in OpenBeavs
Go to **Workspace > Agents** → click **+** → enter `http://localhost:8003` → click **Add**.

### Available Models
Default: `gpt-4o`. Also supported: `gpt-4o-mini`, `gpt-5.2`, `gpt-5.2-chat-latest`, `gpt-5.2-pro`.

---

## Google (Gemini)

### 1. Get Your API Key
1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with your Google account.
2. Click **Get API key** in the left sidebar.
3. Click **Create API key**, select a Google Cloud project, and click **Create API key in existing project**.
4. Copy the key — it starts with `AIza`.

### 2. Add to `agents/gemini-agent/.env`
```
GEMINI_API_KEY='AIza-YOUR_KEY_HERE'
```

### 3. Start the Agent Server
```bash
cd agents/gemini-agent
conda run -n open-webui python agent.py
```
The server runs on **port 8004**.

### 4. Install in OpenBeavs
Go to **Workspace > Agents** → click **+** → enter `http://localhost:8004` → click **Add**.

### Available Models
Default: `gemini-2.0-flash`. Also supported: `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-pro`, `gemini-1.5-flash`.

---

## Notes

- Keys are stored in each agent's `.env` file, which is gitignored and never committed to the repository.
- Each agent server must be running before you can install or chat with it.
- If an agent server is not running, the Add step will fail with: "Error fetching agent's .well-known/agent.json".
- Once installed, an agent appears in the chat model selector and in Arena mode.

---

*API keys for Claude and ChatGPT for testing purposes is held by Long Tran. Contact me via email or Discord if needed.*
