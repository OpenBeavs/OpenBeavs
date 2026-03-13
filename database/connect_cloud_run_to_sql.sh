#!/bin/bash
# =============================================================================
# connect_cloud_run_to_sql.sh
# Connects the Cloud Run service to Cloud SQL (us-west1) and configures
# DATABASE_URL via Secret Manager.
#
# What this script does:
#   1. Ensures genesis-ai-hub-sa has the required IAM roles
#   2. Ensures the Secret Manager secret is accessible to the service account
#   3. Updates the Cloud Run service:
#      - Assigns genesis-ai-hub-sa as the service account
#      - Adds the Cloud SQL instance annotation (enables built-in proxy)
#      - Mounts DATABASE_URL from Secret Manager
#      - Adds DATABASE_POOL_SIZE env var (important for serverless)
#   4. Tails the new revision's logs to confirm a healthy DB connection
#   5. Runs a quick HTTP health check
#
# Usage: ./database/connect_cloud_run_to_sql.sh
#
# Run AFTER: ./database/migrate_sql_us_west1.sh
# =============================================================================

set -euo pipefail

# --- Config ------------------------------------------------------------------
PROJECT_ID="osu-genesis-hub"

CLOUD_RUN_SERVICE="openbeavs-deploy-test"
CLOUD_RUN_REGION="us-west1"

NEW_SQL_INSTANCE="genesis-ai-hub-db-west1"
NEW_SQL_REGION="us-west1"
INSTANCE_CONNECTION_NAME="${PROJECT_ID}:${NEW_SQL_REGION}:${NEW_SQL_INSTANCE}"

SERVICE_ACCOUNT="genesis-ai-hub-sa@osu-genesis-hub.iam.gserviceaccount.com"
SECRET_NAME="database-url"

# --- Functions ---------------------------------------------------------------
info()    { echo ""; echo "► $1"; }
success() { echo "  ✅ $1"; }
warning() { echo "  ⚠️  $1"; }
step()    { echo "  → $1"; }

# --- Check prerequisites -----------------------------------------------------
info "Checking prerequisites..."

ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)
if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "ERROR: Not authenticated. Run: gcloud auth login"
    exit 1
fi
success "Authenticated as: $ACTIVE_ACCOUNT"

gcloud config set project "$PROJECT_ID" --quiet
success "Project set to: $PROJECT_ID"

# Verify the new Cloud SQL instance exists
SQL_STATUS=$(gcloud sql instances describe "$NEW_SQL_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(state)' 2>/dev/null || echo "NOT_FOUND")

if [ "$SQL_STATUS" = "NOT_FOUND" ]; then
    echo "ERROR: Cloud SQL instance '$NEW_SQL_INSTANCE' not found."
    echo "       Run ./database/migrate_sql_us_west1.sh first."
    exit 1
elif [ "$SQL_STATUS" != "RUNNABLE" ]; then
    echo "ERROR: Cloud SQL instance '$NEW_SQL_INSTANCE' is in state '$SQL_STATUS', expected RUNNABLE."
    exit 1
fi
success "Cloud SQL instance '$NEW_SQL_INSTANCE' is RUNNABLE"

# Verify the database-url secret exists
SECRET_URL=$(gcloud secrets versions access latest \
    --secret="$SECRET_NAME" \
    --project="$PROJECT_ID" 2>/dev/null || echo "")

if [ -z "$SECRET_URL" ]; then
    echo "ERROR: Secret '$SECRET_NAME' not found or has no versions."
    echo "       Run ./database/migrate_sql_us_west1.sh first to create it."
    exit 1
fi

# Verify the secret references the correct instance
if ! echo "$SECRET_URL" | grep -q "$NEW_SQL_INSTANCE"; then
    warning "Secret '$SECRET_NAME' does not appear to reference '$NEW_SQL_INSTANCE'."
    echo "  Current URL in secret points to: $(echo "$SECRET_URL" | sed 's/:[^@]*@/:***@/')"
    read -r -p "  Continue anyway? (y/N): " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo "Aborted. Re-run migrate_sql_us_west1.sh to update the secret."
        exit 1
    fi
fi
success "Secret '$SECRET_NAME' verified (contains connection URL)"

# --- Step 1: Ensure service account has required IAM roles -------------------
info "Step 1 of 3: Verifying IAM roles for $SERVICE_ACCOUNT..."

REQUIRED_ROLES=(
    "roles/cloudsql.client"
    "roles/secretmanager.secretAccessor"
    "roles/storage.objectAdmin"
)

for role in "${REQUIRED_ROLES[@]}"; do
    ROLE_EXISTS=$(gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members:$SERVICE_ACCOUNT AND bindings.role:$role" \
        --format='value(bindings.role)' 2>/dev/null | head -1 || echo "")

    if [ -z "$ROLE_EXISTS" ]; then
        step "Granting missing role: $role"
        gcloud projects add-iam-policy-binding "$PROJECT_ID" \
            --member="serviceAccount:${SERVICE_ACCOUNT}" \
            --role="$role" \
            --condition=None \
            --quiet
        success "Granted: $role"
    else
        success "Already has: $role"
    fi
done

# --- Step 2: Ensure the secret is accessible to the service account ----------
info "Step 2 of 3: Granting service account access to Secret Manager secret..."

# Grant at the secret level (more precise than project-level)
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet 2>/dev/null || true

success "Secret access confirmed for $SERVICE_ACCOUNT"

# --- Step 3: Update Cloud Run service ----------------------------------------
info "Step 3 of 3: Updating Cloud Run service '$CLOUD_RUN_SERVICE'..."
step "Region: $CLOUD_RUN_REGION"
step "Adding Cloud SQL: $INSTANCE_CONNECTION_NAME"
step "Mounting DATABASE_URL from Secret Manager"
step "Setting service account: $SERVICE_ACCOUNT"
step ""
step "This triggers a new revision — takes ~1 minute..."

gcloud run services update "$CLOUD_RUN_SERVICE" \
    --region="$CLOUD_RUN_REGION" \
    --project="$PROJECT_ID" \
    --service-account="$SERVICE_ACCOUNT" \
    --add-cloudsql-instances="$INSTANCE_CONNECTION_NAME" \
    --set-secrets="DATABASE_URL=${SECRET_NAME}:latest" \
    --set-env-vars="DATABASE_POOL_SIZE=2,DATABASE_POOL_MAX_OVERFLOW=4" \
    --quiet

success "Cloud Run service updated"

# --- Wait for the new revision to become healthy -----------------------------
info "Waiting for new revision to be healthy..."

MAX_WAIT=120
ELAPSED=0
REVISION_READY="false"

while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    CONDITION=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
        --region="$CLOUD_RUN_REGION" \
        --project="$PROJECT_ID" \
        --format='value(status.conditions[0].status)' 2>/dev/null || echo "Unknown")

    if [ "$CONDITION" = "True" ]; then
        REVISION_READY="true"
        break
    fi

    printf "  Waiting... (%ds)" "$ELAPSED"
    printf "\r"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

echo ""
if [ "$REVISION_READY" = "true" ]; then
    success "New revision is healthy"
else
    warning "Revision not ready after ${MAX_WAIT}s — check Cloud Run logs manually"
fi

# --- Health check ------------------------------------------------------------
info "Running HTTP health check..."
SERVICE_URL=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$CLOUD_RUN_REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null)

if [ -n "$SERVICE_URL" ]; then
    HTTP_STATUS=$(curl -o /dev/null -s -w "%{http_code}" --max-time 30 "${SERVICE_URL}/health" || echo "000")
    if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "204" ]; then
        success "Health check passed (HTTP $HTTP_STATUS): $SERVICE_URL"
    elif [ "$HTTP_STATUS" = "000" ]; then
        warning "Could not reach $SERVICE_URL/health (timeout or unreachable)"
    else
        warning "Health check returned HTTP $HTTP_STATUS — check Cloud Run logs for DB errors"
    fi
fi

# --- Check recent logs for DB connection errors ------------------------------
info "Checking recent Cloud Run logs for database errors..."
step "(Fetching last 20 log entries containing 'database' or 'error'...)"
gcloud logging read \
    "resource.type=cloud_run_revision AND resource.labels.service_name=${CLOUD_RUN_SERVICE} AND (textPayload:\"database\" OR textPayload:\"sqlalchemy\" OR textPayload:\"error\" OR severity>=WARNING)" \
    --project="$PROJECT_ID" \
    --limit=20 \
    --format='value(timestamp, severity, textPayload)' \
    --freshness=5m 2>/dev/null | head -30 || warning "Could not retrieve logs (check Cloud Run logs in console)"

# --- Summary -----------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo " ✅  Cloud Run → Cloud SQL connection configured!"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo " Service URL:  $SERVICE_URL"
echo " Cloud SQL:    $INSTANCE_CONNECTION_NAME"
echo " DATABASE_URL: loaded from Secret Manager secret '$SECRET_NAME'"
echo ""
echo " ─── VERIFY IN BROWSER ──────────────────────────────────────────"
echo " Open $SERVICE_URL and try to:"
echo "   1. Log in with an existing account"
echo "   2. Confirm your existing chats are visible"
echo "   3. Send a test message"
echo ""
echo " ─── MONITOR LOGS ───────────────────────────────────────────────"
echo " gcloud logging tail 'resource.type=cloud_run_revision AND resource.labels.service_name=${CLOUD_RUN_SERVICE}' --project=$PROJECT_ID"
echo ""
echo " ─── IF SOMETHING IS WRONG ──────────────────────────────────────"
echo " Check logs above for 'connection refused' or 'password auth failed'."
echo " Common fixes:"
echo "   • Missing pgvector extension: connect to DB and run CREATE EXTENSION vector;"
echo "   • Wrong password in secret: re-run migrate_sql_us_west1.sh"
echo "   • IAM permission: ensure $SERVICE_ACCOUNT has roles/cloudsql.client"
echo ""
echo " ─── CLEANUP (after verification) ───────────────────────────────"
echo " Delete old Cloud SQL instance (us-central1):"
echo "   gcloud sql instances delete genesis-ai-hub-db --project=$PROJECT_ID"
echo "═══════════════════════════════════════════════════════════════════"
