"""Cloud Run deploy path — security/regression tests.

Each test maps to an attacker scenario or a real regression we need to
catch on the new ``deploy_to_cloud_run`` code path.

    Attacker -> Goal -> Defended invariant.

All tests mock the gcloud helper. No real GCP calls happen in CI.
"""

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI

from test.util.abstract_integration_test import AbstractIntegrationTest


# Same auth-override helper as test_security_qa.py — overrides only
# get_current_user so role gates still run.
@contextmanager
def mock_current_user_only(app: FastAPI, **kwargs):
    from open_webui.models.users import User
    from open_webui.utils.auth import get_current_user

    def make_user():
        now = int(time.time())
        params = {
            "id": "sec-default",
            "name": "Sec Test",
            "email": "sec@test.local",
            "role": "user",
            "profile_image_url": "/u.png",
            "last_active_at": now,
            "updated_at": now,
            "created_at": now,
            **kwargs,
        }
        return User(**params)

    app.dependency_overrides[get_current_user] = make_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _app():
    from main import app

    return app


def _ensure_agents_module_importable():
    # The conftest fixture imports `main` from `front/backend`, which doesn't
    # have the repo root on sys.path. The runtime helper adds it lazily; for
    # these tests we add it up-front so we can monkeypatch it.
    from open_webui.env import BASE_DIR

    repo_root = str(BASE_DIR.parent.resolve())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def _count_agents():
    from open_webui.internal.db import Session
    from open_webui.models.agents import Agent

    return Session.query(Agent).count()


class TestCloudRunDeployment(AbstractIntegrationTest):
    """Attacker = non-admin (or buggy code path); Goal = trigger a real
    GCP deploy or leak partial state. Invariants:
        1. Only admins can invoke the cloud_run path.
        2. Failed deploys never leave an orphan agent row.
        3. API keys are bound via Secret Manager, not env vars.
        4. The disabled-by-config path returns 503, not 500.
    """

    BASE_PATH = "/api/v1/agents"

    def setup_method(self):
        super().setup_method()
        _ensure_agents_module_importable()
        # Capture calls to the deploy helper so each test can assert on them.
        self.calls: list[dict] = []

    def _payload(self, **overrides):
        payload = {
            "name": "CloudBot",
            "description": "x",
            "system_prompt": "You answer in one sentence.",
            "provider": "anthropic",
            "publish_to_registry": False,
            "deploy_to_cloud_run": True,
        }
        payload.update(overrides)
        return payload

    def _patch_helper(self, monkeypatch, *, side_effect=None, return_url=None):
        """Replace ``deploy_agent_to_cloud_run`` at its module location.

        Captures all positional/keyword args into ``self.calls`` so tests
        can assert on the exact gcloud invocation (source dir, env vars,
        secret refs).
        """
        from open_webui.utils import cloud_run as cloud_run_mod

        deploy_agent_mod = cloud_run_mod._load_agents_module()

        def fake(service_name, source_dir, env_vars, **kwargs):
            self.calls.append(
                {
                    "service_name": service_name,
                    "source_dir": Path(source_dir),
                    "env_vars": dict(env_vars),
                    "kwargs": dict(kwargs),
                }
            )
            if side_effect is not None:
                raise side_effect
            return return_url or "https://cloudbot-1234.us-west1.run.app"

        monkeypatch.setattr(deploy_agent_mod, "deploy_agent_to_cloud_run", fake)
        return deploy_agent_mod

    # -- 1. Admin gate ------------------------------------------------------

    def test_non_admin_cannot_deploy_to_cloud_run(self, monkeypatch):
        """role=user requesting cloud_run mode -> 401, no helper call, no row."""
        self._patch_helper(monkeypatch)

        with mock_current_user_only(_app(), id="bob", role="user"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )

        assert response.status_code == 401
        assert _count_agents() == 0
        assert self.calls == []

    # -- 2. Happy path: provider source dir + env vars ----------------------

    def test_admin_deploy_invokes_gcloud_with_provider_source_dir(self, monkeypatch):
        """role=admin, provider=anthropic -> deploys agents/claude-agent dir,
        DB row stores returned URL, deployment_mode=cloud_run."""
        self._patch_helper(
            monkeypatch, return_url="https://cloudbot.us-west1.run.app"
        )

        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )

        assert response.status_code == 200, response.text
        assert _count_agents() == 1
        assert len(self.calls) == 1
        call = self.calls[0]
        assert call["source_dir"].name == "claude-agent"
        assert call["env_vars"]["SYSTEM_PROMPT"] == "You answer in one sentence."
        assert call["env_vars"]["MODEL"] == "claude-sonnet-4-6"

        body = response.json()
        assert body["endpoint"] == "https://cloudbot.us-west1.run.app"
        assert body["deployment_mode"] == "cloud_run"

    @pytest.mark.parametrize(
        "provider, expected_dir, expected_secret_env",
        [
            ("anthropic", "claude-agent", "ANTHROPIC_API_KEY"),
            ("openai", "chatgpt-agent", "CHATGPT_API_KEY"),
            ("gemini", "gemini-agent", "GEMINI_API_KEY"),
        ],
    )
    def test_each_provider_routes_to_correct_source_dir(
        self, monkeypatch, provider, expected_dir, expected_secret_env
    ):
        """Each supported provider deploys its own dir and binds its own secret."""
        self._patch_helper(monkeypatch)

        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"),
                json=self._payload(provider=provider),
            )

        assert response.status_code == 200, response.text
        call = self.calls[0]
        assert call["source_dir"].name == expected_dir
        secret_refs = call["kwargs"].get("secret_refs") or {}
        assert expected_secret_env in secret_refs
        assert ":latest" in secret_refs[expected_secret_env]

    # -- 3. Secret hygiene --------------------------------------------------

    def test_deploy_uses_secret_refs_not_envvars_for_keys(self, monkeypatch):
        """API key must be bound via --update-secrets, never inlined in env vars.
        Cloud Run revision metadata (and `gcloud run services describe`) leaks
        --set-env-vars values; secret refs are routed through Secret Manager."""
        self._patch_helper(monkeypatch)

        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )

        assert response.status_code == 200, response.text
        call = self.calls[0]

        # Whitelist the env vars we expect; assert no key-shaped entries.
        env = call["env_vars"]
        for forbidden in ("ANTHROPIC_API_KEY", "CHATGPT_API_KEY", "GEMINI_API_KEY"):
            assert forbidden not in env, (
                f"{forbidden} found in --set-env-vars payload; "
                "must be passed via --update-secrets instead"
            )

        secret_refs = call["kwargs"].get("secret_refs") or {}
        assert "ANTHROPIC_API_KEY" in secret_refs

    # -- 4. Failure / rollback ---------------------------------------------

    def test_failed_deploy_creates_no_orphan_row(self, monkeypatch):
        """gcloud non-zero exit -> 502 + zero new agent rows."""
        deploy_agent_mod = self._patch_helper(monkeypatch)
        # Replace the side_effect with a real CloudRunDeployError instance.
        from open_webui.utils import cloud_run as cloud_run_mod

        def boom(*a, **kw):
            self.calls.append({"raised": True, "kwargs": kw})
            raise deploy_agent_mod.CloudRunDeployError("simulated gcloud failure")

        monkeypatch.setattr(deploy_agent_mod, "deploy_agent_to_cloud_run", boom)

        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )

        assert response.status_code == 502
        assert "Cloud Run deploy failed" in response.json().get("detail", "")
        assert _count_agents() == 0

    # -- 5. Disabled-by-config path ----------------------------------------

    def test_cloud_run_disabled_returns_503(self, monkeypatch):
        """OPENBEAVS_CLOUD_RUN_DISABLED=1 + deploy_to_cloud_run=True -> 503,
        no helper call, no agent row. Hub stays usable in dev."""
        self._patch_helper(monkeypatch)
        monkeypatch.setenv("OPENBEAVS_CLOUD_RUN_DISABLED", "1")

        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )

        assert response.status_code == 503
        assert _count_agents() == 0
        assert self.calls == []

    # -- 6. Internal-mode path is unchanged --------------------------------

    def test_internal_mode_still_works_when_flag_off(self, monkeypatch):
        """deploy_to_cloud_run omitted -> internal mode, no gcloud call."""
        self._patch_helper(monkeypatch)

        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"),
                json=self._payload(deploy_to_cloud_run=False),
            )

        assert response.status_code == 200, response.text
        assert _count_agents() == 1
        assert self.calls == []
        body = response.json()
        assert body["deployment_mode"] == "internal"
        assert "/internal-a2a" in body["endpoint"]


class TestInternalModeChatShortCircuit(AbstractIntegrationTest):
    """Internal-mode chat must dispatch in-process, never HTTPS-self-call.

    Regression for the prod 60s ReadTimeout: the hub stored agent.endpoint as
    its own URL, so chatting hit ``requests.post(<self>)`` with a 60s deadline
    and a no-API-key-on-hub failure mode. The fix detects deployment_mode in
    ``generate_chat_completion`` and calls ``run_agent_turn`` directly.
    """

    BASE_PATH = "/api/v1/agents"

    def setup_method(self):
        super().setup_method()
        _ensure_agents_module_importable()

    def _make_internal_agent(self, **overrides):
        from open_webui.models.agents import Agents

        agent_id = overrides.get("id", "int-agent-001")
        Agents.insert_new_agent(
            id=agent_id,
            name=overrides.get("name", "InternalBot"),
            description="x",
            endpoint=f"https://hub.example.com/api/v1/agents/{agent_id}/internal-a2a",
            url=f"https://hub.example.com/api/v1/agents/{agent_id}/internal-a2a",
            version="1.0.0",
            capabilities={"streaming": True},
            skills=[],
            default_input_modes=["text"],
            default_output_modes=["text"],
            profile_image_url=None,
            system_prompt=overrides.get("system_prompt", "Answer in one sentence."),
            provider=overrides.get("provider", "anthropic"),
            model=overrides.get("model", "claude-sonnet-4-6"),
            deployment_mode="internal",
            deployment_status="ready",
            user_id="root",
        )
        return Agents.get_agent_by_id(agent_id)

    def _patch_run_agent_turn(self, monkeypatch, *, reply="hi", calls_sink=None):
        from open_webui.utils import a2a_runtime, chat as chat_mod

        async def fake_run_agent_turn(*, provider, model, system_prompt, user_message):
            if calls_sink is not None:
                calls_sink.append(
                    {
                        "provider": provider,
                        "model": model,
                        "system_prompt": system_prompt,
                        "user_message": user_message,
                    }
                )
            return reply

        # Patch on the original module AND on chat module's import binding.
        monkeypatch.setattr(a2a_runtime, "run_agent_turn", fake_run_agent_turn)
        monkeypatch.setattr(
            chat_mod, "generate_internal_agent_chat_completion",
            chat_mod.generate_internal_agent_chat_completion,
        )

    def _forbid_requests_post(self, monkeypatch):
        import requests

        def boom(*a, **kw):
            raise AssertionError(
                "requests.post called from internal-mode chat path; the "
                "short-circuit should have prevented any HTTPS round-trip"
            )

        monkeypatch.setattr(requests, "post", boom)

    def test_internal_agent_chat_dispatches_in_process(self, monkeypatch):
        """deployment_mode=internal -> run_agent_turn called, no HTTPS self-call."""
        import asyncio
        from open_webui.utils import chat as chat_mod

        agent = self._make_internal_agent()

        seen_calls: list[dict] = []
        self._patch_run_agent_turn(
            monkeypatch, reply="The OSU mascot is Benny the Beaver.",
            calls_sink=seen_calls,
        )
        self._forbid_requests_post(monkeypatch)

        # Build a minimal request stub. generate_chat_completion only reads
        # request.state and request.app.state.MODELS; for agent: routes the
        # latter is bypassed entirely.
        class _State:
            pass

        class _AppState:
            MODELS = {}

        class _App:
            state = _AppState()

        class _Req:
            state = _State()
            app = _App()

        class _User:
            id = "root"
            role = "admin"

        form_data = {
            "model": f"agent:{agent.id}",
            "messages": [{"role": "user", "content": "What is the OSU mascot?"}],
            "stream": False,
        }

        result = asyncio.get_event_loop().run_until_complete(
            chat_mod.generate_chat_completion(_Req(), form_data, user=_User())
        )

        # run_agent_turn was called exactly once with the agent's config.
        assert len(seen_calls) == 1
        call = seen_calls[0]
        assert call["provider"] == "anthropic"
        assert call["model"] == "claude-sonnet-4-6"
        assert call["system_prompt"] == "Answer in one sentence."
        assert call["user_message"] == "What is the OSU mascot?"

        # Response is the OpenAI envelope and contains the reply text.
        assert isinstance(result, dict)
        assert result["choices"][0]["message"]["content"] == (
            "The OSU mascot is Benny the Beaver."
        )

    def test_internal_agent_chat_streaming_envelope_is_openai_shaped(
        self, monkeypatch
    ):
        """Streaming branch returns text/event-stream chunks the chat UI expects."""
        import asyncio
        from open_webui.utils import chat as chat_mod
        from starlette.responses import StreamingResponse

        agent = self._make_internal_agent(id="int-agent-002")
        self._patch_run_agent_turn(monkeypatch, reply="hello world")
        self._forbid_requests_post(monkeypatch)

        class _State:
            pass

        class _AppState:
            MODELS = {}

        class _App:
            state = _AppState()

        class _Req:
            state = _State()
            app = _App()

        class _User:
            id = "root"
            role = "admin"

        form_data = {
            "model": f"agent:{agent.id}",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }

        result = asyncio.get_event_loop().run_until_complete(
            chat_mod.generate_chat_completion(_Req(), form_data, user=_User())
        )
        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"
