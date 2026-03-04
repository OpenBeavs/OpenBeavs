import os
import uuid
import logging
from dotenv import load_dotenv

import openai
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
    "name": "ChatGPT",
    "description": "OpenAI ChatGPT — available models: gpt-4o, gpt-4o-mini, gpt-5.2, gpt-5.2-chat-latest, gpt-5.2-pro",
    "version": "1.0.0",
    "url": os.environ.get("AGENT_URL", "http://localhost:8003"),
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "skills": [
        {
            "id": "chat",
            "name": "Chat",
            "description": "Chat with OpenAI ChatGPT models",
            "tags": ["llm", "openai", "chatgpt"],
        }
    ],
}

DEFAULT_MODEL = "gpt-4o"


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

    api_key = os.environ.get("CHATGPT_API_KEY", "")
    if not api_key:
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32000, "message": "CHATGPT_API_KEY not set"},
        }

    model = params.get("model", DEFAULT_MODEL)

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_text}],
        )
        response_text = response.choices[0].message.content if response.choices else ""
    except Exception as e:
        log.error(f"OpenAI API error: {e}")
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
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8003)))
