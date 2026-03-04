import os
import uuid
import logging
from dotenv import load_dotenv

import anthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AGENT_CARD = {
    "name": "Claude",
    "description": "Anthropic Claude — available models: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001, claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022",
    "version": "1.0.0",
    "url": os.environ.get("AGENT_URL", "http://localhost:8002"),
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "skills": [
        {
            "id": "chat",
            "name": "Chat",
            "description": "Chat with Anthropic Claude models",
            "tags": ["llm", "anthropic", "claude"],
        }
    ],
}

DEFAULT_MODEL = "claude-sonnet-4-6"


@app.get("/.well-known/agent.json")
def agent_card():
    return AGENT_CARD


@app.post("/")
async def handle_jsonrpc(request: Request):
    body = await request.json()

    if body.get("method") != "message/send":
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32601, "message": "Method not found"},
        }

    params = body.get("params", {})
    message = params.get("message", {})
    parts = message.get("parts", [])
    user_text = parts[0].get("text", "") if parts else ""

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32000, "message": "ANTHROPIC_API_KEY not set"},
        }

    model = params.get("model", DEFAULT_MODEL)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{"role": "user", "content": user_text}],
        )
        response_text = response.content[0].text if response.content else ""
    except Exception as e:
        log.error(f"Anthropic API error: {e}")
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32000, "message": str(e)},
        }

    return {
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "result": {
            "messageId": str(uuid.uuid4()),
            "role": "agent",
            "artifacts": [
                {
                    "artifactId": str(uuid.uuid4()),
                    "parts": [{"text": response_text}],
                }
            ],
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8002)))
