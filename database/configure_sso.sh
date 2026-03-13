#!/bin/bash
# =============================================================================
# configure_sso.sh
# Stores Microsoft SSO credentials in Secret Manager and mounts them on
# the Cloud Run service as environment variables.
#
# Usage: ./database/configure_sso.sh
# =============================================================================

set -euo pipefail

# --- Config ------------------------------------------------------------------
PROJECT_ID="osu-genesis-hub"
CLOUD_RUN_SERVICE="openbeavs-deploy-test"
CLOUD_RUN_REGION="us-west1"
SERVICE_ACCOUNT="genesis-ai-hub-sa@osu-genesis-hub.iam.gserviceaccount.com"

# --- Functions ---------------------------------------------------------------
info()    { echo ""; echo "► $1"; }
success() { echo "  ✅ $1"; }
step()    { echo "  → $1"; }

upsert_secret() {
    local secret_name="$1"
    local secret_value="$2"
    local exists
    exists=$(gcloud secrets describe "$secret_name" --project="$PROJECT_ID" --format='value(name)' 2>/dev/null || echo "NOT_FOUND")
    if [ "$exists" = "NOT_FOUND" ]; then
        step "Creating secret: $secret_name"
        printf '%s' "$secret_value" | gcloud secrets create "$secret_name" \
            --project="$PROJECT_ID" --data-file=- --quiet
    else
        step "Updating secret: $secret_name"
        printf '%s' "$secret_value" | gcloud secrets versions add "$secret_name" \
            --project="$PROJECT_ID" --data-file=- --quiet
    fi
    # Ensure genesis-ai-hub-sa can read it
    gcloud secrets add-iam-policy-binding "$secret_name" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet 2>/dev/null || true
    success "Secret ready: $secret_name"
}

# --- Auth check --------------------------------------------------------------
info "Checking prerequisites..."
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)
if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "ERROR: Not authenticated. Run: gcloud auth login"
    exit 1
fi
success "Authenticated as: $ACTIVE_ACCOUNT"
gcloud config set project "$PROJECT_ID" --quiet
success "Project: $PROJECT_ID"

# --- Step 1: Read credentials ------------------------------------------------
info "Step 1 of 3: Enter Microsoft SSO credentials"
echo "  These will be stored in Secret Manager and never written to disk."
echo "  ⚠️  If you previously shared these credentials in plaintext, rotate them"
echo "      in Azure AD first: Portal → App Registrations → Certificates & secrets"
echo ""

read -r -p "  Microsoft Client ID (App ID): " MS_CLIENT_ID
read -r -s -p "  Microsoft Client Secret:     " MS_CLIENT_SECRET
echo ""
read -r -p "  Microsoft Tenant ID:          " MS_TENANT_ID

if [ -z "$MS_CLIENT_ID" ] || [ -z "$MS_CLIENT_SECRET" ] || [ -z "$MS_TENANT_ID" ]; then
    echo "ERROR: All three values are required."
    exit 1
fi

# --- Step 2: Store in Secret Manager -----------------------------------------
info "Step 2 of 3: Storing credentials in Secret Manager..."

upsert_secret "microsoft-client-id"     "$MS_CLIENT_ID"
upsert_secret "microsoft-client-secret" "$MS_CLIENT_SECRET"
upsert_secret "microsoft-tenant-id"     "$MS_TENANT_ID"

unset MS_CLIENT_SECRET  # Clear from memory immediately

# --- Step 3: Update Cloud Run ------------------------------------------------
info "Step 3 of 3: Mounting secrets and setting env vars on Cloud Run..."

# Non-sensitive OAuth config goes as plain env vars.
# Sensitive values (client ID, secret, tenant) are mounted from Secret Manager.
step "Updating Cloud Run service '$CLOUD_RUN_SERVICE'..."

gcloud run services update "$CLOUD_RUN_SERVICE" \
    --region="$CLOUD_RUN_REGION" \
    --project="$PROJECT_ID" \
    --update-secrets="MICROSOFT_CLIENT_ID=microsoft-client-id:latest,MICROSOFT_CLIENT_SECRET=microsoft-client-secret:latest,MICROSOFT_CLIENT_TENANT_ID=microsoft-tenant-id:latest" \
    --update-env-vars="ENABLE_OAUTH_SIGNUP=true,OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true,MICROSOFT_OAUTH_SCOPE=openid email profile" \
    --quiet

success "Cloud Run updated with SSO configuration"

# --- Done --------------------------------------------------------------------
SERVICE_URL=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
    --region="$CLOUD_RUN_REGION" --project="$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null)

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo " ✅  Microsoft SSO configured!"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo " Service URL: $SERVICE_URL"
echo ""
echo " Secrets stored in Secret Manager:"
echo "   microsoft-client-id"
echo "   microsoft-client-secret"
echo "   microsoft-tenant-id"
echo ""
echo " Cloud Run env vars set:"
echo "   ENABLE_OAUTH_SIGNUP=true"
echo "   OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true"
echo "   MICROSOFT_OAUTH_SCOPE=openid email profile"
echo ""
echo " ─── VERIFY ─────────────────────────────────────────────────────"
echo " Open $SERVICE_URL — you should see a 'Sign in with Microsoft' button."
echo ""
echo " ─── AZURE AD REDIRECT URI ──────────────────────────────────────"
echo " Ensure this URI is registered in your Azure App Registration:"
echo "   ${SERVICE_URL}/oauth/microsoft/callback"
echo "═══════════════════════════════════════════════════════════════════"
