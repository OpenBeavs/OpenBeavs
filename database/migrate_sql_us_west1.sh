#!/bin/bash
# =============================================================================
# migrate_sql_us_west1.sh
# Migrates the Cloud SQL database from us-central1 to us-west1 to match
# the Cloud Run service region, preserving all existing data.
#
# What this script does:
#   1. Gets the Cloud SQL service account and grants it GCS access
#   2. Exports the webui database from genesis-ai-hub-db (us-central1) to GCS
#   3. Creates a new PostgreSQL instance genesis-ai-hub-db-west1 (us-west1)
#   4. Enables the pgvector extension
#   5. Imports the data into the new instance
#   6. Stores the full DATABASE_URL in Google Secret Manager
#   7. Prints next steps
#
# Usage: ./database/migrate_sql_us_west1.sh
#
# Prerequisites:
#   - gcloud CLI authenticated (gcloud auth login)
#   - gcloud config set project osu-genesis-hub
#   - The old Cloud SQL instance must be RUNNABLE
# =============================================================================

set -euo pipefail

# --- Config ------------------------------------------------------------------
PROJECT_ID="osu-genesis-hub"
DB_NAME="webui"
DB_USER="postgres"

OLD_INSTANCE="genesis-ai-hub-db"
OLD_REGION="us-central1"

NEW_INSTANCE="genesis-ai-hub-db-west1"
NEW_REGION="us-west1"
NEW_TIER="db-f1-micro"  # Same as existing instance; upgrade to db-g1-small for more stability

GCS_BUCKET="genesis-ai-hub-uploads"
# If a previous run already created an export, reuse the latest one instead of
# generating a new timestamp (avoids running a redundant export on re-runs).
EXISTING_EXPORT=$(gcloud storage ls "gs://${GCS_BUCKET}/migration/webui_export_*.sql" 2>/dev/null | sort | tail -1 || echo "")
if [ -n "$EXISTING_EXPORT" ]; then
    GCS_EXPORT_PATH="$EXISTING_EXPORT"
else
    GCS_EXPORT_PATH="gs://${GCS_BUCKET}/migration/webui_export_$(date +%Y%m%d_%H%M%S).sql"
fi

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
    echo "ERROR: Not authenticated. Run: gcloud auth login && gcloud auth application-default login"
    exit 1
fi
success "Authenticated as: $ACTIVE_ACCOUNT"

gcloud config set project "$PROJECT_ID" --quiet
success "Project set to: $PROJECT_ID"

# Verify the old instance exists and is running
OLD_STATUS=$(gcloud sql instances describe "$OLD_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(state)' 2>/dev/null || echo "NOT_FOUND")

if [ "$OLD_STATUS" = "NOT_FOUND" ]; then
    echo "ERROR: Cloud SQL instance '$OLD_INSTANCE' not found. Cannot migrate."
    exit 1
elif [ "$OLD_STATUS" != "RUNNABLE" ]; then
    echo "ERROR: Cloud SQL instance '$OLD_INSTANCE' is in state '$OLD_STATUS', expected RUNNABLE."
    exit 1
fi
success "Source instance '$OLD_INSTANCE' is RUNNABLE"

# Check if new instance already exists
NEW_STATUS=$(gcloud sql instances describe "$NEW_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(state)' 2>/dev/null || echo "NOT_FOUND")

if [ "$NEW_STATUS" != "NOT_FOUND" ] && [ "$NEW_STATUS" != "RUNNABLE" ]; then
    echo "ERROR: Instance '$NEW_INSTANCE' exists but is in unexpected state: $NEW_STATUS"
    exit 1
fi

if [ "$NEW_STATUS" = "RUNNABLE" ]; then
    warning "Instance '$NEW_INSTANCE' already exists — skipping creation, will resume from import step"
    SKIP_CREATE=true
else
    success "Target instance '$NEW_INSTANCE' does not exist yet (good)"
    SKIP_CREATE=false
fi

# --- Securely read DB password -----------------------------------------------
info "Database password required"
echo "  You will be prompted for the PostgreSQL 'postgres' user password."
echo "  This password will be stored in Google Secret Manager (not written to disk)."
echo ""

# Try to read from Secret Manager first (if already stored from a previous partial run)
EXISTING_URL=$(gcloud secrets versions access latest \
    --secret="$SECRET_NAME" \
    --project="$PROJECT_ID" 2>/dev/null || echo "")

if [ -n "$EXISTING_URL" ] && echo "$EXISTING_URL" | grep -q "west1"; then
    # Already has a west1 URL — extract the password from it
    DB_PASSWORD=$(echo "$EXISTING_URL" | python3 -c "
import sys, urllib.parse
url = sys.stdin.read().strip()
parsed = urllib.parse.urlparse(url)
print(parsed.password or '')
")
    if [ -n "$DB_PASSWORD" ]; then
        success "Password loaded from existing Secret Manager entry"
    else
        read -r -s -p "  Enter postgres password: " DB_PASSWORD
        echo ""
    fi
else
    read -r -s -p "  Enter postgres password: " DB_PASSWORD
    echo ""
fi

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: Password cannot be empty."
    exit 1
fi

# --- Step 1: Grant Cloud SQL service account access to GCS -------------------
info "Step 1 of 5: Granting Cloud SQL service account access to GCS bucket..."

# Read the service account email directly from the instance (most reliable approach).
# This is the actual SA that Cloud SQL uses for import/export operations.
CLOUDSQL_SA=$(gcloud sql instances describe "$OLD_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(serviceAccountEmailAddress)' 2>/dev/null || echo "")

if [ -z "$CLOUDSQL_SA" ]; then
    echo "ERROR: Could not read service account from Cloud SQL instance '$OLD_INSTANCE'."
    exit 1
fi
step "Cloud SQL service account: $CLOUDSQL_SA"

# Grant at the project level (requires resourcemanager.projectIamAdmin, not storage.admin).
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${CLOUDSQL_SA}" \
    --role="roles/storage.objectAdmin" \
    --condition=None \
    --quiet

success "GCS access granted to Cloud SQL service account (project-level)"

# # IAM changes take 30-60s to propagate across GCP before they're enforced.
# # Without this wait the export immediately hits a 412 permission error.
# step "Waiting 60 seconds for IAM policy to propagate..."
# sleep 60
# success "IAM propagation wait complete"

# --- Step 2: Export the database to GCS --------------------------------------
info "Step 2 of 5: Exporting database from '$OLD_INSTANCE' ($OLD_REGION) to GCS..."
step "Export path: $GCS_EXPORT_PATH"

if [ -n "$EXISTING_EXPORT" ]; then
    success "Reusing existing export: $GCS_EXPORT_PATH"
else
    step "This may take a few minutes depending on database size..."
    gcloud sql export sql "$OLD_INSTANCE" "$GCS_EXPORT_PATH" \
        --database="$DB_NAME" \
        --project="$PROJECT_ID" \
        --quiet
    success "Database exported successfully"
fi

# --- Step 3: Create new Cloud SQL instance in us-west1 -----------------------
if [ "$SKIP_CREATE" = true ]; then
    info "Step 3 of 5: Skipping instance creation (already exists)"
else
    info "Step 3 of 5: Creating Cloud SQL instance '$NEW_INSTANCE' in $NEW_REGION..."
    step "Tier: $NEW_TIER  |  This takes 5-10 minutes, please wait..."

    gcloud sql instances create "$NEW_INSTANCE" \
        --database-version=POSTGRES_15 \
        --tier="$NEW_TIER" \
        --region="$NEW_REGION" \
        --storage-type=SSD \
        --storage-size=10GB \
        --storage-auto-increase \
        --backup-start-time=03:00 \
        --availability-type=zonal \
        --project="$PROJECT_ID" \
        --quiet

    success "Instance '$NEW_INSTANCE' created in $NEW_REGION"

    # Set postgres user password
    step "Setting postgres user password..."
    gcloud sql users set-password "$DB_USER" \
        --instance="$NEW_INSTANCE" \
        --password="$DB_PASSWORD" \
        --project="$PROJECT_ID" \
        --quiet

    success "Password set on new instance"

    # Create the webui database
    step "Creating '$DB_NAME' database..."
    gcloud sql databases create "$DB_NAME" \
        --instance="$NEW_INSTANCE" \
        --project="$PROJECT_ID" \
        --quiet

    success "Database '$DB_NAME' created"
fi

# Grant the NEW instance's service account GCS access for the import.
# Each Cloud SQL instance has its own unique SA — must grant separately from the old one.
NEW_CLOUDSQL_SA=$(gcloud sql instances describe "$NEW_INSTANCE" \
    --project="$PROJECT_ID" \
    --format='value(serviceAccountEmailAddress)')
step "New instance service account: $NEW_CLOUDSQL_SA"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${NEW_CLOUDSQL_SA}" \
    --role="roles/storage.objectViewer" \
    --condition=None \
    --quiet

success "GCS read access granted to new instance's service account"
step "Waiting 60 seconds for IAM policy to propagate..."
sleep 60
success "IAM propagation wait complete"

# --- Step 4: Import data into new instance -----------------------------------
info "Step 4 of 5: Importing data into '$NEW_INSTANCE'..."
step "Source: $GCS_EXPORT_PATH"
step "This may take a few minutes..."

gcloud sql import sql "$NEW_INSTANCE" "$GCS_EXPORT_PATH" \
    --database="$DB_NAME" \
    --project="$PROJECT_ID" \
    --quiet

success "Data imported successfully"

# Enable pgvector extension (requires connecting via Cloud SQL)
step "Enabling pgvector extension (via gcloud sql connect)..."
echo "  Note: You may be prompted to whitelist your IP address. Accept the prompt."
echo "  Running: CREATE EXTENSION IF NOT EXISTS vector;"
echo "CREATE EXTENSION IF NOT EXISTS vector;" | \
    gcloud sql connect "$NEW_INSTANCE" \
        --user="$DB_USER" \
        --database="$DB_NAME" \
        --project="$PROJECT_ID" \
        --quiet 2>/dev/null || warning "Could not auto-enable pgvector. Enable it manually if needed."

# --- Step 5: Store DATABASE_URL in Secret Manager ----------------------------
info "Step 5 of 5: Storing DATABASE_URL in Secret Manager (secret: '$SECRET_NAME')..."

# Cloud Run connects via Unix socket: /cloudsql/PROJECT:REGION:INSTANCE
INSTANCE_CONNECTION_NAME="${PROJECT_ID}:${NEW_REGION}:${NEW_INSTANCE}"
# URL-encode the password for the connection string
ENCODED_PASSWORD=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$DB_PASSWORD")
DATABASE_URL="postgresql://${DB_USER}:${ENCODED_PASSWORD}@/${DB_NAME}?host=/cloudsql/${INSTANCE_CONNECTION_NAME}"

# Check if secret already exists
SECRET_EXISTS=$(gcloud secrets describe "$SECRET_NAME" \
    --project="$PROJECT_ID" \
    --format='value(name)' 2>/dev/null || echo "NOT_FOUND")

if [ "$SECRET_EXISTS" = "NOT_FOUND" ]; then
    step "Creating new secret '$SECRET_NAME'..."
    printf '%s' "$DATABASE_URL" | gcloud secrets create "$SECRET_NAME" \
        --project="$PROJECT_ID" \
        --data-file=- \
        --quiet
    success "Secret '$SECRET_NAME' created"
else
    step "Adding new version to existing secret '$SECRET_NAME'..."
    printf '%s' "$DATABASE_URL" | gcloud secrets versions add "$SECRET_NAME" \
        --project="$PROJECT_ID" \
        --data-file=- \
        --quiet
    success "Secret '$SECRET_NAME' updated with new version"
fi

# Disable the password variable immediately — no longer needed in memory
unset DB_PASSWORD
unset ENCODED_PASSWORD
unset DATABASE_URL

# --- Summary -----------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo " ✅  Migration complete!"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo " New Cloud SQL instance:"
echo "   Name   : $NEW_INSTANCE"
echo "   Region : $NEW_REGION"
echo "   Connection name: ${PROJECT_ID}:${NEW_REGION}:${NEW_INSTANCE}"
echo ""
echo " Secret Manager:"
echo "   '$SECRET_NAME' updated with Cloud Run Unix socket URL"
echo ""
echo " Temporary export file (can delete after verification):"
echo "   $GCS_EXPORT_PATH"
echo ""
echo " ─── NEXT STEPS ─────────────────────────────────────────────────"
echo " 1. Connect Cloud Run to the new Cloud SQL instance:"
echo "      ./database/connect_cloud_run_to_sql.sh"
echo ""
echo " 2. After verifying everything works, delete the old instance:"
echo "      gcloud sql instances delete $OLD_INSTANCE --project=$PROJECT_ID"
echo ""
echo " 3. Delete the temporary export file:"
echo "      gcloud storage rm $GCS_EXPORT_PATH"
echo "═══════════════════════════════════════════════════════════════════"
