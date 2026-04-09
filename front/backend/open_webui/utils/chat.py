import time
import logging
import sys

from typing import Any, Optional
import random
import json
import inspect
import uuid
import asyncio

from fastapi import Request, status
from starlette.responses import Response, StreamingResponse


from open_webui.models.users import UserModel

from open_webui.socket.main import (
    sio,
    get_event_call,
    get_event_emitter,
)
from open_webui.functions import generate_function_chat_completion

from open_webui.routers.openai import (
    generate_chat_completion as generate_openai_chat_completion,
)

from open_webui.routers.ollama import (
    generate_chat_completion as generate_ollama_chat_completion,
)

from open_webui.routers.pipelines import (
    process_pipeline_inlet_filter,
    process_pipeline_outlet_filter,
)


from open_webui.models.functions import Functions
from open_webui.models.models import Models


from open_webui.utils.plugin import load_function_module_by_id
from open_webui.utils.models import get_all_models, check_model_access
from open_webui.utils.payload import convert_payload_openai_to_ollama
from open_webui.utils.response import (
    convert_response_ollama_to_openai,
    convert_streaming_response_ollama_to_openai,
)
from open_webui.utils.filter import (
    get_sorted_filter_ids,
    process_filter_functions,
)

from open_webui.env import SRC_LOG_LEVELS, GLOBAL_LOG_LEVEL, BYPASS_MODEL_ACCESS_CONTROL


logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


async def generate_a2a_agent_chat_completion(
    request: Request,
    form_data: dict,
    user: Any,
    model: dict,
):
    """Generate chat completion using A2A protocol"""
    log.info("generate_a2a_agent_chat_completion")

    import requests as req

    # Extract agent information
    agent_info = model.get("agent", {})
    agent_endpoint = agent_info.get("endpoint")

    if not agent_endpoint:
        raise Exception("Agent endpoint not configured")

    # Google ADK agents use root path for JSON-RPC, not /jsonrpc
    # Just use the endpoint as-is (e.g., http://localhost:8001)
    agent_endpoint = agent_endpoint.rstrip('/')

    log.info(f"Sending A2A request to: {agent_endpoint}")

    # Get the last user message from form_data
    messages = form_data.get("messages", [])
    if not messages:
        raise Exception("No messages provided")

    # Get the last message content
    last_message = messages[-1]
    user_message_content = last_message.get("content", "")

    # Build JSON-RPC request following A2A protocol
    message_id = str(uuid.uuid4())
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "messageId": message_id,  # Top-level messageId required by A2A spec
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [{"text": user_message_content}],  # Remove "type" field
            }
        },
        "id": 1,
    }

    log.debug(f"JSON-RPC request: {jsonrpc_request}")

    if form_data.get("stream"):
        # For streaming, we'll make a non-streaming request and stream the response
        # A2A protocol doesn't necessarily support streaming, so we convert
        try:
            response = req.post(agent_endpoint, json=jsonrpc_request, timeout=60)
            response.raise_for_status()
            response_data = response.json()

            # Extract the response text from JSON-RPC result
            result = response_data.get("result", {})
            response_text = ""

            # A2A response format: result.artifacts[0].parts[0].text
            if isinstance(result, dict) and "artifacts" in result:
                artifacts = result.get("artifacts", [])
                if artifacts and len(artifacts) > 0:
                    artifact_parts = artifacts[0].get("parts", [])
                    if artifact_parts and len(artifact_parts) > 0:
                        response_text = artifact_parts[0].get("text", "")

            # Fallback to old format if new format doesn't work
            if not response_text and isinstance(result, dict):
                parts = result.get("parts", [])
                if parts and isinstance(parts, list):
                    response_text = parts[0].get("text", str(result))
                else:
                    response_text = result.get("text", str(result))
            elif not response_text:
                response_text = str(result)

            # Create OpenAI-compatible streaming response
            async def stream_response():
                chunk_id = f"chatcmpl-{uuid.uuid4()}"
                # Send the response as chunks
                words = response_text.split()
                for i, word in enumerate(words):
                    chunk = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": form_data.get("model"),
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": word + " " if i < len(words) - 1 else word},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    await asyncio.sleep(0.01)

                # Send final chunk
                final_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": form_data.get("model"),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
            )

        except Exception as e:
            log.error(f"Error communicating with A2A agent: {e}")
            raise Exception(f"Error communicating with agent: {str(e)}")

    else:
        # Non-streaming response
        try:
            response = req.post(agent_endpoint, json=jsonrpc_request, timeout=60)
            response.raise_for_status()
            response_data = response.json()

            # Extract the response text from JSON-RPC result
            result = response_data.get("result", {})
            response_text = ""

            # A2A response format: result.artifacts[0].parts[0].text
            if isinstance(result, dict) and "artifacts" in result:
                artifacts = result.get("artifacts", [])
                if artifacts and len(artifacts) > 0:
                    artifact_parts = artifacts[0].get("parts", [])
                    if artifact_parts and len(artifact_parts) > 0:
                        response_text = artifact_parts[0].get("text", "")

            # Fallback to old format if new format doesn't work
            if not response_text and isinstance(result, dict):
                parts = result.get("parts", [])
                if parts and isinstance(parts, list):
                    response_text = parts[0].get("text", str(result))
                else:
                    response_text = result.get("text", str(result))
            elif not response_text:
                response_text = str(result)

            # Return OpenAI-compatible format
            return {
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": form_data.get("model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": response_text,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }

        except Exception as e:
            log.error(f"Error communicating with A2A agent: {e}")
            raise Exception(f"Error communicating with agent: {str(e)}")


async def generate_direct_chat_completion(
    request: Request,
    form_data: dict,
    user: Any,
    models: dict,
):
    log.info("generate_direct_chat_completion")

    metadata = form_data.pop("metadata", {})

    user_id = metadata.get("user_id")
    session_id = metadata.get("session_id")
    request_id = str(uuid.uuid4())  # Generate a unique request ID

    event_caller = get_event_call(metadata)

    channel = f"{user_id}:{session_id}:{request_id}"

    if form_data.get("stream"):
        q = asyncio.Queue()

        async def message_listener(sid, data):
            """
            Handle received socket messages and push them into the queue.
            """
            await q.put(data)

        # Register the listener
        sio.on(channel, message_listener)

        # Start processing chat completion in background
        res = await event_caller(
            {
                "type": "request:chat:completion",
                "data": {
                    "form_data": form_data,
                    "model": models[form_data["model"]],
                    "channel": channel,
                    "session_id": session_id,
                },
            }
        )

        log.info(f"res: {res}")

        if res.get("status", False):
            # Define a generator to stream responses
            async def event_generator():
                nonlocal q
                try:
                    while True:
                        data = await q.get()  # Wait for new messages
                        if isinstance(data, dict):
                            if "done" in data and data["done"]:
                                break  # Stop streaming when 'done' is received

                            yield f"data: {json.dumps(data)}\n\n"
                        elif isinstance(data, str):
                            yield data
                except Exception as e:
                    log.debug(f"Error in event generator: {e}")
                    pass

            # Define a background task to run the event generator
            async def background():
                try:
                    del sio.handlers["/"][channel]
                except Exception as e:
                    pass

            # Return the streaming response
            return StreamingResponse(
                event_generator(), media_type="text/event-stream", background=background
            )
        else:
            raise Exception(str(res))
    else:
        res = await event_caller(
            {
                "type": "request:chat:completion",
                "data": {
                    "form_data": form_data,
                    "model": models[form_data["model"]],
                    "channel": channel,
                    "session_id": session_id,
                },
            }
        )

        if "error" in res and res["error"]:
            raise Exception(res["error"])

        return res


async def generate_chat_completion(
    request: Request,
    form_data: dict,
    user: Any,
    bypass_filter: bool = False,
):
    log.debug(f"generate_chat_completion: {form_data}")
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    if hasattr(request.state, "metadata"):
        if "metadata" not in form_data:
            form_data["metadata"] = request.state.metadata
        else:
            form_data["metadata"] = {
                **form_data["metadata"],
                **request.state.metadata,
            }

    if getattr(request.state, "direct", False) and hasattr(request.state, "model"):
        models = {
            request.state.model["id"]: request.state.model,
        }
        log.debug(f"direct connection to model: {models}")
    else:
        models = request.app.state.MODELS

    model_id = form_data["model"]
    log.info(f"Chat request for model_id: {model_id}")

    # Check if this is an A2A agent model
    if model_id.startswith("agent:"):
        from open_webui.models.agents import Agents

        agent_id = model_id.replace("agent:", "")
        log.info(f"A2A agent request detected. Agent ID: {agent_id}")
        agent = Agents.get_agent_by_id(agent_id)

        if not agent:
            log.error(f"Agent not found in database: {agent_id}")
            raise Exception("Agent not found")

        log.info(f"Found agent: {agent.name} at {agent.endpoint or agent.url}")

        # Construct model object for agent
        model = {
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
            }
        }
    elif model_id not in models:
        raise Exception("Model not found")
    else:
        model = models[model_id]

    if getattr(request.state, "direct", False):
        return await generate_direct_chat_completion(
            request, form_data, user=user, models=models
        )
    else:
        # Check if user has access to the model
        if not bypass_filter and user.role == "user":
            try:
                check_model_access(user, model)
            except Exception as e:
                raise e

        if model.get("owned_by") == "arena":
            model_ids = model.get("info", {}).get("meta", {}).get("model_ids")
            filter_mode = model.get("info", {}).get("meta", {}).get("filter_mode")
            if model_ids and filter_mode == "exclude":
                model_ids = [
                    model["id"]
                    for model in list(request.app.state.MODELS.values())
                    if model.get("owned_by") != "arena" and model["id"] not in model_ids
                ]

            selected_model_id = None
            if isinstance(model_ids, list) and model_ids:
                selected_model_id = random.choice(model_ids)
            else:
                model_ids = [
                    model["id"]
                    for model in list(request.app.state.MODELS.values())
                    if model.get("owned_by") != "arena"
                ]
                selected_model_id = random.choice(model_ids)

            form_data["model"] = selected_model_id

            if form_data.get("stream") == True:

                async def stream_wrapper(stream):
                    yield f"data: {json.dumps({'selected_model_id': selected_model_id})}\n\n"
                    async for chunk in stream:
                        yield chunk

                response = await generate_chat_completion(
                    request, form_data, user, bypass_filter=True
                )
                return StreamingResponse(
                    stream_wrapper(response.body_iterator),
                    media_type="text/event-stream",
                    background=response.background,
                )
            else:
                return {
                    **(
                        await generate_chat_completion(
                            request, form_data, user, bypass_filter=True
                        )
                    ),
                    "selected_model_id": selected_model_id,
                }

        if model.get("owned_by") == "a2a-agent":
            # Route to A2A agent
            log.info(f"Routing to A2A agent handler for model: {model.get('name')}")
            return await generate_a2a_agent_chat_completion(
                request, form_data, user=user, model=model
            )

        if model.get("pipe"):
            # Below does not require bypass_filter because this is the only route the uses this function and it is already bypassing the filter
            return await generate_function_chat_completion(
                request, form_data, user=user, models=models
            )
        if model.get("owned_by") == "ollama":
            # Using /ollama/api/chat endpoint
            form_data = convert_payload_openai_to_ollama(form_data)
            response = await generate_ollama_chat_completion(
                request=request,
                form_data=form_data,
                user=user,
                bypass_filter=bypass_filter,
            )
            if form_data.get("stream"):
                response.headers["content-type"] = "text/event-stream"
                return StreamingResponse(
                    convert_streaming_response_ollama_to_openai(response),
                    headers=dict(response.headers),
                    background=response.background,
                )
            else:
                return convert_response_ollama_to_openai(response)
        else:
            return await generate_openai_chat_completion(
                request=request,
                form_data=form_data,
                user=user,
                bypass_filter=bypass_filter,
            )


chat_completion = generate_chat_completion


async def chat_completed(request: Request, form_data: dict, user: Any):
    if not request.app.state.MODELS:
        await get_all_models(request, user=user)

    if getattr(request.state, "direct", False) and hasattr(request.state, "model"):
        models = {
            request.state.model["id"]: request.state.model,
        }
    else:
        models = request.app.state.MODELS

    data = form_data
    model_id = data["model"]
    if model_id not in models:
        raise Exception("Model not found")

    model = models[model_id]

    try:
        data = await process_pipeline_outlet_filter(request, data, user, models)
    except Exception as e:
        return Exception(f"Error: {e}")

    metadata = {
        "chat_id": data["chat_id"],
        "message_id": data["id"],
        "session_id": data["session_id"],
        "user_id": user.id,
    }

    extra_params = {
        "__event_emitter__": get_event_emitter(metadata),
        "__event_call__": get_event_call(metadata),
        "__user__": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
        "__metadata__": metadata,
        "__request__": request,
        "__model__": model,
    }

    try:
        filter_functions = [
            Functions.get_function_by_id(filter_id)
            for filter_id in get_sorted_filter_ids(model)
        ]

        result, _ = await process_filter_functions(
            request=request,
            filter_functions=filter_functions,
            filter_type="outlet",
            form_data=data,
            extra_params=extra_params,
        )
        return result
    except Exception as e:
        return Exception(f"Error: {e}")


async def chat_action(request: Request, action_id: str, form_data: dict, user: Any):
    if "." in action_id:
        action_id, sub_action_id = action_id.split(".")
    else:
        sub_action_id = None

    action = Functions.get_function_by_id(action_id)
    if not action:
        raise Exception(f"Action not found: {action_id}")

    if not request.app.state.MODELS:
        await get_all_models(request, user=user)

    if getattr(request.state, "direct", False) and hasattr(request.state, "model"):
        models = {
            request.state.model["id"]: request.state.model,
        }
    else:
        models = request.app.state.MODELS

    data = form_data
    model_id = data["model"]

    if model_id not in models:
        raise Exception("Model not found")
    model = models[model_id]

    __event_emitter__ = get_event_emitter(
        {
            "chat_id": data["chat_id"],
            "message_id": data["id"],
            "session_id": data["session_id"],
            "user_id": user.id,
        }
    )
    __event_call__ = get_event_call(
        {
            "chat_id": data["chat_id"],
            "message_id": data["id"],
            "session_id": data["session_id"],
            "user_id": user.id,
        }
    )

    if action_id in request.app.state.FUNCTIONS:
        function_module = request.app.state.FUNCTIONS[action_id]
    else:
        function_module, _, _ = load_function_module_by_id(action_id)
        request.app.state.FUNCTIONS[action_id] = function_module

    if hasattr(function_module, "valves") and hasattr(function_module, "Valves"):
        valves = Functions.get_function_valves_by_id(action_id)
        function_module.valves = function_module.Valves(**(valves if valves else {}))

    if hasattr(function_module, "action"):
        try:
            action = function_module.action

            # Get the signature of the function
            sig = inspect.signature(action)
            params = {"body": data}

            # Extra parameters to be passed to the function
            extra_params = {
                "__model__": model,
                "__id__": sub_action_id if sub_action_id is not None else action_id,
                "__event_emitter__": __event_emitter__,
                "__event_call__": __event_call__,
                "__request__": request,
            }

            # Add extra params in contained in function signature
            for key, value in extra_params.items():
                if key in sig.parameters:
                    params[key] = value

            if "__user__" in sig.parameters:
                __user__ = {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "role": user.role,
                }

                try:
                    if hasattr(function_module, "UserValves"):
                        __user__["valves"] = function_module.UserValves(
                            **Functions.get_user_valves_by_id_and_user_id(
                                action_id, user.id
                            )
                        )
                except Exception as e:
                    log.exception(f"Failed to get user values: {e}")

                params = {**params, "__user__": __user__}

            if inspect.iscoroutinefunction(action):
                data = await action(**params)
            else:
                data = action(**params)

        except Exception as e:
            return Exception(f"Error: {e}")

    return data
