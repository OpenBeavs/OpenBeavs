#!/bin/bash
# =============================================================================
# verify_cloud_status.sh
# Checks the current state of Cloud Run, Cloud SQL, and Secret Manager
# before running the migration or connection scripts.
#
# Usage: ./database/verify_cloud_status.sh
# =============================================================================

set -euo pipefail

# --- Config ------------------------------------------------------------------
PROJECT_ID="osu-genesis-hub"
CLOUD_RUN_SERVICE="openbeavs-deploy-test"
CLOUD_RUN_REGION="us-west1"
OLD_SQL_INSTANCE="genesis-ai-hub-db"
OLD_SQL_REGION="us-central1"
NEW_SQL_INSTANCE="genesis-ai-hub-db-west1"
NEW_SQL_REGION="us-west1"
SERVICE_ACCOUNT="genesis-ai-hub-sa@osu-genesis-hub.iam.gserviceaccount.com"
GCS_BUCKET="genesis-ai-hub-uploads"

PASS=0
WARN=0
FAIL=0

ok()   { echo "  ✅ $1"; PASS=$((PASS + 1)); }
warn() { echo "  ⚠️  $1"; WARN=$((WARN + 1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL + 1)); }
header() { echo ""; echo "── $1 ──────────────────────────────────────────"; }

# --- 1. gcloud auth ----------------------------------------------------------
header "1. gcloud authentication"
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)
if [ -z "$ACTIVE_ACCOUNT" ]; then
    fail "Not authenticated. Run: gcloud auth login"
    echo "Cannot continue without authentication."
    exit 1
fi
ok "Authenticated as: $ACTIVE_ACCOUNT"

# Set the default project for subsequent commands
gcloud config set project "$PROJECT_ID" --quiet

# --- 2. Cloud SQL (us-central1 — old instance) --------------------------------
header "2. Cloud SQL — old instance ($OLD_SQL_INSTANCE in $OLD_SQL_REGION)"
OLD_SQL_STATUS=$(gcloud sql instances describe "$OLD_SQL_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(state)' 2>/dev/null || echo "NOT_FOUND")

if [ "$OLD_SQL_STATUS" = "NOT_FOUND" ]; then
    warn "Instance '$OLD_SQL_INSTANCE' not found in $OLD_SQL_REGION (may already be migrated)"
elif [ "$OLD_SQL_STATUS" = "RUNNABLE" ]; then
    OLD_SQL_TIER=$(gcloud sql instances describe "$OLD_SQL_INSTANCE" \
        --project="$PROJECT_ID" --format='value(settings.tier)' 2>/dev/null)
    OLD_SQL_IP=$(gcloud sql instances describe "$OLD_SQL_INSTANCE" \
        --project="$PROJECT_ID" --format='value(ipAddresses[0].ipAddress)' 2>/dev/null || echo "none")
    ok "Instance running (tier: $OLD_SQL_TIER, public IP: $OLD_SQL_IP)"
else
    fail "Instance in unexpected state: $OLD_SQL_STATUS"
fi

# --- 3. Cloud SQL (us-west1 — new instance) -----------------------------------
header "3. Cloud SQL — new instance ($NEW_SQL_INSTANCE in $NEW_SQL_REGION)"
NEW_SQL_STATUS=$(gcloud sql instances describe "$NEW_SQL_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(state)' 2>/dev/null || echo "NOT_FOUND")

if [ "$NEW_SQL_STATUS" = "NOT_FOUND" ]; then
    warn "Not yet created — run migrate_sql_us_west1.sh next"
elif [ "$NEW_SQL_STATUS" = "RUNNABLE" ]; then
    ok "Instance already exists and is running"
else
    warn "Instance exists but in state: $NEW_SQL_STATUS"
fi

# --- 4. Cloud Run service -----------------------------------------------------
header "4. Cloud Run — $CLOUD_RUN_SERVICE ($CLOUD_RUN_REGION)"
CR_DESCRIBE=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$CLOUD_RUN_REGION" \
    --project="$PROJECT_ID" \
    --format='json' 2>/dev/null || echo "{}")

if [ "$CR_DESCRIBE" = "{}" ]; then
    fail "Cloud Run service '$CLOUD_RUN_SERVICE' not found"
else
    CR_URL=$(echo "$CR_DESCRIBE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',{}).get('url','?'))")
    CR_SA=$(echo "$CR_DESCRIBE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('spec',{}).get('template',{}).get('spec',{}).get('serviceAccountName','(default compute SA)'))" 2>/dev/null || echo "(unknown)")
    CR_SQL=$(echo "$CR_DESCRIBE" | python3 -c "import sys,json; d=json.load(sys.stdin); ann=d.get('spec',{}).get('template',{}).get('metadata',{}).get('annotations',{}); print(ann.get('run.googleapis.com/cloudsql-instances','none'))" 2>/dev/null || echo "none")
    CR_DB_SECRET=$(echo "$CR_DESCRIBE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
containers = d.get('spec',{}).get('template',{}).get('spec',{}).get('containers',[])
for c in containers:
    for env in c.get('env', []):
        if env.get('name') == 'DATABASE_URL':
            vf = env.get('valueFrom', {})
            ref = vf.get('secretKeyRef', {})
            if ref:
                print(f\"SECRET:{ref.get('name','')}:{ref.get('key','')}\")
            else:
                print('ENV_VAR (plaintext)')
            sys.exit(0)
print('not set')
" 2>/dev/null || echo "unknown")

    ok "Service URL: $CR_URL"
    if [[ "$CR_SA" == *"genesis-ai-hub-sa"* ]]; then
        ok "Service account: $CR_SA"
    else
        warn "Service account: $CR_SA (expected genesis-ai-hub-sa)"
    fi

    if [ "$CR_SQL" = "none" ]; then
        warn "Cloud SQL NOT connected to Cloud Run yet"
    else
        ok "Cloud SQL connected: $CR_SQL"
    fi

    if [ "$CR_DB_SECRET" = "not set" ]; then
        warn "DATABASE_URL not configured in Cloud Run"
    else
        ok "DATABASE_URL source: $CR_DB_SECRET"
    fi
fi

# --- 5. Secret Manager --------------------------------------------------------
header "5. Secret Manager"
for secret_name in "database-url" "pgvector-db-url" "microsoft-client-id"; do
    SECRET_EXISTS=$(gcloud secrets describe "$secret_name" \
        --project="$PROJECT_ID" \
        --format='value(name)' 2>/dev/null || echo "NOT_FOUND")
    if [ "$SECRET_EXISTS" = "NOT_FOUND" ]; then
        if [ "$secret_name" = "database-url" ]; then
            fail "Secret missing (required): $secret_name — will be created by migrate script"
        else
            warn "Secret not found: $secret_name"
        fi
    else
        # Get the number of versions to show it has a value
        VERSION_COUNT=$(gcloud secrets versions list "$secret_name" \
            --project="$PROJECT_ID" \
            --filter="state=ENABLED" \
            --format='value(name)' 2>/dev/null | wc -l | tr -d ' ')
        ok "Secret exists: $secret_name ($VERSION_COUNT enabled version(s))"
    fi
done

# --- 6. Service account IAM roles ---------------------------------------------
header "6. Service account IAM roles ($SERVICE_ACCOUNT)"
SA_ROLES=$(gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[].members" \
    --filter="bindings.members:$SERVICE_ACCOUNT" \
    --format='value(bindings.role)' 2>/dev/null || echo "")

if [ -z "$SA_ROLES" ]; then
    fail "Could not retrieve IAM roles (permission error or SA does not exist)"
else
    EXPECTED_ROLES=("roles/cloudsql.client" "roles/storage.objectAdmin" "roles/secretmanager.secretAccessor")
    for role in "${EXPECTED_ROLES[@]}"; do
        if echo "$SA_ROLES" | grep -q "$role"; then
            ok "Has role: $role"
        else
            fail "Missing role: $role"
        fi
    done
fi

# --- 7. GCS bucket ------------------------------------------------------------
header "7. GCS bucket ($GCS_BUCKET)"
BUCKET_EXISTS=$(gcloud storage buckets describe "gs://$GCS_BUCKET" \
    --project="$PROJECT_ID" \
    --format='value(name)' 2>/dev/null || echo "NOT_FOUND")
if [ "$BUCKET_EXISTS" = "NOT_FOUND" ]; then
    fail "Bucket 'gs://$GCS_BUCKET' not found (needed for SQL export/import)"
else
    ok "Bucket exists: gs://$GCS_BUCKET"
fi

# --- Summary ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════"
echo " Results: ✅ $PASS passed  ⚠️  $WARN warnings  ❌ $FAIL failed"
echo "═══════════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Recommended next steps:"
    if [ "$NEW_SQL_STATUS" = "NOT_FOUND" ]; then
        echo "  1. Run: ./database/migrate_sql_us_west1.sh   (migrate Cloud SQL to us-west1)"
    fi
    if echo "${CR_SQL:-}" | grep -qv "genesis-ai-hub-db-west1"; then
        echo "  2. Run: ./database/connect_cloud_run_to_sql.sh   (connect Cloud Run to Cloud SQL)"
    fi
fi
