# Security QA — What's Defended, What's Tested, What's Deferred

> Location of the suite: `front/backend/open_webui/test/security/test_security_qa.py`
> Helpers: `front/backend/open_webui/test/security/conftest.py` (session-scoped
> postgres fixture — see "Conftest" section below).
> One file, six class groups, 23 tests total (20 active, 1 xfail, 1 skip,
> 1 conditional skip).
>
> **Status on this commit:** 23 passed, 2 skipped, 1 xfailed, 0 failed in ~43s
> (`pytest test/security/ -v` from `front/backend/open_webui/`).

This doc is the one-page answer to "how do we know nothing can be abused?"
Every assertion below maps to a named test. If the test is green, the
invariant holds on that commit. If the test is red, a real regression
has landed.

---

## TL;DR

| Area | Attacker story | # tests | Status |
|---|---|---|---|
| A. Chat privacy | Another logged-in user tries to read/mutate your chat | 8 | active |
| B. Agent deploy authz | Non-admin tries to deploy a hub-hosted agent | 4 | active |
| C. Internal A2A surface | Anonymous network caller tries to exfiltrate system prompt | 4 | active |
| D. Registry ownership | Non-owner tries to delete/overwrite someone else's registry entry | 3 | active |
| E. SSRF via `register-by-url` | Authed user points hub at internal URL (AWS metadata, localhost) | 3 | 1 active, 1 xfail, 1 skip |
| F. Secret-key hygiene | Forged JWT using shipped default secret | 1 | conditional skip |

Green suite = the listed attacks do not work against the current commit.

---

## A. Chat privacy (8 tests) — `TestChatPrivacy`

**Defended invariant:** every chat mutation and read goes through an
ownership-scoped query (`Chats.get_chat_by_id_and_user_id`,
`delete_chat_by_id_and_user_id`, etc.), so a second user's request cannot
affect or observe another user's chat — *and* pending-role users are
blocked upstream by `get_verified_user` before the handler runs.

| Test | Attacker action | Assertion |
|---|---|---|
| `test_user_cannot_read_another_users_chat` | Bob `GET /{id}` for Alice's chat | 401, no leak of chat content in body |
| `test_user_cannot_update_another_users_chat` | Bob `POST /{id}` mutation | 401 + row unchanged in DB |
| `test_user_cannot_delete_another_users_chat` | Bob `DELETE /{id}` | Row still present (handler may return 200/False) |
| `test_user_cannot_share_another_users_chat` | Bob `POST /{id}/share` | `share_id` remains null |
| `test_pending_user_cannot_read_own_chat_list` | Pending user `GET /` | 401 — `get_verified_user` rejects |
| `test_pending_user_blocked_from_read_and_create` | Pending user `GET /{id}` + `POST /new` | 401 on both |
| `test_admin_chat_access_respects_flag` | Admin `GET /list/user/{id}` with `ENABLE_ADMIN_CHAT_ACCESS=False` vs `True` | 401/403 when flag off, 200 when on |
| `test_anonymous_cannot_read_chat` | No bearer token | 401/403 from `get_current_user` |

**Relevant source:** `routers/chats.py:343-374` (read/update),
`routers/chats.py:483-509` (delete), `routers/chats.py:640-666` (share),
`utils/auth.py:242-248` (`get_verified_user`).

---

## B. Agent deploy authorization (4 tests) — `TestAgentDeployAuthz`

**Defended invariant:** `POST /api/v1/agents/deploy` is wrapped in
`get_admin_user`. Any non-admin request must be rejected *before* any
agent row is inserted, and the happy path for an admin must still work.

| Test | Who | Expected |
|---|---|---|
| `test_non_admin_user_cannot_deploy_agent` | role=user | 401 + 0 agent rows |
| `test_pending_user_cannot_deploy_agent` | role=pending | 401 + 0 agent rows |
| `test_anonymous_cannot_deploy_agent` | no token | 401/403 + 0 agent rows |
| `test_admin_can_deploy_agent_happy_path` | role=admin | 200 + 1 agent row |

**Why this matters:** the deploy endpoint creates a chat-model-backed agent
that the hub itself hosts. If a non-admin could invoke it they could spin
up arbitrary LLM-backed models on the hub, burning API budget and
injecting content into the model picker.

**Relevant source:** `routers/agents.py:450-533`, `utils/auth.py:251-257`.

---

## C. Internal A2A surface safety (4 tests) — `TestInternalA2ASafety`

**Context:** the A2A spec requires `/.well-known/agent.json` and the
message-send endpoint to be **publicly reachable**. We do not try to auth
them. What we *do* defend is: a public caller cannot trick the handler
into returning the stored `system_prompt`, another agent's config, or
API-key env var names — via *any* code path, including error envelopes.

Setup: an admin deploys `CanaryBot` with `system_prompt =
"CANARY_PROMPT_d0n0t_leak_42"`. Tests then probe the public surface.

| Test | Probe | Assertion |
|---|---|---|
| `test_well_known_exposes_only_public_fields` | `GET .../.well-known/agent.json` | body must NOT contain the canary, `system_prompt`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` |
| `test_internal_a2a_error_envelope_never_leaks_system_prompt` | Malformed body + valid body without API key | canary not in either response body |
| `test_internal_a2a_404s_for_non_internal_agent` | Insert `deployment_mode="external"` agent directly, POST its `/internal-a2a` | 404 (mode gate at `agents.py:540`) |
| `test_internal_a2a_rejects_unknown_method` | `method="message/broadcast"` | JSON-RPC error envelope (not HTTP 500), `id` preserved |

**Explicit non-goal:** this suite does **not** assert the downstream LLM
provider refuses to paraphrase the system prompt when asked. That is a
probabilistic property, belongs to a red-team eval harness, and is
tracked separately. What we assert here is the code we wrote never
*transmits* the prompt itself from the hub.

**Relevant source:** `routers/agents.py:536-619`.

---

## D. Registry ownership (3 tests) — `TestRegistryOwnership`

**Defended invariant:** `PUT /api/v1/registry/{id}` and `DELETE
/api/v1/registry/{id}` enforce `user.role == "admin" or agent.user_id ==
user.id` at the router level.

| Test | Attacker | Assertion |
|---|---|---|
| `test_user_cannot_delete_another_users_registry_entry` | role=user, not owner | 401 + row still present |
| `test_user_cannot_update_another_users_registry_entry` | role=user, not owner | 401 + `name` unchanged |
| `test_admin_can_delete_any_registry_entry` | role=admin, not owner | 200 + row removed (positive control) |

**Relevant source:** `routers/registry.py:119-184`.

---

## E. SSRF characterization (3 tests) — `TestRegisterByUrlSsrf`

**Today's surface:** `POST /api/v1/agents/register-by-url` calls
`requests.get(well_known_url, timeout=10)` against any user-supplied host
(`routers/agents.py:156`). There is no private/loopback/metadata
allowlist. That's a real risk in any deployment where the hub process
can reach an internal network.

This class is deliberately a mix of active and deferred tests so the
file *documents* the problem and the fix lands cleanly later.

| Test | Marker | What it says |
|---|---|---|
| `test_register_by_url_rejects_missing_url` | active | Empty string → 400. |
| `test_register_by_url_rejects_non_http_schemes` | active, parametrized (`file://`, `ftp://`, `gopher://`) | Non-http schemes → 400 (they get rewritten to https and fail on connect today, still 400). |
| `test_register_by_url_rejects_loopback` | `xfail(strict=False)` | Pending: today `http://127.0.0.1:1/` passes validation and fails on connect (also 400, but for the wrong reason); the target behaviour is "validator refuses before any network attempt." |
| `test_register_by_url_blocks_aws_metadata_endpoint` | `skip` | Pending: `http://169.254.169.254/...` → 400. Unskip when SEC-001 merges. |

**The deferred fix: SEC-001.** Add a host allowlist with an env-var
override (`ALLOW_PRIVATE_AGENT_URLS=1` for local dev). Flip `xfail` →
active and unskip the metadata-endpoint test in the same PR.

**Relevant source:** `routers/agents.py:140-215`, `routers/registry.py:36-111`.

---

## F. Secret-key hygiene (1 test) — `TestSecretKeyHygiene`

`open_webui.env` ships a default `WEBUI_SECRET_KEY = "t0p-s3cr3t"`. Any
production deployment that boots without overriding it inherits a secret
that's public in the source. Anyone can forge a JWT with it.

| Test | Behaviour |
|---|---|
| `test_default_jwt_secret_is_not_hardcoded_value` | **Hard failure** when `SEC_ENFORCE_SECRET=1` is set in CI. Conditionally **skips** in dev (with a message pointing at the env var) so the test does not false-fail on local clones that haven't rotated the key. |

**CI gate:** set `SEC_ENFORCE_SECRET=1` in the pipeline environment on
production-deploy branches.

---

## Conftest: session-scoped postgres fixture

`test/security/conftest.py` exists because the repo's `AbstractPostgresTest`
spins up a **new docker container per test class** without re-running
migrations — so the second test class in a run hits `relation "auth" does
not exist`. The conftest runs one `postgres:16.2` container for the whole
security session, imports `main` (triggering migrations against that
container), and attaches the resulting `TestClient` to every class via an
autouse function-scoped fixture. After each test it truncates every table
the suite writes to (including `agent` and `registry_agent`, which the base
class doesn't know about).

Test classes in this suite therefore inherit from `AbstractIntegrationTest`
(the plain base — no docker lifecycle), **not** `AbstractPostgresTest`. The
conftest is the one place the container is managed.

Two product bugs surfaced while wiring the suite; the tests work around them
rather than fix them (out of scope):

1. `RegistryAgents.insert_new_agent` round-trips rows through
   `RegistryAgentModel.model_validate`, which fails Pydantic's `dict`
   validation for `access_control` because migration 020 created that
   column as TEXT while the ORM declares it `JSON`. The helper swallows the
   exception and returns `None`. `TestRegistryOwnership.setup_method`
   therefore inserts rows with raw SQL and leaves `access_control` NULL so
   the router's own `get_agent_by_id` succeeds and the ownership check
   actually runs.
2. `ENABLE_ADMIN_CHAT_ACCESS` is captured as a module-level boolean at
   import time (`from open_webui.config import ENABLE_ADMIN_CHAT_ACCESS` in
   `routers/chats.py`), not read off `app.state.config`. To flip it in a
   test we patch `open_webui.routers.chats.ENABLE_ADMIN_CHAT_ACCESS`
   directly.

Both are good follow-up tickets but are explicitly not this PR's concern.

---

## Why the custom `mock_current_user_only` helper

The repo's existing `mock_webui_user` at `test/util/mock_user.py:7`
overrides **all four** auth dependencies (`get_current_user`,
`get_verified_user`, `get_admin_user`, `get_current_user_by_api_key`) with
a single stub that returns the mocked user regardless of role. Useful for
functional tests, **but it bypasses the role checks we need to exercise**
here. If used blindly in this suite, a test titled "non-admin cannot
deploy" would pass by accident because `get_admin_user` never runs.

`mock_current_user_only` (defined at the top of the test file, lines
32-56) overrides **only** `get_current_user`. `get_verified_user` and
`get_admin_user` still run their role checks against the mocked user.
That's what makes the negative-auth tests meaningful.

If you add new security tests to this file, use `mock_current_user_only`
and never `mock_webui_user`.

---

## How to run

### In CI
The file is discovered by the existing pytest invocation; nothing to
wire up. Flip on the secret-key gate by exporting `SEC_ENFORCE_SECRET=1`
in the CI environment.

### Locally
Requires docker (the base class spins up a throwaway `postgres:16.2`)
and the test dependencies:

```bash
cd front/
docker pull postgres:16.2
pip install -r backend/requirements.txt pytest pytest-docker
pytest backend/open_webui/test/security/ -v
```

Run a single group, e.g.:
```bash
pytest backend/open_webui/test/security/test_security_qa.py::TestAgentDeployAuthz -v
```

Run just the secret-key gate in enforced mode:
```bash
SEC_ENFORCE_SECRET=1 pytest \
  backend/open_webui/test/security/test_security_qa.py::TestSecretKeyHygiene -v
```

Expected runtime: <30s once the postgres image is cached.

---

## How to verify the tests are real (self-check)

A security test is only useful if it turns **red** when the invariant
breaks. On a throwaway branch:

1. Remove the ownership check in `routers/registry.py:134` → registry
   ownership tests turn red.
2. Weaken `utils/auth.py:243` to `user.role not in {"pending", "user",
   "admin"}` → pending-bypass tests turn red.
3. Drop the `deployment_mode == "internal"` guard at
   `routers/agents.py:540` → `test_internal_a2a_404s_for_non_internal_agent`
   turns red.
4. Remove `get_admin_user` from the `/deploy` route → all three negative
   deploy tests turn red.

If any of those edits *do not* flip the expected test, that test is
aspirational, not real, and needs rewriting before merge.

---

## Deliberately out of scope (tracked as separate follow-ups)

| Tag | Scope |
|---|---|
| SEC-001 | SSRF allowlist for `register-by-url` / registry submit. |
| SEC-002 | Rate-limit `/signup` and `/signin` — no limiter is present today. |
| SEC-003 | Enforce minimum password length on signup. |
| (no tag) | Real LLM jailbreak resistance — belongs to a red-team eval suite, not unit tests. |
| (no tag) | Frontend XSS / CSRF — Playwright-based suite, separate PR. |
| (no tag) | Dependency-vulnerability scanning (`npm audit`, `pip-audit`) — CI config change, separate PR. |

---

## Maintenance guide

- When a new endpoint is added that handles per-user data, add an
  ownership-check test in the matching class group.
- When `deployment_mode` values grow (e.g. `cloud_run`), extend
  `test_internal_a2a_404s_for_non_internal_agent` to also assert the new
  mode is rejected at `/internal-a2a`.
- When SEC-001 merges, flip the `xfail` to active and remove the `skip`
  marker on the two SSRF tests — do *not* touch the assertions
  themselves. They were pre-written for the target behaviour.
- Keep the docstring format `Attacker -> Goal -> Invariant` on every new
  test. A reviewer should be able to read this file top-to-bottom and
  answer "what can't be abused?" without running anything.
