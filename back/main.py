from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import uuid
from datetime import datetime
import asyncio
import json

# JSON-RPC imports
from jsonrpcserver import method, Result, Success, Error as JSONRPCError
import jsonrpcserver

app = FastAPI()


# Well-known endpoint for agent discovery (following the format from example)
@app.get("/.well-known/agent.json")
def get_agent_info(request: Request):
    """Return agent information in the expected format"""
    # Return information about the hub itself as an agent
    hub_agent = {
        "capabilities": {"streaming": True},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "description": "OpenBeavs for agent coordination and management",
        "name": "OpenBeavs",
        "skills": [
            {
                "description": "Manages and coordinates AI agents",
                "examples": ["list agents", "register agent", "chat with agent"],
                "id": "agent_management",
                "name": "Agent Management",
                "tags": ["agent", "coordination", "management"],
            }
        ],
        "supportsAuthenticatedExtendedCard": True,
        "url": f"{request.url.scheme}://{request.url.netloc}",
        "version": "1.0.0",
    }
    return hub_agent


# Allow all origins for simplicity, but you should restrict this in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for demonstration (would use database in production)
chats_db: Dict[str, dict] = {}
messages_db: Dict[str, List[dict]] = {}
agents_db: List[dict] = []


# Define JSON-RPC methods
@method
def SendMessageRequest(params: Dict[str, Any]) -> Result:
    """Handle JSON-RPC SendMessageRequest"""
    try:
        chat_id = params.get("chat_id")
        message = params.get("message", params.get("input", ""))
        files = params.get("files", [])

        if not chat_id:
            return JSONRPCError(code=-32602, message="Missing chat_id parameter")

        # Add user message to the chat
        user_message = Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="user",
            content=message,
            timestamp=datetime.now(),
            files=files if files else None,
        )

        messages_db[chat_id].append(user_message.dict())

        # Get the agent for this chat
        chat_agent_id = chats_db[chat_id]["agent_id"]
        agent = next((a for a in agents_db if a["id"] == chat_agent_id), None)
        if not agent:
            return JSONRPCError(code=404, message="Agent not found")

        # Generate response from agent
        response_content = generate_agent_response(message, agent)

        # Add assistant message
        assistant_message = Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content=response_content,
            timestamp=datetime.now(),
        )

        messages_db[chat_id].append(assistant_message.dict())

        # Update chat timestamp
        chats_db[chat_id]["updated_at"] = datetime.now()

        return Success(assistant_message.dict())
    except Exception as e:
        return JSONRPCError(code=-32603, message=f"Internal error: {str(e)}")


@method
def SendStreamingMessageRequest(params: Dict[str, Any]) -> Result:
    """Handle JSON-RPC SendStreamingMessageRequest"""
    # For now, just return the same as SendMessageRequest since streaming is not fully implemented
    return SendMessageRequest(params)


@method
def GetTaskRequest(params: Dict[str, Any]) -> Result:
    """Handle JSON-RPC GetTaskRequest"""
    try:
        task_id = params.get("task_id")
        if not task_id:
            return JSONRPCError(code=-32602, message="Missing task_id parameter")

        # For now, return a simple response
        return Success(
            {
                "task_id": task_id,
                "status": "completed",
                "result": "Task result placeholder",
            }
        )
    except Exception as e:
        return JSONRPCError(code=-32603, message=f"Internal error: {str(e)}")


@method
def CancelTaskRequest(params: Dict[str, Any]) -> Result:
    """Handle JSON-RPC CancelTaskRequest"""
    try:
        task_id = params.get("task_id")
        if not task_id:
            return JSONRPCError(code=-32602, message="Missing task_id parameter")

        # For now, return a simple response
        return Success({"task_id": task_id, "cancelled": True})
    except Exception as e:
        return JSONRPCError(code=-32603, message=f"Internal error: {str(e)}")


@method
def SetTaskPushNotificationConfigRequest(params: Dict[str, Any]) -> Result:
    """Handle JSON-RPC SetTaskPushNotificationConfigRequest"""
    try:
        # For now, just acknowledge the request
        return Success({"status": "config_set"})
    except Exception as e:
        return JSONRPCError(code=-32603, message=f"Internal error: {str(e)}")


@method
def GetTaskPushNotificationConfigRequest(params: Dict[str, Any]) -> Result:
    """Handle JSON-RPC GetTaskPushNotificationConfigRequest"""
    try:
        # For now, return a default configuration
        return Success({"config": {"enabled": True, "endpoint": ""}})
    except Exception as e:
        return JSONRPCError(code=-32603, message=f"Internal error: {str(e)}")


@method
def TaskResubscriptionRequest(params: Dict[str, Any]) -> Result:
    """Handle JSON-RPC TaskResubscriptionRequest"""
    try:
        # For now, just acknowledge the request
        return Success({"status": "resubscribed"})
    except Exception as e:
        return JSONRPCError(code=-32603, message=f"Internal error: {str(e)}")


# Data models
class Chat(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    agent_id: str


class Message(BaseModel):
    id: str
    chat_id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    files: Optional[List[dict]] = None


class Agent(BaseModel):
    id: str
    name: str
    description: str
    endpoint: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None


class CreateChatRequest(BaseModel):
    title: str
    agent_id: str


class SendMessageRequest(BaseModel):
    content: str
    files: Optional[List[dict]] = None


class RegisterAgentRequest(BaseModel):
    name: str
    description: str
    endpoint: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None


# JSON-RPC endpoint
@app.post("/jsonrpc")
async def jsonrpc_endpoint(request: Request):
    """Handle JSON-RPC requests"""
    try:
        request_json = await request.json()
        response = await jsonrpcserver.dispatch(request_json)
        return response
    except Exception as e:
        # Return a JSON-RPC error response
        error_response = {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            "id": None,
        }
        return error_response


# Initialize with example agent
@app.on_event("startup")
def startup_event():
    default_agents = [
        Agent(
            id="cyrano_agent",
            name="Cyrano de Bergerac",
            description="A poetic assistant that responds with eloquent, flowery language",
            endpoint="http://localhost:8001",
            input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"response": {"type": "string"}}},
        ),
        Agent(
            id="claude_agent",
            name="Claude",
            description="Anthropic Claude — claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001",
            endpoint="http://localhost:8002",
            input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"response": {"type": "string"}}},
        ),
        Agent(
            id="chatgpt_agent",
            name="ChatGPT",
            description="OpenAI ChatGPT — gpt-4o, gpt-4o-mini, gpt-5.2",
            endpoint="http://localhost:8003",
            input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"response": {"type": "string"}}},
        ),
        Agent(
            id="gemini_agent",
            name="Gemini",
            description="Google Gemini — gemini-2.5-pro, gemini-2.5-flash, gemini-2.0-flash",
            endpoint="http://localhost:8004",
            input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"response": {"type": "string"}}},
        ),
    ]
    for agent in default_agents:
        agents_db.append(agent.dict())


# Chat endpoints
@app.get("/")
def read_root():
    return {"message": "OpenBeavs Backend - Ready!"}


@app.get("/health")
def health_check():
    return {"status": "ok", "agents": len(agents_db)}


@app.get("/chats", response_model=List[Chat])
def get_chats():
    """Get all chat threads"""
    return [Chat(**chat_data) for chat_data in chats_db.values()]


@app.post("/chats", response_model=Chat)
def create_chat(chat_request: CreateChatRequest):
    """Create a new chat thread"""
    chat_id = str(uuid.uuid4())

    # Verify agent exists
    agent_exists = any(agent["id"] == chat_request.agent_id for agent in agents_db)
    if not agent_exists:
        raise HTTPException(status_code=404, detail="Agent not found")

    chat = Chat(
        id=chat_id,
        title=chat_request.title,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        agent_id=chat_request.agent_id,
    )

    chats_db[chat_id] = chat.dict()
    messages_db[chat_id] = []

    return chat


@app.get("/chats/{chat_id}", response_model=Chat)
def get_chat(chat_id: str):
    """Get a specific chat thread"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")

    return Chat(**chats_db[chat_id])


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str):
    """Delete a chat thread"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")

    del chats_db[chat_id]
    if chat_id in messages_db:
        del messages_db[chat_id]

    return {"message": "Chat deleted successfully"}


# Message endpoints
@app.get("/chats/{chat_id}/messages", response_model=List[Message])
def get_messages(chat_id: str):
    """Get all messages in a chat thread"""
    if chat_id not in messages_db:
        raise HTTPException(status_code=404, detail="Chat not found")

    return [Message(**msg) for msg in messages_db[chat_id]]


@app.post("/chats/{chat_id}/messages", response_model=Message)
def send_message(chat_id: str, message_request: SendMessageRequest):
    """Send a message to a chat and get a response"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Add user message
    user_message = Message(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="user",
        content=message_request.content,
        timestamp=datetime.now(),
        files=message_request.files,
    )

    messages_db[chat_id].append(user_message.dict())

    # Get the agent for this chat
    chat_agent_id = chats_db[chat_id]["agent_id"]
    agent = next((a for a in agents_db if a["id"] == chat_agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Generate response from agent - for external agents with endpoints, make HTTP request
    response_content = generate_agent_response(message_request.content, agent)

    # Add assistant message
    assistant_message = Message(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        role="assistant",
        content=response_content,
        timestamp=datetime.now(),
    )

    messages_db[chat_id].append(assistant_message.dict())

    # Update chat timestamp
    chats_db[chat_id]["updated_at"] = datetime.now()

    return assistant_message


# Agent endpoints
@app.get("/agents", response_model=List[Agent])
def get_agents():
    """Get all registered agents"""
    return [Agent(**agent_data) for agent_data in agents_db]


@app.post("/agents/register", response_model=Agent)
def register_agent(agent_request: RegisterAgentRequest):
    """Register a new agent"""
    agent_id = str(uuid.uuid4())

    agent = Agent(
        id=agent_id,
        name=agent_request.name,
        description=agent_request.description,
        endpoint=agent_request.endpoint,
        input_schema=agent_request.input_schema,
        output_schema=agent_request.output_schema,
    )

    agents_db.append(agent.dict())
    return agent


# Endpoint to register an agent using its .well-known/agent.json file
# Example of a valid agent.json: https://hello-world-gxfr.onrender.com/.well-known/agent.json
class RegisterAgentByUrlRequest(BaseModel):
    agent_url: str


@app.post("/agents/register-by-url", response_model=Agent)
def register_agent_by_url(request_data: RegisterAgentByUrlRequest):
    """Register a new agent by fetching its .well-known/agent.json file"""
    import requests
    from urllib.parse import urljoin, urlparse

    agent_url = request_data.agent_url

    if not agent_url:
        raise HTTPException(status_code=400, detail="Agent URL is required")

    # Ensure the URL has proper scheme
    if not agent_url.startswith(("http://", "https://")):
        agent_url = "https://" + agent_url

    # Parse the URL and normalize it to just the domain for the well-known file
    parsed_url = urlparse(agent_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    well_known_url = f"{base_url}/.well-known/agent.json"

    try:
        response = requests.get(well_known_url, timeout=10)
        response.raise_for_status()

        agent_data = response.json()

        # Map the well-known format to our internal Agent model
        # Extract name and description from the well-known format
        name = agent_data.get("name", "Unknown Agent")
        description = agent_data.get("description", "")
        endpoint = agent_data.get(
            "url", base_url
        )  # Use the base URL if no explicit endpoint

        # Generate new ID for the agent in our system
        agent_id = str(uuid.uuid4())

        # Create agent with fetched data
        agent = Agent(
            id=agent_id,
            name=name,
            description=description,
            endpoint=endpoint,
            input_schema=agent_data.get(
                "input_schema",
                {"type": "object", "properties": {"message": {"type": "string"}}},
            ),
            output_schema=agent_data.get(
                "output_schema",
                {"type": "object", "properties": {"response": {"type": "string"}}},
            ),
        )

        agents_db.append(agent.dict())
        return agent

    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error fetching agent's .well-known/agent.json file: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON response from agent's .well-known/agent.json file: {str(e)}",
        )


# Endpoint to fetch an agent's .well-known/agent.json file
@app.get("/agents/fetch-well-known")
def fetch_agent_well_known(agent_url: str):
    """Fetch an agent's .well-known/agent.json file"""
    import requests
    from urllib.parse import urljoin, urlparse

    if not agent_url:
        raise HTTPException(status_code=400, detail="Agent URL is required")

    # Ensure the URL has proper scheme
    if not agent_url.startswith(("http://", "https://")):
        agent_url = "https://" + agent_url

    # Parse the URL and normalize it to just the domain for the well-known file
    parsed_url = urlparse(agent_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    well_known_url = f"{base_url}/.well-known/agent.json"

    try:
        response = requests.get(well_known_url, timeout=10)
        response.raise_for_status()

        agent_data = response.json()

        # Convert the well-known format to our internal Agent model format for display
        return {
            "id": "temp_id",  # ID will be generated during actual registration
            "name": agent_data.get("name", "Unknown Agent"),
            "description": agent_data.get("description", ""),
            "endpoint": agent_data.get("url", base_url),
            "input_schema": agent_data.get(
                "input_schema",
                {"type": "object", "properties": {"message": {"type": "string"}}},
            ),
            "output_schema": agent_data.get(
                "output_schema",
                {"type": "object", "properties": {"response": {"type": "string"}}},
            ),
        }
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error fetching agent's .well-known/agent.json file: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON response from agent's .well-known/agent.json file: {str(e)}",
        )


def generate_agent_response(user_message: str, agent: dict) -> str:
    """Generate response from an agent based on user message"""
    import requests, uuid, random

    # If the agent has an endpoint, make an HTTP request to it
    if agent.get("endpoint"):
        try:
            agent_endpoint = agent["endpoint"]

            # ✅ Build the proper JSON-RPC request
            agent_request_data = {
                "jsonrpc": "2.0",
                "method": "message/send",  # must be literal 'message/send'
                "params": {
                    "message": {
                        # Required by schema
                        "messageId": str(uuid.uuid4()),  # unique ID for each message
                        "role": "user",
                        # 'parts' must be a list of objects (not a single string)
                        "parts": [{"text": user_message, "type": "text"}],
                    }
                },
                "id": 1,
            }

            # Make the API call to the external agent
            response = requests.post(
                agent_endpoint, json=agent_request_data, timeout=30
            )

            if response.status_code == 200:
                response_data = response.json()

                # Try different common response field names based on typical agent APIs
                if isinstance(response_data, str):
                    return response_data
                elif "response" in response_data:
                    return response_data["response"]
                elif "output" in response_data:
                    return response_data["output"]
                elif "content" in response_data:
                    return response_data["content"]
                elif "message" in response_data:
                    return response_data["message"]
                elif isinstance(response_data, dict) and len(response_data) == 1:
                    return list(response_data.values())[0]
                else:
                    return str(response_data)
            else:
                return (
                    f"Error contacting agent: {response.status_code} - {response.text}"
                )

        except requests.exceptions.RequestException as e:
            return f"Connection error with agent: {str(e)}"
        except Exception as e:
            return f"Error processing agent response: {str(e)}"

    # Fallback to built-in agents if no endpoint is provided
    if agent["id"] == "cyrano_agent":
        response_templates = [
            f"Ah, dear interlocutor, what you speak of '{user_message}' doth stir within me thoughts most profound...",
            f"'{user_message}', you say? How wondrous that fate hath brought us to discourse upon such matters...",
            f"With quill in hand and thoughts aflutter, I ponder your words '{user_message}' with the reverence they deserve...",
            f"Verily, your inquiry regarding '{user_message}' doth remind me of the beauty that lies in thoughtful contemplation...",
            f"In the symphony of discourse, your words '{user_message}' play a melody both sweet and intriguing...",
        ]
        return random.choice(response_templates)
    else:
        return f"I'm {agent['name']}. You said: '{user_message}'. How may I assist you?"


