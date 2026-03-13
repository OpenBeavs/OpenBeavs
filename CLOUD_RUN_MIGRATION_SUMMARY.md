# Conversation Summary: Cloud Run → Cloud SQL + SSO Integration

## Project Overview
**Goal**: Connect the live OpenBeavs Cloud Run service to a PostgreSQL Cloud SQL database
(migrated from us-central1 to us-west1), wire it up via Secret Manager, and enable
Microsoft Azure AD SSO on the deployed app.

**Date**: March 5–6, 2026
**Status**: ✅ Complete — Cloud Run connected to Cloud SQL, Microsoft SSO working

---

## Starting State (Before This Session)

- **Cloud Run service**: `openbeavs-deploy-test` running in `us-west1`
  - URL: https://openbeavs-deploy-test-716080272371.us-west1.run.app
  - Was using local **SQLite** database (not Postgres)
  - Using the **default compute service account** (not `genesis-ai-hub-sa`)
  - No Cloud SQL connection, no `DATABASE_URL` env var
- **Cloud SQL instance**: `genesis-ai-hub-db` running in **us-central1** (region mismatch)
  - PostgreSQL 15, db-f1-micro, public IP: 104.154.141.27
  - Already populated with user/chat data from a previous migration
- **Secret Manager**: Had `database-url`, `pgvector-db-url`, `microsoft-client-id` secrets
  but the `database-url` value pointed to `localhost:5433` (local proxy URL, not Cloud Run socket)
- **Microsoft SSO**: Configured in `.env` for local dev but **not** set up on Cloud Run

---

## What Was Accomplished

### 1. Infrastructure Verification ✅

**Script created**: `database/verify_cloud_status.sh`

Checks all of the following and prints a pass/warn/fail summary:
- gcloud authentication
- Old Cloud SQL instance state (us-central1)
- New Cloud SQL instance state (us-west1)
- Cloud Run service config (SA, Cloud SQL connection, DATABASE_URL)
- Secret Manager secrets (database-url, pgvector-db-url, microsoft-client-id)
- Service account IAM roles
- GCS bucket existence

**Findings from initial run**:
- ✅ Old Cloud SQL RUNNABLE
- ⚠️ New instance not yet created
- ⚠️ Cloud Run using default compute SA (not genesis-ai-hub-sa)
- ⚠️ Cloud SQL not connected to Cloud Run
- ⚠️ DATABASE_URL not set on Cloud Run
- ❌ genesis-ai-hub-sa missing `roles/storage.objectAdmin`

---

### 2. Cloud SQL Region Migration (us-central1 → us-west1) ✅

**Script created**: `database/migrate_sql_us_west1.sh`

Cloud SQL instances cannot be moved in-place — the script exports, creates a new instance,
and imports.

**What the script does**:
1. Reads the Cloud SQL service account directly from the instance
   (`gcloud sql instances describe ... --format='value(serviceAccountEmailAddress)'`)
2. Grants that SA `roles/storage.objectAdmin` at the project level (not bucket level)
   with `--condition=None` (required because the project policy has conditional bindings)
3. Waits 60 seconds for IAM propagation before attempting the export
4. Exports the `webui` database to `gs://genesis-ai-hub-uploads/migration/webui_export_*.sql`
5. Creates `genesis-ai-hub-db-west1` in `us-west1` (db-f1-micro, PostgreSQL 15)
6. Sets the postgres user password on the new instance
7. Creates the `webui` database
8. Grants the **new** instance's SA `roles/storage.objectViewer` (separate SA from old instance)
   and waits another 60s for propagation before importing
9. Imports the export file into the new instance
10. Attempts to enable pgvector extension via `gcloud sql connect`
11. Stores the Cloud Run Unix socket DATABASE_URL in Secret Manager:
    `postgresql://postgres:PASSWORD@/webui?host=/cloudsql/osu-genesis-hub:us-west1:genesis-ai-hub-db-west1`

**Re-run safety**: The script detects if the new instance already exists and skips
creation/password/database steps, resuming from the import. It also detects and reuses
an existing export file instead of re-exporting.

**Issues fixed during development**:

| Error | Fix |
|---|---|
| `HTTPError 412: service account does not have required permissions` (Step 1) | Switched from `gcloud storage buckets add-iam-policy-binding` (requires `storage.admin`) to `gcloud projects add-iam-policy-binding` (requires `resourcemanager.projectIamAdmin` which we have) |
| `Adding a binding without specifying a condition is prohibited in non-interactive mode` | Added `--condition=None` to all `add-iam-policy-binding` calls |
| `Service account service-716080272371@gcp-sa-cloud-sql.iam.gserviceaccount.com does not exist` | Replaced hardcoded SA email construction with `gcloud sql instances describe ... --format='value(serviceAccountEmailAddress)'` |
| `HTTPError 412` on Step 4 import (new instance has a different SA) | Added a second IAM grant for the new instance's SA after creation, with another 60s propagation wait |
| `line 163: --quiet: command not found` | Was a broken backslash continuation from a prior edit; resolved when file was corrected |

**New Cloud SQL instance**:
- Name: `genesis-ai-hub-db-west1`
- Region: `us-west1`
- Connection name: `osu-genesis-hub:us-west1:genesis-ai-hub-db-west1`
- Public IP: `136.118.232.155`

---

### 3. Cloud Run → Cloud SQL Connection ✅

**Script created**: `database/connect_cloud_run_to_sql.sh`

**What the script does**:
1. Verifies new Cloud SQL instance is RUNNABLE
2. Verifies `database-url` secret references the new instance
3. Ensures `genesis-ai-hub-sa` has all required roles (grants any missing ones with `--condition=None`)
4. Grants `genesis-ai-hub-sa` access to the `database-url` secret at the secret level
5. Updates the Cloud Run service:
   - `--service-account=genesis-ai-hub-sa@osu-genesis-hub.iam.gserviceaccount.com`
   - `--add-cloudsql-instances=osu-genesis-hub:us-west1:genesis-ai-hub-db-west1`
     (this enables the Cloud SQL Auth Proxy sidecar inside the container)
   - `--set-secrets=DATABASE_URL=database-url:latest`
   - `--set-env-vars=DATABASE_POOL_SIZE=2,DATABASE_POOL_MAX_OVERFLOW=4`
6. Waits up to 120s for the new revision to become healthy
7. Runs an HTTP health check against `/health`
8. Fetches recent Cloud Run logs filtered for database/error keywords

**Fix applied before running**: Added `--condition=None` to IAM binding call
(same conditional policy issue as during migration).

**Result**: Revision `openbeavs-deploy-test-00018-lgx` deployed successfully, HTTP 200,
logs confirmed settings loading from the Postgres database.

---

### 4. Microsoft SSO on Cloud Run ✅

**Script created**: `database/configure_sso.sh`

**What the script does**:
1. Interactively prompts for Microsoft Client ID, Client Secret, and Tenant ID
2. Stores each in Secret Manager (`microsoft-client-id`, `microsoft-client-secret`, `microsoft-tenant-id`)
   — creates or adds a new version if already exists
3. Grants `genesis-ai-hub-sa` read access to each secret
4. Updates Cloud Run with `--update-secrets` to mount all three as env vars
5. Sets non-sensitive OAuth config as plain env vars:
   `ENABLE_OAUTH_SIGNUP=true`, `OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true`, `MICROSOFT_OAUTH_SCOPE=openid email profile`

**Redirect URI mismatch fix**:

Azure AD returned `AADSTS50011` because Open WebUI was sending the internal regional
URL (`ahkgdqjvhq-uw.a.run.app`) as the redirect URI instead of the stable URL.

Fix: Set `MICROSOFT_REDIRECT_URI` explicitly on Cloud Run:
```bash
gcloud run services update openbeavs-deploy-test \
  --region=us-west1 \
  --project=osu-genesis-hub \
  --update-env-vars="MICROSOFT_REDIRECT_URI=https://openbeavs-deploy-test-716080272371.us-west1.run.app/oauth/microsoft/callback"
```

**Azure AD manual step required**: The redirect URI
`https://openbeavs-deploy-test-716080272371.us-west1.run.app/oauth/microsoft/callback`
must be registered under the App Registration → Authentication → Redirect URIs in Azure Portal.

---

### 5. cloudbuild.yaml Updated ✅

All Cloud Run configuration is now codified in `cloudbuild.yaml` so every CI/CD deploy
(triggered by merging to `main`) automatically applies the full production config:

```yaml
- '--service-account=genesis-ai-hub-sa@osu-genesis-hub.iam.gserviceaccount.com'
- '--add-cloudsql-instances=osu-genesis-hub:us-west1:genesis-ai-hub-db-west1'
- '--set-secrets=DATABASE_URL=database-url:latest,MICROSOFT_CLIENT_ID=microsoft-client-id:latest,MICROSOFT_CLIENT_SECRET=microsoft-client-secret:latest,MICROSOFT_CLIENT_TENANT_ID=microsoft-tenant-id:latest'
- '--set-env-vars=...,ENABLE_OAUTH_SIGNUP=true,OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true,MICROSOFT_OAUTH_SCOPE=openid email profile,MICROSOFT_REDIRECT_URI=https://openbeavs-deploy-test-716080272371.us-west1.run.app/oauth/microsoft/callback'
```

Also removed `WEBUI_SECRET_KEY=change-me-in-prod` (was a hardcoded insecure placeholder).

---

### 6. Security Hardening ✅

- Added `chat.txt` to `.gitignore` — a plaintext chat log in the repo root contained
  the Postgres password and Microsoft client secret; it was never committed but must be deleted
- All secrets go through Secret Manager; no plaintext credentials in `cloudbuild.yaml` or env vars
- Teammates get DB access via IAM (`roles/secretmanager.secretAccessor` on the secret),
  not by sharing passwords directly

---

## Current Architecture

```
GitHub (main branch merge)
        │
        ▼
Cloud Build (cloudbuild.yaml)
  - Builds unified Docker image (SvelteKit + FastAPI)
  - Pushes to Artifact Registry (us-west1)
        │
        ▼
Cloud Run: openbeavs-deploy-test (us-west1)
  Service account: genesis-ai-hub-sa
  ├── Cloud SQL Auth Proxy sidecar
  │     └── Unix socket → genesis-ai-hub-db-west1
  ├── Secret Manager mounts:
  │     ├── DATABASE_URL        (database-url)
  │     ├── MICROSOFT_CLIENT_ID (microsoft-client-id)
  │     ├── MICROSOFT_CLIENT_SECRET (microsoft-client-secret)
  │     └── MICROSOFT_CLIENT_TENANT_ID (microsoft-tenant-id)
  └── Env vars:
        ├── ENABLE_OAUTH_SIGNUP=true
        ├── MICROSOFT_REDIRECT_URI=https://...716080272371.us-west1.run.app/oauth/microsoft/callback
        ├── DATABASE_POOL_SIZE=2
        └── ... (other app config)
        │
        ▼
Cloud SQL: genesis-ai-hub-db-west1 (us-west1)
  PostgreSQL 15, db-f1-micro
  Connection: osu-genesis-hub:us-west1:genesis-ai-hub-db-west1
  Database: webui (migrated from genesis-ai-hub-db in us-central1)
```

---

## Files Created / Modified

### New Scripts (`/database/`)
| File | Purpose |
|---|---|
| `verify_cloud_status.sh` | Diagnostic — checks all cloud resources before running migration |
| `migrate_sql_us_west1.sh` | Migrates Cloud SQL from us-central1 to us-west1, updates Secret Manager |
| `connect_cloud_run_to_sql.sh` | Connects Cloud Run to Cloud SQL, mounts DATABASE_URL from Secret Manager |
| `configure_sso.sh` | Stores Microsoft SSO credentials in Secret Manager, configures Cloud Run |

### Modified Files
| File | Change |
|---|---|
| `cloudbuild.yaml` | Added service account, Cloud SQL connection, all secrets, SSO env vars, redirect URI |
| `.gitignore` | Added `chat.txt` |

---

## Secret Manager Secrets (Current State)

| Secret Name | Contents | Used By |
|---|---|---|
| `database-url` | PostgreSQL connection string with Unix socket path for Cloud Run | Cloud Run env var `DATABASE_URL` |
| `pgvector-db-url` | Same as database-url (for vector DB) | App code if enabled |
| `microsoft-client-id` | Azure App Registration Application ID | Cloud Run env var `MICROSOFT_CLIENT_ID` |
| `microsoft-client-secret` | Azure OAuth client secret | Cloud Run env var `MICROSOFT_CLIENT_SECRET` |
| `microsoft-tenant-id` | Azure AD tenant ID | Cloud Run env var `MICROSOFT_CLIENT_TENANT_ID` |

The `database-url` secret format for Cloud Run (Unix socket, no port):
```
postgresql://postgres:PASSWORD@/webui?host=/cloudsql/osu-genesis-hub:us-west1:genesis-ai-hub-db-west1
```

---

## IAM Roles Summary

### `genesis-ai-hub-sa@osu-genesis-hub.iam.gserviceaccount.com`
| Role | Purpose |
|---|---|
| `roles/cloudsql.client` | Connect to Cloud SQL via Auth Proxy |
| `roles/secretmanager.secretAccessor` | Read secrets at runtime |
| `roles/storage.objectAdmin` | Read/write GCS bucket |

### Cloud SQL instance SA (`p716080272371-0zywbb@gcp-sa-cloud-sql.iam.gserviceaccount.com`)
| Role | Purpose |
|---|---|
| `roles/storage.objectAdmin` (old instance SA) | Export database to GCS |
| `roles/storage.objectViewer` (new instance SA) | Import database from GCS |

---

## Cleanup TODO

- [ ] Delete the old Cloud SQL instance once data is verified:
  ```bash
  gcloud sql instances delete genesis-ai-hub-db --project=osu-genesis-hub
  ```
- [ ] Delete the temporary GCS export file:
  ```bash
  gcloud storage rm "gs://genesis-ai-hub-uploads/migration/webui_export_*.sql"
  ```
- [ ] Delete `chat.txt` from local disk (contains plaintext credentials):
  ```bash
  rm /Users/minsoup/random/OpenBeavs/chat.txt
  ```
- [ ] Rotate the Microsoft client secret in Azure AD (it was shared in plaintext during this session)
  then re-run `./database/configure_sso.sh` with the new secret

---

## Known Issues / Gotchas

1. **IAM propagation**: All `gcloud projects add-iam-policy-binding` calls require
   `--condition=None` because the project policy contains conditional bindings.
   Without it, gcloud errors in non-interactive mode.
   A 60-second sleep is needed after granting before Cloud SQL export/import will work.

2. **Cloud SQL SA per instance**: Each Cloud SQL instance has a unique service account.
   Granting GCS access to the old instance's SA does **not** cover the new instance.
   Both must be granted separately.

3. **Two Cloud Run URLs**: Cloud Run has both a stable URL
   (`716080272371.us-west1.run.app`) and an internal regional URL
   (`ahkgdqjvhq-uw.a.run.app`). Open WebUI uses the internal one for OAuth redirects
   unless `MICROSOFT_REDIRECT_URI` is set explicitly. Always set it to the stable URL.

4. **`WEBUI_SECRET_KEY`**: Was previously set to `change-me-in-prod` in cloudbuild.yaml.
   Removed — it should be added to Secret Manager and mounted properly before production use.

---

## Verify Everything Still Works

```bash
# 1. Run the full status check
./database/verify_cloud_status.sh

# 2. Check the live site
open https://openbeavs-deploy-test-716080272371.us-west1.run.app

# 3. Tail live logs
gcloud logging tail \
  'resource.type=cloud_run_revision AND resource.labels.service_name=openbeavs-deploy-test' \
  --project=osu-genesis-hub

# 4. Verify DB connection string in Secret Manager
gcloud secrets versions access latest --secret="database-url" --project=osu-genesis-hub
```
