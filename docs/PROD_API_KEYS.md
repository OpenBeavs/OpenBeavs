# Production API Keys for Deployed Agents

When an admin uses the **Deploy Agent** form with **"Deploy to dedicated
Cloud Run service"** checked, the hub provisions a per-agent Cloud Run
service backed by one of the provider shims in
`agents/{claude,chatgpt,gemini}-agent/`. Those shims expect their
provider's API key in a specific environment variable. We bind that env
var on each Cloud Run service via **Google Secret Manager** —
`--update-secrets`, not `--set-env-vars` — so the key value is not
visible in revision metadata or `gcloud run services describe` output.

This page is the operational checklist for setting those secrets up.

---

## TL;DR by provider

| Provider | Env var on the agent service | Default Secret Manager name |
|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic-api-key` |
| OpenAI    | `CHATGPT_API_KEY`   | `openai-api-key` |
| Gemini    | `GEMINI_API_KEY`    | `gemini-api-key` |

If you want a different Secret Manager name (e.g. multi-tenant
deployments, key rotation strategies, or you already have a secret
under a different name), set this on the **hub** Cloud Run service:

```
OPENBEAVS_SECRET_ANTHROPIC_API_KEY=my-team-anthropic-key
OPENBEAVS_SECRET_CHATGPT_API_KEY=my-team-openai-key
OPENBEAVS_SECRET_GEMINI_API_KEY=my-team-gemini-key
```

The hub will then bind `ANTHROPIC_API_KEY` (etc.) on the deployed agent
to whatever Secret Manager name you supply.

---

## One-time setup (per provider)

Pick the provider you want to enable. Repeat for each.

### 1. Create the secret in Secret Manager

```bash
# Anthropic example
gcloud secrets create anthropic-api-key \
  --replication-policy=automatic \
  --project=osu-genesis-hub
```

Replace `osu-genesis-hub` with your project. Run once per provider.

### 2. Add the actual key as the first version

```bash
echo -n "$YOUR_REAL_API_KEY" \
  | gcloud secrets versions add anthropic-api-key \
      --data-file=- \
      --project=osu-genesis-hub
```

`echo -n` matters — a trailing newline will get included in the secret
and break the API call.

### 3. Grant the agent's runtime service account access

When `gcloud run deploy --source=...` builds an agent service, it runs
as the project's default Cloud Run runtime SA
(`<project-number>-compute@developer.gserviceaccount.com`). Grant it
read access to the secret:

```bash
PROJECT=osu-genesis-hub
PROJECT_NUMBER=$(gcloud projects describe $PROJECT \
  --format='value(projectNumber)')

gcloud secrets add-iam-policy-binding anthropic-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=$PROJECT
```

If you've configured a dedicated SA for Cloud Run, substitute its email
on `--member`.

### 4. (Optional) Verify before deploying an agent

```bash
gcloud secrets versions access latest \
  --secret=anthropic-api-key \
  --project=osu-genesis-hub
```

Should print the literal key. If it errors with "permission denied",
revisit step 3.

---

## Verifying a deployed agent uses the secret

After an admin clicks **Deploy** in the UI, you can confirm the binding
was applied correctly without revealing the key value:

```bash
# Get the service name (the hub uses "a-<agent-uuid>" as the service name)
gcloud run services list --project=osu-genesis-hub --region=us-west1

# Inspect just the secret bindings; the key value is not shown
gcloud run services describe a-<agent-uuid> \
  --project=osu-genesis-hub --region=us-west1 \
  --format='value(spec.template.spec.containers[0].env)'
```

You should see the env var name (e.g. `ANTHROPIC_API_KEY`) bound to a
`secretKeyRef` rather than a `value`. If `value` appears, the deploy
took the wrong code path — open a bug.

---

## Rotating a key

1. Add a new version to the existing secret:
   ```bash
   echo -n "$NEW_KEY" \
     | gcloud secrets versions add anthropic-api-key --data-file=-
   ```
2. The agent services are deployed with `:latest`, so they pick up the
   new version on the next cold start. Force one immediately by
   redeploying the service or using
   `gcloud run services update --update-secrets=...:latest`.
3. Disable the old version once you've confirmed agents are working
   with the new key:
   ```bash
   gcloud secrets versions disable 1 --secret=anthropic-api-key
   ```
   (Replace `1` with the old version number.)

---

## Cost-control note

Each deployed agent that uses a real API key burns provider credit on
every chat turn routed through it. Recommendations:

- Keep the **provider quota** low when you first wire up a new key and
  raise it after you've verified the prompts in production.
- The hub badges each agent in the workspace UI with its provider and
  model. Audit that list periodically — every badge is a potential
  cost line item.
- For dev environments, set `OPENBEAVS_CLOUD_RUN_DISABLED=1` on the
  hub. The deploy form's "Deploy to dedicated Cloud Run service"
  checkbox will return a clean 503 if checked, and unchecked deploys
  fall through to the in-hub internal-mode path which still respects
  the per-agent system prompt but does not provision new GCP services.

---

## Cold-start expectation for the demo

A freshly deployed agent service is usually cold for the first request
after deploy. Expect ~3–5 s of latency on the very first chat turn (or
on the first curl in `DEMO_VIDEO_BRIEF.md`). Later turns are warm. If
the demo timing matters, send one warm-up request between **Deploy**
and the screen recording.

---

## Laptop-driven deploys (current default)

The deployed prod hub returns 503 when an admin checks "Deploy to
Cloud Run service" — the hub image doesn't ship `gcloud` yet, so the
in-UI button is intentionally gated off via
`OPENBEAVS_CLOUD_RUN_DISABLED=1`. See
`docs/CLOUD_RUN_OPERATIONS.md` for the gate's rationale and the
laptop-side script that drives the same helper the router would.

The Secret Manager wiring on this page is unchanged for that path.
The runtime SA that reads each secret is the *agent's* Cloud Run
service account (`<project-number>-compute@developer.gserviceaccount.com`
by default), not the hub's. Whether the deploy is triggered from the
hub UI or a laptop, the per-agent service still reads
`anthropic-api-key:latest` (etc.) at cold start.

---

## Out-of-scope

- Multi-tenant key isolation (per-user secret routing) — not supported
  in this PR. All deployed agents in a hub share one secret per
  provider.
- Shared service accounts for cross-project deploys — single-project
  only here.
- Quota guardrails / per-user spend caps — separate concern; tracked
  with the rate-limit work under SEC-002.
