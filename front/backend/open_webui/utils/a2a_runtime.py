"""Internal A2A runtime — turns (system_prompt, user_message) into a reply.

Used by the Agent Deploy View MVP so the hub itself can serve internally-hosted
A2A agents without spinning up a separate process per agent. Dispatches to the
Anthropic, OpenAI, or Gemini provider based on agent configuration.
"""

import logging
import os
from typing import Optional

from fastapi import HTTPException

from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


PROVIDER_DEFAULTS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
}

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _require_key(env_var: str) -> str:
    key = os.environ.get(env_var)
    if not key:
        raise HTTPException(
            status_code=502,
            detail=f"{env_var} is not set on the hub; cannot run internal agent",
        )
    return key


async def run_agent_turn(
    provider: str,
    model: str,
    system_prompt: str,
    user_message: str,
) -> str:
    """Call the configured LLM provider with a system prompt and a user message.

    Returns the assistant's text reply. Raises HTTPException(502) on
    upstream failures or missing API keys.
    """
    provider = (provider or "anthropic").lower()
    model = model or PROVIDER_DEFAULTS.get(provider)
    if not model:
        raise HTTPException(
            status_code=400, detail=f"Unknown provider '{provider}'"
        )

    try:
        if provider == "anthropic":
            return _run_anthropic(model, system_prompt, user_message)
        if provider == "openai":
            return _run_openai(model, system_prompt, user_message)
        if provider == "gemini":
            return _run_gemini(model, system_prompt, user_message)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Internal agent LLM call failed")
        raise HTTPException(status_code=502, detail=f"Agent runtime error: {e}")

    raise HTTPException(
        status_code=400, detail=f"Unsupported provider '{provider}'"
    )


def _run_anthropic(model: str, system_prompt: str, user_message: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=_require_key("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt or "",
        messages=[{"role": "user", "content": user_message}],
    )
    parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
    return "".join(parts).strip()


def _openai_chat(base_url: Optional[str], api_key: str, model: str,
                 system_prompt: str, user_message: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})
    resp = client.chat.completions.create(model=model, messages=messages)
    return (resp.choices[0].message.content or "").strip()


def _run_openai(model: str, system_prompt: str, user_message: str) -> str:
    return _openai_chat(None, _require_key("OPENAI_API_KEY"), model, system_prompt, user_message)


def _run_gemini(model: str, system_prompt: str, user_message: str) -> str:
    return _openai_chat(
        GEMINI_OPENAI_BASE_URL,
        _require_key("GEMINI_API_KEY"),
        model,
        system_prompt,
        user_message,
    )
