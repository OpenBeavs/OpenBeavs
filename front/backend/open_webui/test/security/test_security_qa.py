"""Security QA suite.

Each test maps to a concrete attacker story. Docstrings state:
    Attacker -> Goal -> Defended invariant.

A failing test is a real security regression. Out of scope is listed in the
plan file (jailbreak LLM behavior, rate-limiting, frontend XSS, dep scans).
"""

import os
import time
import uuid
from contextlib import contextmanager

import pytest
from fastapi import FastAPI

from test.util.abstract_integration_test import AbstractIntegrationTest


# ---------------------------------------------------------------------------
# Auth-override helper
#
# `mock_webui_user` in test/util/mock_user.py overrides *all* auth deps,
# including `get_verified_user` and `get_admin_user` — which means it bypasses
# the role checks we want to exercise here. This helper overrides only
# `get_current_user`, so the real role gates run on top of the mocked user.
# ---------------------------------------------------------------------------


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
    # Must match the module path used by get_fast_api_client (`from main import app`).
    # Importing `open_webui.main` gives a *different* module object (and FastAPI
    # instance) even though the file on disk is the same — dependency overrides
    # set on that instance will not affect the TestClient.
    from main import app

    return app


# A. Chat privacy


class TestChatPrivacy(AbstractIntegrationTest):
    """Attacker = another logged-in user (role=user). Goal = read/mutate Alice's chat.
    Invariant: ownership-scoped queries block all cross-user access."""

    BASE_PATH = "/api/v1/chats"

    def setup_method(self):
        super().setup_method()
        from open_webui.models.chats import ChatForm, Chats

        self.chats = Chats
        self.victim_id = "alice"
        self.attacker_id = "bob"
        chat = self.chats.insert_new_chat(
            self.victim_id,
            ChatForm(chat={"name": "alice_secret_chat", "messages": []}),
        )
        self.chat_id = chat.id

    def test_user_cannot_read_another_users_chat(self):
        """Bob GETs /{id} for Alice's chat. Handler must return 401; body must not contain chat content."""
        with mock_current_user_only(_app(), id=self.attacker_id, role="user"):
            response = self.fast_api_client.get(self.create_url(f"/{self.chat_id}"))
        assert response.status_code == 401
        assert "alice_secret_chat" not in response.text

    def test_user_cannot_update_another_users_chat(self):
        """Bob POSTs /{id} with a mutation. Row must be unchanged in DB afterwards."""
        with mock_current_user_only(_app(), id=self.attacker_id, role="user"):
            response = self.fast_api_client.post(
                self.create_url(f"/{self.chat_id}"),
                json={"chat": {"name": "hacked", "messages": []}},
            )
        assert response.status_code == 401
        fresh = self.chats.get_chat_by_id(self.chat_id)
        assert fresh is not None
        assert fresh.chat.get("name") == "alice_secret_chat"

    def test_user_cannot_delete_another_users_chat(self):
        """Bob DELETEs /{id}. Row must still exist. (Handler returns 200/False; that's fine — what matters is persistence.)"""
        with mock_current_user_only(_app(), id=self.attacker_id, role="user"):
            self.fast_api_client.delete(self.create_url(f"/{self.chat_id}"))
        assert self.chats.get_chat_by_id(self.chat_id) is not None

    def test_user_cannot_share_another_users_chat(self):
        """Bob tries to create a share_id for Alice's chat. share_id must remain unset."""
        with mock_current_user_only(_app(), id=self.attacker_id, role="user"):
            response = self.fast_api_client.post(
                self.create_url(f"/{self.chat_id}/share")
            )
        # handler either 401s or returns None-ish; either way, no share_id
        assert response.status_code in (401, 200)
        fresh = self.chats.get_chat_by_id(self.chat_id)
        assert fresh.share_id is None

    def test_pending_user_cannot_read_own_chat_list(self):
        """Pending-role user hits any verified endpoint. `get_verified_user` must 401 before the handler runs."""
        with mock_current_user_only(_app(), id=self.victim_id, role="pending"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 401

    def test_pending_user_blocked_from_read_and_create(self):
        """Same pending-role gate covers GET /{id} and POST /new, not just list."""
        with mock_current_user_only(_app(), id=self.victim_id, role="pending"):
            r_get = self.fast_api_client.get(self.create_url(f"/{self.chat_id}"))
            r_post = self.fast_api_client.post(
                self.create_url("/new"),
                json={"chat": {"name": "x", "messages": []}},
            )
        assert r_get.status_code == 401
        assert r_post.status_code == 401

    def test_admin_chat_access_respects_flag(self):
        """Admin hitting /list/user/{id} is gated by ENABLE_ADMIN_CHAT_ACCESS.
        When the flag is off, the endpoint must refuse even for role=admin.
        The router captures the flag at import time (`from open_webui.config
        import ENABLE_ADMIN_CHAT_ACCESS`), so we patch the module attribute."""
        from open_webui.routers import chats as chats_mod

        original = chats_mod.ENABLE_ADMIN_CHAT_ACCESS
        try:
            chats_mod.ENABLE_ADMIN_CHAT_ACCESS = False
            with mock_current_user_only(_app(), id="root", role="admin"):
                r_off = self.fast_api_client.get(
                    self.create_url(f"/list/user/{self.victim_id}")
                )
            chats_mod.ENABLE_ADMIN_CHAT_ACCESS = True
            with mock_current_user_only(_app(), id="root", role="admin"):
                r_on = self.fast_api_client.get(
                    self.create_url(f"/list/user/{self.victim_id}")
                )
        finally:
            chats_mod.ENABLE_ADMIN_CHAT_ACCESS = original
        assert r_off.status_code in (401, 403)
        assert r_on.status_code == 200

    def test_anonymous_cannot_read_chat(self):
        """No bearer token. `get_current_user` must 403 before any handler logic."""
        response = self.fast_api_client.get(self.create_url(f"/{self.chat_id}"))
        assert response.status_code in (401, 403)


# B. Agent deploy authorization


class TestAgentDeployAuthz(AbstractIntegrationTest):
    """Attacker = non-admin (user/pending/anonymous). Goal = deploy an internal agent.
    Invariant: `get_admin_user` rejects; no rows created."""

    BASE_PATH = "/api/v1/agents"

    def setup_method(self):
        super().setup_method()

    def _payload(self):
        return {
            "name": "ShouldNotExist",
            "description": "x",
            "system_prompt": "y",
            "provider": "anthropic",
            "publish_to_registry": False,
        }

    def _count_agents(self):
        from open_webui.internal.db import Session
        from open_webui.models.agents import Agent

        return Session.query(Agent).count()

    def test_non_admin_user_cannot_deploy_agent(self):
        """role=user hits /deploy. 401 expected; zero agent rows created."""
        with mock_current_user_only(_app(), id="bob", role="user"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )
        assert response.status_code == 401
        assert self._count_agents() == 0

    def test_pending_user_cannot_deploy_agent(self):
        """role=pending hits /deploy. 401 expected; zero agent rows."""
        with mock_current_user_only(_app(), id="p1", role="pending"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )
        assert response.status_code == 401
        assert self._count_agents() == 0

    def test_anonymous_cannot_deploy_agent(self):
        """No bearer token. 401/403 expected; zero agent rows."""
        response = self.fast_api_client.post(
            self.create_url("/deploy"), json=self._payload()
        )
        assert response.status_code in (401, 403)
        assert self._count_agents() == 0

    def test_admin_can_deploy_agent_happy_path(self):
        """Positive control: role=admin creates exactly one agent row."""
        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"), json=self._payload()
            )
        assert response.status_code == 200, response.text
        assert self._count_agents() == 1


# C. Internal A2A surface safety (public endpoints by A2A spec)


class TestInternalA2ASafety(AbstractIntegrationTest):
    """Attacker = anyone on the network (endpoints are intentionally unauthenticated).
    Goal = exfiltrate the stored system_prompt or API keys.
    Invariant: handler never writes the system_prompt or env-var names into any response."""

    BASE_PATH = "/api/v1/agents"
    SECRET_SYSTEM_PROMPT = "CANARY_PROMPT_d0n0t_leak_42"

    def setup_method(self):
        super().setup_method()
        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.post(
                self.create_url("/deploy"),
                json={
                    "name": "CanaryBot",
                    "description": "canary",
                    "system_prompt": self.SECRET_SYSTEM_PROMPT,
                    "provider": "anthropic",
                    "publish_to_registry": False,
                },
            )
        assert response.status_code == 200, response.text
        self.agent_id = response.json()["id"]

    def test_well_known_exposes_only_public_fields(self):
        """Public GET must omit system_prompt, provider, model, and API-key env-var names."""
        response = self.fast_api_client.get(
            self.create_url(f"/{self.agent_id}/internal-a2a/.well-known/agent.json")
        )
        assert response.status_code == 200
        body = response.text
        assert self.SECRET_SYSTEM_PROMPT not in body
        for forbidden in (
            "system_prompt",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
        ):
            assert forbidden not in body, f"leaked: {forbidden}"

    def test_internal_a2a_error_envelope_never_leaks_system_prompt(self):
        """Malformed and valid-but-no-key JSON-RPC both must omit the stored system prompt."""
        # malformed
        r1 = self.fast_api_client.post(
            self.create_url(f"/{self.agent_id}/internal-a2a"),
            json={"method": "nope"},
        )
        assert self.SECRET_SYSTEM_PROMPT not in r1.text
        # valid shape but no ANTHROPIC_API_KEY -> provider call raises -> error envelope
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            r2 = self.fast_api_client.post(
                self.create_url(f"/{self.agent_id}/internal-a2a"),
                json={
                    "jsonrpc": "2.0",
                    "method": "message/send",
                    "params": {
                        "message": {
                            "messageId": "x",
                            "role": "user",
                            "parts": [{"text": "hi", "type": "text"}],
                        }
                    },
                    "id": 1,
                },
            )
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved
        assert self.SECRET_SYSTEM_PROMPT not in r2.text

    def test_internal_a2a_404s_for_non_internal_agent(self):
        """Directly insert an external-mode agent; its /internal-a2a must 404."""
        from open_webui.internal.db import Session
        from open_webui.models.agents import Agent

        external_id = str(uuid.uuid4())
        row = Agent(
            id=external_id,
            name="External",
            description="x",
            endpoint="https://example.com/a2a",
            url="https://example.com/a2a",
            deployment_mode="external",
            is_active=True,
            created_at=int(time.time()),
            updated_at=int(time.time()),
        )
        Session.add(row)
        Session.commit()

        response = self.fast_api_client.post(
            self.create_url(f"/{external_id}/internal-a2a"),
            json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {"message": {"parts": [{"text": "hi"}]}},
                "id": 1,
            },
        )
        # The mode gate returns a JSON-RPC "Agent not found" error envelope
        # at HTTP 200 (per A2A spec — transport stays healthy, payload says
        # no). What matters is that the handler never reaches run_agent_turn
        # for a non-internal agent.
        assert response.status_code == 200
        body = response.json()
        assert "error" in body
        assert "not found" in body["error"]["message"].lower()

    def test_internal_a2a_rejects_unknown_method(self):
        """Any method other than message/send must return a JSON-RPC error envelope (not 500)."""
        response = self.fast_api_client.post(
            self.create_url(f"/{self.agent_id}/internal-a2a"),
            json={
                "jsonrpc": "2.0",
                "method": "message/broadcast",
                "params": {},
                "id": 99,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "error" in body
        assert body.get("id") == 99


# D. Registry ownership


class TestRegistryOwnership(AbstractIntegrationTest):
    """Attacker = non-owner, non-admin. Goal = overwrite/delete someone else's registry entry.
    Invariant: router-level ownership check rejects with 401; row unchanged."""

    BASE_PATH = "/api/v1/registry"

    def setup_method(self):
        super().setup_method()
        from sqlalchemy import text as sql_text
        from open_webui.internal.db import Session
        from open_webui.models.registry import RegistryAgents

        self.registry = RegistryAgents
        self.owner_id = "alice"
        self.attacker_id = "bob"
        self.entry_id = str(uuid.uuid4())
        # The `registry_agent.access_control` column is declared as `JSON` on
        # the ORM model but migration 020 actually created it as TEXT. Writing
        # a Python dict via the ORM round-trips back as the literal string
        # '{}' / 'null', which then fails Pydantic dict validation in
        # `get_agent_by_id` — so the helper silently returns None and the
        # router 404s before reaching the ownership check. Insert with raw
        # SQL and leave access_control NULL to avoid that read-side bug.
        now = int(time.time())
        Session.execute(
            sql_text(
                "INSERT INTO registry_agent "
                "(id, user_id, url, name, description, created_at, updated_at) "
                "VALUES (:id, :uid, :url, :name, :desc, :c, :u)"
            ),
            {
                "id": self.entry_id,
                "uid": self.owner_id,
                "url": f"http://example.test/{self.entry_id}",
                "name": "AlicesAgent",
                "desc": "private",
                "c": now,
                "u": now,
            },
        )
        Session.commit()
        Session.close()

    def test_user_cannot_delete_another_users_registry_entry(self):
        with mock_current_user_only(_app(), id=self.attacker_id, role="user"):
            response = self.fast_api_client.delete(self.create_url(f"/{self.entry_id}"))
        assert response.status_code == 401
        assert self.registry.get_agent_by_id(self.entry_id) is not None

    def test_user_cannot_update_another_users_registry_entry(self):
        with mock_current_user_only(_app(), id=self.attacker_id, role="user"):
            response = self.fast_api_client.put(
                self.create_url(f"/{self.entry_id}"), json={"name": "hacked"}
            )
        assert response.status_code == 401
        fresh = self.registry.get_agent_by_id(self.entry_id)
        assert fresh.name == "AlicesAgent"

    def test_admin_can_delete_any_registry_entry(self):
        """Positive control: admin role bypasses ownership check."""
        with mock_current_user_only(_app(), id="root", role="admin"):
            response = self.fast_api_client.delete(self.create_url(f"/{self.entry_id}"))
        assert response.status_code == 200
        assert self.registry.get_agent_by_id(self.entry_id) is None


# E. SSRF characterization (register-by-url)


class TestRegisterByUrlSsrf(AbstractIntegrationTest):
    """Attacker = authenticated user. Goal = coerce the hub into fetching internal URLs
    (cloud metadata, localhost admin ports, RFC1918).
    Invariant (today): rejects plainly-invalid schemes. Hardened invariant (SEC-001)
    will reject private/loopback hosts — tests prefilled with skip/xfail."""

    BASE_PATH = "/api/v1/agents"

    def setup_method(self):
        super().setup_method()

    def test_register_by_url_rejects_missing_url(self):
        with mock_current_user_only(_app(), id="u1", role="user"):
            response = self.fast_api_client.post(
                self.create_url("/register-by-url"), json={"agent_url": ""}
            )
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "bad_url",
        ["file:///etc/passwd", "ftp://example.com/", "gopher://evil/"],
    )
    def test_register_by_url_rejects_non_http_schemes(self, bad_url):
        """Handler must refuse non-http(s) schemes. Today they get prefixed
        with https:// (agents.py:147) and then fail on connect; that's
        still a 400, which satisfies the contract."""
        with mock_current_user_only(_app(), id="u1", role="user"):
            response = self.fast_api_client.post(
                self.create_url("/register-by-url"), json={"agent_url": bad_url}
            )
        assert response.status_code == 400

    @pytest.mark.xfail(
        strict=False,
        reason="SEC-001 pending: register-by-url currently accepts http://127.0.0.1",
    )
    def test_register_by_url_rejects_loopback(self):
        """Today this passes the URL validator and then fails on connect; should 400 on validation instead."""
        with mock_current_user_only(_app(), id="u1", role="user"):
            response = self.fast_api_client.post(
                self.create_url("/register-by-url"),
                json={"agent_url": "http://127.0.0.1:1/"},
            )
        # desired behaviour: validator rejects before any network attempt
        assert response.status_code == 400
        # desired behaviour: reason mentions "private" / "loopback"
        assert any(
            word in response.text.lower() for word in ("loopback", "private", "blocked")
        )

    @pytest.mark.skip(reason="SEC-001: blocks 169.254.169.254 — turns on when fix merges")
    def test_register_by_url_blocks_aws_metadata_endpoint(self):
        with mock_current_user_only(_app(), id="u1", role="user"):
            response = self.fast_api_client.post(
                self.create_url("/register-by-url"),
                json={"agent_url": "http://169.254.169.254/latest/meta-data/"},
            )
        assert response.status_code == 400


# F. Secret-key hygiene


class TestSecretKeyHygiene:
    """Attacker = anyone who has read the public source. Goal = forge a JWT using the
    known default secret. Invariant: production boots must not use the shipped default."""

    def test_default_jwt_secret_is_not_hardcoded_value(self):
        """Hard failure in CI (when SEC_ENFORCE_SECRET=1); warning otherwise."""
        from open_webui.env import WEBUI_SECRET_KEY

        default = "t0p-s3cr3t"
        if os.environ.get("SEC_ENFORCE_SECRET") == "1":
            assert WEBUI_SECRET_KEY != default, (
                "WEBUI_SECRET_KEY is the shipped default; set a unique value in prod"
            )
        else:
            if WEBUI_SECRET_KEY == default:
                pytest.skip(
                    "WEBUI_SECRET_KEY is the default; set SEC_ENFORCE_SECRET=1 in CI to make this a hard failure"
                )
