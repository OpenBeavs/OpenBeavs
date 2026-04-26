"""Hub-side helper for provisioning per-agent Cloud Run services.

Wraps :func:`agents.deploy_agent.deploy_agent_to_cloud_run` from the
top-level ``agents/`` directory and picks the right provider source dir
(``agents/claude-agent``, ``agents/chatgpt-agent``,
``agents/gemini-agent``) based on the form's ``provider`` field.

Set ``OPENBEAVS_CLOUD_RUN_DISABLED=1`` on dev/no-creds installs to make
the router fall back to the existing internal-mode handler instead of
attempting a real deploy. Without that flag, callers must have
``gcloud`` on PATH and a default project configured.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

from open_webui.env import BASE_DIR


_PROVIDER_DIRS: Mapping[str, str] = {
    "anthropic": "claude-agent",
    "openai": "chatgpt-agent",
    "gemini": "gemini-agent",
}

_PROVIDER_SECRET_ENV: Mapping[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "CHATGPT_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

_PROVIDER_SECRET_DEFAULT_NAME: Mapping[str, str] = {
    "anthropic": "anthropic-api-key",
    "openai": "openai-api-key",
    "gemini": "gemini-api-key",
}


class CloudRunDisabled(RuntimeError):
    """Raised when Cloud Run deploys are disabled in this environment."""


def _agents_dir() -> Path:
    override = os.environ.get("OPENBEAVS_AGENTS_DIR")
    if override:
        return Path(override).resolve()
    return (BASE_DIR.parent / "agents").resolve()


def _service_name(agent_id: str) -> str:
    # Cloud Run service names must be <=49 chars, lowercase, start with a
    # letter, and contain only letters/digits/hyphens. Agent UUIDs are 36
    # hex+hyphens — start with a fixed letter prefix to satisfy the rule.
    safe = agent_id.lower()
    return f"a-{safe}"[:49]


def _load_agents_module():
    agents_dir = _agents_dir()
    repo_root = str(agents_dir.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from agents import deploy_agent  # type: ignore

    return deploy_agent


def _cloud_run_deploy_error_cls():
    return _load_agents_module().CloudRunDeployError


def deploy_provider_agent(
    agent_id: str,
    *,
    provider: str,
    model: str,
    system_prompt: str,
    profile_image_url: str | None = None,
) -> str:
    """Provision a Cloud Run service for the given internal agent.

    Returns the public service URL. Raises
    :class:`CloudRunDisabled` if the hub is configured to skip Cloud
    Run deploys, and
    :class:`agents.deploy_agent.CloudRunDeployError` on any deploy
    failure.
    """
    if os.environ.get("OPENBEAVS_CLOUD_RUN_DISABLED") == "1":
        raise CloudRunDisabled(
            "Cloud Run deploys are disabled on this hub "
            "(OPENBEAVS_CLOUD_RUN_DISABLED=1). The agent was NOT created. "
            "Uncheck 'Deploy to dedicated Cloud Run service' and submit "
            "again to host the agent inside this hub instance."
        )

    if provider not in _PROVIDER_DIRS:
        raise ValueError(f"Unsupported provider for Cloud Run deploy: {provider}")

    deploy_agent_to_cloud_run = _load_agents_module().deploy_agent_to_cloud_run
    agents_dir = _agents_dir()

    source_dir = agents_dir / _PROVIDER_DIRS[provider]

    env_vars = {
        "MODEL": model,
        "SYSTEM_PROMPT": system_prompt,
    }
    if profile_image_url:
        env_vars["AGENT_PROFILE_IMAGE_URL"] = profile_image_url

    secret_env_name = _PROVIDER_SECRET_ENV[provider]
    secret_name = os.environ.get(
        f"OPENBEAVS_SECRET_{secret_env_name}",
        _PROVIDER_SECRET_DEFAULT_NAME[provider],
    )
    secret_refs = {secret_env_name: f"{secret_name}:latest"}

    return deploy_agent_to_cloud_run(
        _service_name(agent_id),
        source_dir,
        env_vars,
        secret_refs=secret_refs,
        allow_unauthenticated=True,
    )
