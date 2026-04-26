---
## What this is

OpenBeavs now ships a small, named set of automated tests whose only
job is to prove that specific abuse attempts against the hub do not
work. The suite lives at
`front/backend/open_webui/test/security/test_security_qa.py`. It has
**23 tests** grouped into six categories. When the whole suite is
green, it means the listed attacks are defended against on that
commit. When a test flips red, something real was weakened in the
product.
---

## Test info

| Group                    | In plain English                                              | Status              |
| ------------------------ | ------------------------------------------------------------- | ------------------- |
| A. Chat privacy          | Can a logged-in user peek at someone else's chat?             | 8 green             |
| B. Deploy authorization  | Can a non-admin spin up a hub-hosted agent?                   | 4 green             |
| C. Public A2A surface    | Can an anonymous caller read an agent's secret system prompt? | 4 green             |
| D. Registry ownership    | Can someone overwrite or delete an entry they don't own?      | 3 green             |
| E. SSRF via "add by URL" | Can an admin point the hub at an internal URL?                | 1 green, 2 deferred |
| F. Secret key hygiene    | Did we ship the default JWT signing key?                      | conditional         |
| G. Cloud Run deploy path | Does "Deploy to Cloud Run" leak keys, run as non-admin, or leave orphan rows? | 9 green |

"JWT" is the signed token the browser sends with every request to
prove who you are. A _system prompt_ is the private instruction given
to a hosted agent at deploy time — it shapes the agent's behaviour
and is not meant to be public. "JSON-RPC" is the wire format the
A2A protocol uses — a normal HTTP POST with a JSON body.

---

## The six things we defend

### A. Chat privacy — `TestChatPrivacy`

**The bad scenario.** Imagine Bob logs in, notices his browser URL
says `/chats/42`, and tries `/chats/43` — hoping to read, edit, or
delete a chat that belongs to Alice. Or imagine Bob sits on an
approval queue with role _pending_ and tries to read any chat at all
before an admin promotes him.

**What the hub does about it.** Every chat-touching endpoint
(`routers/chats.py`) looks up chats using a query that includes the
current user's id. Bob's request for Alice's chat silently returns
_not found_. Users whose role is _pending_ are rejected before the
handler runs at all, by a global rule in the auth utilities.

**What the tests do.** A test creates a chat as Alice, logs in as
Bob, and tries the full set of operations — read, update, delete,
share. Each must be rejected and the database row must be unchanged
afterwards. A separate test logs in as a pending user and hits the
chat list, read, and create endpoints — all must be rejected. A
final test hits the admin-only "read another user's chats" endpoint
both with the feature flag on and with it off, to confirm admin
access only works when explicitly enabled.

**What green proves (and doesn't).** Green proves the direct HTTP
calls to the chat endpoints are ownership-checked. Green does **not**
prove anything about the chat contents after they've been fetched by
the owner — for example, a compromised frontend, a leaked database
backup, or a third-party integration reading from the DB directly
are outside this test group's scope.

---

### B. Agent deploy authorization — `TestAgentDeployAuthz`

**The bad scenario.** OpenBeavs lets a hub admin spin up a hosted,
chattable agent from a name + description + system prompt. That
endpoint creates an LLM-backed model that burns real API budget and
shows up in every user's model picker. If a non-admin could call it,
they could bootleg models onto the hub.

**What the hub does about it.** The deploy endpoint
(`POST /api/v1/agents/deploy`) requires the admin role — any other
role is rejected before the handler runs. Unauthenticated requests
are rejected too.

**What the tests do.** Four tests hit the deploy endpoint with four
different identities: a regular user, a pending user, an anonymous
request (no token), and an admin. The first three must be rejected
_and_ the database must contain zero new agent rows afterwards. The
admin call must succeed and produce exactly one new row — this last
one is a positive control so we know the endpoint itself still works.

**What green proves (and doesn't).** Green proves the role gate is
in place. Green does not prove that the admin role itself is
impossible to obtain by accident (e.g., by promoting the first
signup automatically, which is the default in Open WebUI). Admin
account hygiene is a deployment concern, not a test concern.

---

### C. Public A2A surface safety — `TestInternalA2ASafety`

**The bad scenario.** The A2A agent protocol _requires_ two endpoints
to be public: the discovery card at `/.well-known/agent.json`, and
the JSON-RPC message-send endpoint. Anyone on the internet can call
them. Someone calls those endpoints and tries to get back the
agent's hidden system prompt, or the hub's provider API key, or
another agent's configuration — either by asking politely (in the
JSON body) or by triggering an error to see what the error message
reveals.

**What the hub does about it.** The discovery card is built from a
small list of fields and explicitly omits the system prompt,
provider, model, and any API-key env names. The JSON-RPC handler has
a mode gate — only agents deployed as "internal" serve traffic
through this endpoint — and its error envelopes carry generic
messages, never the stored system prompt.

**What the tests do.** The setup deploys an agent whose system
prompt contains a unique canary string (e.g.,
`CANARY_PROMPT_d0n0t_leak_42`). Four tests then probe the public
surface: (1) fetch the discovery card and assert the canary and the
API-key env names are absent; (2) send a valid JSON-RPC call without
an API key configured, plus a malformed body, and assert the canary
appears in neither error response; (3) register an agent marked as
_external_ and confirm the internal endpoint refuses to serve it;
(4) send a JSON-RPC request with an unknown method and assert the
hub returns a clean error envelope rather than crashing.

**What green proves (and doesn't).** Green proves the hub's own code
never transmits the system prompt, and that the public surface
refuses to spill under the probes in this file. Green does **NOT**
prove the downstream LLM will refuse to paraphrase the system prompt
when a user asks "what were your instructions?" — that's a
probabilistic property of the model, not a property of our code,
and it belongs to a separate red-team evaluation.

---

### D. Registry ownership — `TestRegistryOwnership`

**The bad scenario.** The agent registry (`/api/v1/registry/`) is
OpenBeavs's public showcase of submitted agents. A user can submit
their own entry and edit or delete it later. The bad scenario is
one user deleting or overwriting another user's entry — the
registry equivalent of tampering with someone else's listing on a
marketplace.

**What the hub does about it.** The update and delete endpoints
check that either the requesting user is an admin or they own the
registry row. Otherwise they reject the call.

**What the tests do.** A test inserts a registry entry owned by
Alice, then logs in as Bob (a regular user) and tries to update and
delete it. Both must be rejected; the row must still be there and
its name must be unchanged. A positive-control test confirms an
admin can delete any entry.

**What green proves (and doesn't).** Green proves the ownership
check is enforced. It does not prove the submit endpoint itself is
free of abuse — SSRF via the submit flow is its own group (section
E).

---

### E. SSRF via "add by URL" — `TestRegisterByUrlSsrf`

**The bad scenario.** When a user adds an agent by URL, the hub
fetches the agent's discovery card by making an HTTP GET from the
server. Today there is no allowlist on the target host. A hostile
admin (or a confused one) could make the hub fetch an internal URL
— `http://127.0.0.1/admin`, another service on the private network,
or the AWS instance metadata endpoint at `169.254.169.254` that
hands out cloud credentials to any caller on the machine. This is
SSRF (Server-Side Request Forgery).

**What the hub does about it.** The minimal validation — rejects an
empty URL, rejects non-HTTP schemes like `file://` and `ftp://`.
That's all. A proper allowlist is on the backlog as **SEC-001** and
is deliberately out of scope for this suite.

**What the tests do.** Active tests assert the empty-URL and
non-HTTP-scheme cases return 400. A third test is marked as an
**expected failure** — it documents that `http://127.0.0.1:1/`
currently is not rejected by the validator (it fails later on the
network call, for the wrong reason). A fourth test is **skipped**
with a pointer to SEC-001 — it contains the final assertion we want
(AWS metadata endpoint must be rejected). When SEC-001 lands, the
fix PR flips those markers; the assertions themselves do not need
to change.

**What green proves (and doesn't).** Green on this group means the
obvious bad inputs (empty string, wrong scheme) are rejected and
that the known gap is documented _inside the test file_, not on a
wiki page that drifts. Green does **NOT** claim SSRF is fixed. The
two deferred tests are literally placeholders for the fix.

---

### F. Secret key hygiene — `TestSecretKeyHygiene`

**The bad scenario.** Open WebUI (the project OpenBeavs is forked
from) ships a default JWT signing key. If a deployment boots without
overriding that key, anyone on the internet can forge a valid login
token because the key is public on GitHub.

**What the hub does about it.** The key is supposed to be rotated
by the deployment environment. Nothing in the code forces it.

**What the test does.** There is one test,
`test_default_jwt_secret_is_not_hardcoded_value`. When the CI env
var `SEC_ENFORCE_SECRET=1` is set, the test hard-fails if the
deployed key equals the well-known default. When that env var is
not set — e.g. on a fresh local clone — the test skips with a
helpful message. This keeps the guardrail in CI without breaking
developer laptops.

**What green proves (and doesn't).** Green (in CI, with the enforce
flag on) proves the deployment's JWT key is not the shipped
default. It does not prove the key is rotated on a sensible
schedule, and it does not prove it's stored securely at rest — that
is the deployment's responsibility.

---

### G. Cloud Run deploy path — `TestCloudRunDeployment`

**The bad scenario.** OpenBeavs now supports deploying agents to
**dedicated Google Cloud Run services** instead of hosting them inside
the hub itself. The new code path shells out to `gcloud run deploy`
and expects an API key wired up via Secret Manager. Three real
regressions could land here. (1) A non-admin convinces the form to
trigger a real GCP deploy — that's a billable side effect on shared
infrastructure. (2) The hub forwards the API key as a plain
environment variable instead of a Secret Manager reference, leaving it
visible in `gcloud run services describe`. (3) The deploy fails
halfway and leaves an "orphan" agent row in the database that points
at a service that doesn't exist.

**What the hub does about it.** The deploy endpoint is admin-gated;
the helper that talks to gcloud always uses `--update-secrets`
(routed through Secret Manager) for the provider API key, never
`--set-env-vars`; and the route invokes the gcloud helper **before**
inserting the database row, so a failed deploy raises a 502 and
leaves no agent row behind.

**What the tests do.** Nine tests, all of which mock the gcloud
subprocess call so CI never makes a real GCP request. The mock
captures every argument, and the tests assert: (1) a non-admin
request is rejected with 401 *and* the mock is never invoked; (2)
each provider routes to the correct source directory under
`agents/{claude,chatgpt,gemini}-agent/`; (3) the API-key env var
appears in the `--update-secrets` payload but never in the
`--set-env-vars` payload; (4) when the mock raises a deploy failure,
the response is 502 and zero agent rows exist; (5) when the
operator sets `OPENBEAVS_CLOUD_RUN_DISABLED=1`, the deploy returns
503 (not 500) and the in-hub fallback path keeps working.

**What green proves (and doesn't).** Green proves the hub's deploy
code path holds the listed invariants on every commit. Green does
**not** prove the resulting Cloud Run service is configured exactly
right — that requires a real GCP deploy, which the tests deliberately
do not perform. Operationally, the
[Production API Keys doc](./PROD_API_KEYS.md) is the
checklist for that part. Green also does not prove anything about
the per-agent service after it's running — just about the act of
provisioning it.

---

## The "not yet" list

These gaps are real. They are deliberately not tested green in this
suite because the fixes haven't landed yet and we don't want the
test file to lie about the current state of the product.

| Tag         | What it is                                                                                                        | Why it's separate                                                      |
| ----------- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **SEC-001** | Add an allowlist to "add by URL" so the hub refuses to fetch loopback, private-network, and cloud-metadata hosts. | Real fix, separate PR. Two placeholder tests are in the suite already. |
| **SEC-002** | Rate-limit the signup and signin endpoints.                                                                       | Needs a limiter dependency; belongs to an infra PR.                    |
| **SEC-003** | Enforce a minimum password length on signup.                                                                      | Needs a migration for existing accounts; separate PR.                  |
| (no tag)    | Real jailbreak resistance — prove the hosted agent's LLM will not paraphrase the system prompt when coaxed.       | Probabilistic, needs an evaluation harness, not unit tests.            |
| (no tag)    | Frontend cross-site scripting (XSS) and CSRF.                                                                     | Needs a Playwright-based browser suite; separate PR.                   |
| (no tag)    | Third-party dependency vulnerability scanning (`npm audit`, `pip-audit`).                                         | A CI config change, not a test file.                                   |

If a reviewer asks "what about X?" and X is on this list, the honest
answer is "yes, it's a known gap, it has a ticket, and the reason
it isn't in this suite is [row above]."

---

## How to see it for yourself

You need Docker running (the test suite spins up a throwaway
Postgres container). From the project root:

```bash
cd front/
docker pull postgres:16.2
pip install -r backend/requirements.txt
pytest backend/open_webui/test/security/ -v
```

The last line of output should read something like:

```
31 passed, 2 skipped, 1 xfailed in ~55s
```

- **31 passed** — 31 attack scenarios were executed against the
  current code and rejected as intended.
- **2 skipped** — two placeholders waiting on SEC-001 (SSRF fix) and
  the CI-only secret-key gate.
- **1 xfailed** — one test that is _expected_ to fail on today's
  code because the matching fix hasn't landed; it'll flip when
  SEC-001 merges.
- **0 failed** — nothing is unexpectedly broken on this commit.

If you want to poke at the tests themselves, the single file is
`front/backend/open_webui/test/security/test_security_qa.py`. Each
test has a docstring naming the attacker scenario in one or two
lines. The docstrings are intentionally readable without opening
any of the production code.

---

## Why you can trust it

A test is only valuable if it turns **red** when the product breaks.
A green test that would stay green even with the guard removed is
security theatre.

To sanity-check this suite, we deliberately broke the product on a
throwaway branch — removed the ownership check in the registry
endpoint, then weakened the auth utility so pending users could
reach protected endpoints. In each case, the matching test in this
suite went from green to red. We put the checks back, the tests
returned to green, and we merged neither of the sabotage edits.

That's the property we keep paying for with every new test added:
the test must be able to fail for a real reason. The maintenance
guidance at the bottom of `SECURITY_QA.md` is how we keep it that
way.
