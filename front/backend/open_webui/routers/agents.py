import uuid
import json
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
import requests

from open_webui.models.agents import (
    AgentModel,
    AgentResponse,
    RegisterAgentForm,
    RegisterAgentByUrlForm,
    AgentUpdateForm,
    Agents,
)
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_admin_user, get_verified_user

router = APIRouter()

############################
# JSON-RPC Message Models
############################


class JSONRPCMessage(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any]
    id: Optional[int] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[int] = None


class A2AMessagePart(BaseModel):
    text: str
    type: str = "text"


class A2AMessage(BaseModel):
    messageId: str
    role: str
    parts: List[A2AMessagePart]


class SendMessageToAgentForm(BaseModel):
    message: str
    chat_id: Optional[str] = None


############################
# GetAgents
############################


@router.get("/", response_model=List[AgentResponse])
async def get_agents(user=Depends(get_verified_user)):
    """Get all active agents"""
    agents = Agents.get_agents()
    return [AgentResponse(**agent.model_dump()) for agent in agents]


@router.get("/all", response_model=List[AgentModel])
async def get_all_agents(user=Depends(get_admin_user)):
    """Get all agents including inactive (admin only)"""
    agents = Agents.get_all_agents()
    return agents


############################
# GetAgentById
############################


@router.get("/{agent_id}", response_model=AgentModel)
async def get_agent_by_id(agent_id: str, user=Depends(get_verified_user)):
    """Get a specific agent by ID"""
    agent = Agents.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    return agent


############################
# RegisterAgent
############################

@router.post("/register", response_model=AgentModel)
async def register_agent(
    form_data: RegisterAgentForm,
    user=Depends(get_verified_user),
):
    """Register a new agent manually"""
    agent_id = str(uuid.uuid4())

    agent = Agents.insert_new_agent(
        id=agent_id,
        name=form_data.name,
        description=form_data.description,
        endpoint=form_data.endpoint,
        input_schema=form_data.input_schema,
        output_schema=form_data.output_schema,
        user_id=user.id,
    )

    if agent:
        return agent
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.DEFAULT(),
    )


############################
# RegisterAgentByUrl
############################


@router.post("/register-by-url", response_model=AgentModel)
async def register_agent_by_url(
    form_data: RegisterAgentByUrlForm,
    user=Depends(get_verified_user),
):
    """Register a new agent by fetching its .well-known/agent.json file"""
    agent_url = form_data.agent_url

    if not agent_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent URL is required",
        )

    # Ensure the URL has proper scheme
    if not agent_url.startswith(("http://", "https://")):
        agent_url = "https://" + agent_url

    # If the URL already points to a well-known card, use it directly.
    # Otherwise construct the standard path from the base domain.
    parsed_url = urlparse(agent_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    if "/.well-known/" in agent_url:
        well_known_url = agent_url
    else:
        well_known_url = f"{base_url}/.well-known/agent.json"

    try:
        response = requests.get(well_known_url, timeout=10)
        response.raise_for_status()
        agent_data = response.json()

        # Extract information from well-known format
        name = agent_data.get("name", "Unknown Agent")
        description = agent_data.get("description", "")
        url = agent_data.get("url") or base_url
        version = agent_data.get("version", "1.0.0")
        capabilities = agent_data.get("capabilities", {})
        skills = agent_data.get("skills", [])
        default_input_modes = agent_data.get("defaultInputModes", ["text"])
        default_output_modes = agent_data.get("defaultOutputModes", ["text"])

        # Derive the A2A JSON-RPC endpoint from the well-known URL path.
        # ADK agents host their RPC handler at the path prefix before /.well-known/,
        # not at the base domain root (e.g. /a2a/trivia_agent/ not /).
        if "/.well-known/" in well_known_url:
            rpc_endpoint = well_known_url[: well_known_url.index("/.well-known/")] + "/"
        else:
            rpc_endpoint = base_url + "/"

        # Use provided profile image or default to favicon
        profile_image_url = form_data.profile_image_url or agent_data.get("profileImageUrl") or "/static/favicon.png"

        # Check if agent with this URL already exists
        existing_agent = Agents.get_agent_by_url(url)
        if existing_agent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An agent with this URL is already registered",
            )

        # Generate a unique ID for the agent
        agent_id = str(uuid.uuid4())

        # Insert the agent into the database
        agent = Agents.insert_new_agent(
            id=agent_id,
            name=name,
            description=description,
            url=url,
            endpoint=rpc_endpoint,
            version=version,
            capabilities=capabilities,
            skills=skills,
            default_input_modes=default_input_modes,
            default_output_modes=default_output_modes,
            profile_image_url=profile_image_url,
            user_id=user.id,
        )
        
        if agent:
            return agent
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(),
        )
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching agent's .well-known/agent.json file: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON response from agent: {str(e)}",
        )


############################
# FetchWellKnown
############################


@router.get("/fetch-well-known")
async def fetch_agent_well_known(agent_url: str, user=Depends(get_verified_user)):
    """Fetch an agent's .well-known/agent.json file without registering"""
    if not agent_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent URL is required",
        )

    # Ensure the URL has proper scheme
    if not agent_url.startswith(("http://", "https://")):
        agent_url = "https://" + agent_url

    parsed_url = urlparse(agent_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    if "/.well-known/" in agent_url:
        well_known_url = agent_url
    else:
        well_known_url = f"{base_url}/.well-known/agent.json"

    try:
        response = requests.get(well_known_url, timeout=10)
        response.raise_for_status()
        agent_data = response.json()
        return agent_data
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching agent's .well-known/agent.json: {str(e)}",
        )


############################
# UpdateAgent
############################


@router.patch("/{agent_id}", response_model=AgentModel)
async def update_agent(
    agent_id: str,
    form_data: AgentUpdateForm,
    user=Depends(get_verified_user),
):
    """Update an agent"""
    agent = Agents.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Check if user has permission (owner or admin)
    if user.role != "admin" and agent.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    updated_agent = Agents.update_agent_by_id(agent_id, form_data)
    if updated_agent:
        return updated_agent
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.DEFAULT(),
    )


############################
# DeleteAgent
############################


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, user=Depends(get_verified_user)):
    """Delete an agent"""
    agent = Agents.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Check if user has permission (owner or admin)
    if user.role != "admin" and agent.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    result = Agents.delete_agent_by_id(agent_id)
    if result:
        return {"success": True, "message": "Agent deleted successfully"}
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.DEFAULT(),
    )


############################
# SendMessageToAgent
############################


@router.post("/{agent_id}/message")
async def send_message_to_agent(
    agent_id: str,
    form_data: SendMessageToAgentForm,
    user=Depends(get_verified_user),
):
    """Send a message to an A2A agent using JSON-RPC protocol"""
    agent = Agents.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    if not agent.endpoint and not agent.url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent has no endpoint configured",
        )

    endpoint = agent.endpoint or agent.url

    # Build JSON-RPC request following A2A protocol
    message_id = str(uuid.uuid4())
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [{"text": form_data.message, "type": "text"}],
            }
        },
        "id": 1,
    }

    try:
        # Send request to external agent
        response = requests.post(endpoint, json=jsonrpc_request, timeout=30)
        response.raise_for_status()

        response_data = response.json()
        return {
            "success": True,
            "agent_response": response_data,
            "message_id": message_id,
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error communicating with agent: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing agent response: {str(e)}",
        )


############################
# GetAgentsAsModels
############################


@router.get("/models")
async def get_agents_as_models(user=Depends(get_verified_user)):
    """Get all active agents formatted as models for the chat interface"""
    agents = Agents.get_agents()

    models = []
    for agent in agents:
        model_id = f"agent:{agent.id}"
        models.append({
            "id": model_id,
            "name": agent.name,
            "object": "model",
            "created": agent.created_at,
            "owned_by": "a2a-agent",
            "agent": {
                "id": agent.id,
                "description": agent.description,
                "endpoint": agent.endpoint or agent.url,
                "capabilities": agent.capabilities,
                "skills": agent.skills,
            },
            "info": {
                "meta": {
                    "description": agent.description,
                    "capabilities": agent.capabilities,
                }
            }
        })

    return {"data": models}
