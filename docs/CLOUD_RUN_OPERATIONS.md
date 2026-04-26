# Operating OpenBeavs on Google Cloud Run

The original capstone owner stood up the project on **Google Cloud
Run**, region `us-west1`, GCP project `osu-genesis-hub`. This is the
short manual for taking over: how to log in, what's deployed, how to
ship a change, how to look at logs, and how to roll back when you
break something.

This is operational, not architectural. For "what does the code do",
read `CLAUDE.md`. For "what does the deploy form do", read
`docs/TEST_AGENT_DEPLOY.txt`.

---

## What's deployed

There are two kinds of Cloud Run service in this project:

1. **The hub** — the SvelteKit frontend bundled with the
   FastAPI/uvicorn backend, all in one container. CI deploys this on
   every merge to `main`. Service name:
   `openbeavs-deploy-test`. Built from the root `Dockerfile` via
   `cloudbuild.yaml`.
2. **Per-agent services** — provisioned at runtime when a hub admin
   clicks **Deploy** in the Agents workspace and checks "Deploy to
   dedicated Cloud Run service." One service per agent. Service
   names start with `a-` followed by the agent UUID. Built from
   `agents/{claude,chatgpt,gemini}-agent/` source dirs via
   `gcloud run deploy --source=...`.

Both run as `--allow-unauthenticated` because the A2A discovery card
and message-send endpoints are public by protocol.

---

## First-time setup on a new machine

```bash
# 1. Install gcloud — once per machine
#    https://cloud.google.com/sdk/docs/install
gcloud --version    # confirm install

# 2. Log in with the Google account that has access to the project
gcloud auth login
gcloud auth application-default login

# 3. Set the default project + region
gcloud config set project osu-genesis-hub
gcloud config set run/region us-west1
gcloud config set compute/region us-west1

# 4. Confirm
gcloud config list
gcloud projects describe osu-genesis-hub --format='value(name,projectNumber)'
```

If step 2 says "permission denied" on the project, ask the project
owner (sponsor / previous capstone owner) to add you to the
`roles/run.admin` and `roles/secretmanager.secretAccessor` roles.

---

## Looking at what's running

```bash
# All Cloud Run services in the project, with URLs
gcloud run services list

# The hub specifically
gcloud run services describe openbeavs-deploy-test \
  --region=us-west1 \
  --format='value(status.url, status.conditions[0].status)'

# All per-agent services (their names begin with "a-")
gcloud run services list --filter="metadata.name~^a-"

# Detail on one agent service
gcloud run services describe a-<agent-uuid> --region=us-west1
```

A service is healthy when `status.conditions[0].status == True`. The
URL printed by `services list` is the public URL — paste it into a
browser (for the hub) or use it as the base for `curl
.well-known/agent.json` (for an agent service).

---

## Deploying the hub

You usually do not deploy by hand. Cloud Build is wired to the GitHub
repo: every merge to `main` triggers `cloudbuild.yaml` and pushes a
new revision to `openbeavs-deploy-test`.

### Watch a CI deploy in progress

```bash
gcloud builds list --limit=5
gcloud builds log <BUILD_ID>     # live tail
```

### Deploy the hub from your laptop (rare)

Only do this when CI is broken and you need a hotfix out fast.

```bash
# From the repo root
./deploy.sh
# Or, equivalent unified path that matches CI:
gcloud builds submit --config=cloudbuild.yaml .
```

`./deploy.sh` reads `GCP_PROJECT_ID` and `GCP_REGION` from a `.env`
file. If you don't have one, copy from the deployed env or ask the
sponsor.

### Update the hub's environment without redeploying code

The hub reads most config at boot. To change one env var, you do not
need a new image:

```bash
gcloud run services update openbeavs-deploy-test \
  --region=us-west1 \
  --update-env-vars=KEY=VALUE,ANOTHER=VALUE
```

To remove an env var:

```bash
gcloud run services update openbeavs-deploy-test \
  --region=us-west1 \
  --remove-env-vars=KEY
```

---

## Per-agent service operations

### List all per-agent services

```bash
gcloud run services list --filter="metadata.name~^a-"
```

### Tail logs for one agent

```bash
gcloud run services logs read a-<agent-uuid> \
  --region=us-west1 \
  --limit=200
```

### Update the system prompt on a deployed agent without re-deploying

The system prompt is bound as the `SYSTEM_PROMPT` env var. You can
change it in place:

```bash
gcloud run services update a-<agent-uuid> \
  --region=us-west1 \
  --update-env-vars="SYSTEM_PROMPT=You answer in exactly two sentences."
```

The agent picks up the new value on its next cold start.

### Delete a per-agent service

```bash
gcloud run services delete a-<agent-uuid> --region=us-west1
```

This removes the service but does **not** clean up the agent row in
the hub's database — that is a separate hub-side delete on
`/workspace/agents`. Plan to do both.

---

## Logs

Cloud Run logs flow into Cloud Logging.

### One-shot read

```bash
# Hub logs, last 200 lines
gcloud run services logs read openbeavs-deploy-test \
  --region=us-west1 --limit=200

# Same, but only errors
gcloud run services logs read openbeavs-deploy-test \
  --region=us-west1 --limit=200 \
  --log-filter='severity>=ERROR'
```

### Live tail (the closest thing to `tail -f`)

```bash
gcloud beta run services logs tail openbeavs-deploy-test --region=us-west1
```

### Searching across services

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=WARNING' \
  --limit=100 --format=json
```

### The web UI

`https://console.cloud.google.com/run?project=osu-genesis-hub` →
click a service → **Logs** tab. Free-text search and time filtering
are usually faster here than on the CLI.

---

## Rolling back

Cloud Run keeps every revision. To revert the hub to an earlier one
without a new build:

```bash
# 1. List revisions, newest first
gcloud run revisions list \
  --service=openbeavs-deploy-test --region=us-west1

# 2. Send 100% of traffic to the chosen revision
gcloud run services update-traffic openbeavs-deploy-test \
  --region=us-west1 \
  --to-revisions=<REVISION_NAME>=100
```

To gradually roll forward (canary), use `--to-revisions=<NEW>=10` and
watch the error rate before pushing 100%.

You can also do this in the Cloud Run console: select the service,
click **Manage Traffic**, and drag the slider.

---

## Common operational scenarios

### "The hub returned 502 for one user"

1. Check Cloud Run uptime: `gcloud run services describe
   openbeavs-deploy-test --region=us-west1 --format='value(status.url,
   status.conditions[].status)'`.
2. Tail logs filtered to `severity>=ERROR` for the last 30 minutes.
3. If the error trace points at a per-agent JSON-RPC call, check that
   agent's service — it might be cold-starting or the API key is
   missing. See `docs/PROD_API_KEYS.md`.

### "I deployed an agent, but chat returns the API-key-missing envelope"

The Cloud Run service was created but Secret Manager wasn't wired up
yet, or the runtime SA lacks `secretmanager.secretAccessor` on the
secret. Re-read **Section 3** of `docs/PROD_API_KEYS.md`.

### "I want to nuke a stuck deploy"

```bash
gcloud run services delete a-<agent-uuid> --region=us-west1
# Then on the hub UI, delete the agent row from /workspace/agents.
```

### "The hub doesn't have gcloud on PATH and 'Deploy to Cloud Run' fails"

The hub's container image does not currently bundle the gcloud CLI.
The deploy code path therefore requires either (a) the hub run with
`OPENBEAVS_CLOUD_RUN_DISABLED=1` and admins use the in-hub internal
mode, or (b) a future PR that ships gcloud (or the Cloud Run REST
client library) inside the hub image. Until that PR lands, set the
disable flag for prod hubs that should not provision per-agent
services.

---

## Why the prod hub returns 503 on "Deploy to Cloud Run service"

`cloudbuild.yaml` sets `OPENBEAVS_CLOUD_RUN_DISABLED=1` on the
`openbeavs-deploy-test` service on purpose. Two gaps in the hub
image make the in-UI button non-functional today:

1. **No `gcloud` CLI in the hub image.** The base image is
   `python:3.11-slim` and the root `Dockerfile` does not
   `apt-get install google-cloud-sdk` or pip-install
   `google-cloud-run`. The current `utils/cloud_run.py` shells
   out to `gcloud run deploy`, so the call would 502.
2. **No `agents/` directory inside the hub image.** The
   `Dockerfile` only `COPY`s `front/backend/open_webui/` and the
   built static assets. `utils/cloud_run.py` resolves the source
   dir at `BASE_DIR.parent / "agents"`, which doesn't exist
   inside the deployed container.

So the prod hub UI button intentionally returns a clean 503
("Cloud Run deploys are disabled on this hub") rather than
crashing with a 500 or stack trace.

### How to actually deploy a per-agent service today

Until the follow-up PR (Path B — Cloud Run Admin REST API + ADC,
plus `COPY agents/...` in the `Dockerfile`) lands, deploy from a
developer laptop where both gcloud and the agent source dirs are
present:

```bash
cd /path/to/OpenBeavs/front/backend
PYTHONPATH=. python <<'EOF'
from open_webui.utils.cloud_run import deploy_provider_agent
url = deploy_provider_agent(
    "smoke-deadbeef-1234",
    provider="anthropic",
    model="claude-sonnet-4-6",
    system_prompt="You answer in exactly one sentence.",
)
print("Deployed to:", url)
EOF
```

This drives the same helper the router would call. The Secret
Manager wiring in `docs/PROD_API_KEYS.md` still applies — the
runtime SA on the *agent's* Cloud Run service is what reads the
secret, regardless of whether the deploy was triggered from the
hub UI or a laptop.

### Flipping the gate off (after Path B ships)

```bash
gcloud run services update openbeavs-deploy-test \
  --region=us-west1 \
  --remove-env-vars=OPENBEAVS_CLOUD_RUN_DISABLED
```

Then remove `OPENBEAVS_CLOUD_RUN_DISABLED=1` from
`cloudbuild.yaml`'s `--set-env-vars` so the next CI deploy
doesn't re-add it.

---

## Provider keys on the hub itself (separate from per-agent services)

Internal-mode agents (the default — Cloud Run checkbox unchecked)
are served *by the hub container* in-process. They call the LLM
provider directly from the hub, so the hub needs at least one of:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

This is **separate** from the per-agent secret bindings in
`docs/PROD_API_KEYS.md`: those wire keys onto each provisioned
Cloud Run service; this wires keys onto the hub itself for the
in-process path.

Provision via Secret Manager (same secret names as the per-agent
flow — one source of truth):

```bash
PROJECT=osu-genesis-hub
PN=$(gcloud projects describe $PROJECT --format='value(projectNumber)')

# Grant the hub's runtime SA read access to whichever secrets it needs.
# (Skip any provider you do not want available on the hub.)
for SECRET in anthropic-api-key openai-api-key gemini-api-key; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${PN}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT
done

# Bind the keys on the hub. --update-secrets keeps values out of
# revision metadata.
gcloud run services update openbeavs-deploy-test \
  --region=us-west1 \
  --update-secrets=ANTHROPIC_API_KEY=anthropic-api-key:latest,OPENAI_API_KEY=openai-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest
```

You only need to do this once per project; CI deploys preserve
secret bindings across revisions. If you only want one provider
live for now, drop the others from the `--update-secrets` line.

### Verifying

```bash
gcloud run services describe openbeavs-deploy-test \
  --region=us-west1 \
  --format='value(spec.template.spec.containers[0].env)'
# Expect: ANTHROPIC_API_KEY -> secretKeyRef (not value), and similar
# for any other providers you bound.
```

### Why this matters operationally

Without a key on the hub, any chat with an internal-mode agent
returns `502: ANTHROPIC_API_KEY is not set on the hub; cannot run
internal agent` (or the equivalent for the configured provider).
The reply path no longer self-HTTPS-calls (that was the source of
the 60 s `ReadTimeout` we hit before the in-process short-circuit
shipped), so the error surfaces immediately rather than after a
minute.

---

## Cost overview

Cloud Run charges per request CPU time and per request count, with a
generous monthly free tier. Things that move the needle:

- **Number of per-agent services.** Each one is a separately scaled
  service — each gets its own warm/cold cycle. Don't deploy hundreds
  unless you mean to.
- **Memory & CPU.** The hub is configured `--memory=8Gi --cpu=4`
  in `cloudbuild.yaml`. Per-agent services default to `1Gi`. Bumping
  these is the largest single lever on the bill.
- **Real LLM calls.** Each chat turn against a deployed agent
  triggers a paid API call to the underlying provider. The Cloud
  Run cost is small next to the provider cost.

You can check actual spend at:
`https://console.cloud.google.com/billing/?project=osu-genesis-hub` →
**Reports** → filter by service.

---

## When you get really stuck

- `gcloud feedback` opens a bug template in your browser pre-filled
  with your last command and stderr — useful for support tickets.
- Cloud Run incidents:
  `https://status.cloud.google.com/products/cloud-run`.
- Sponsor / previous capstone owner: see `CLAUDE.md` § 19 for emails.
