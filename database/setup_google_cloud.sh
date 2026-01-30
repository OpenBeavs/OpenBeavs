#!/bin/bash

# =============================================================================
# Google Cloud Setup Script
# =============================================================================
# This script sets up Google Cloud resources for Genesis AI Hub
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==============================================================================${NC}"
echo -e "${BLUE}Genesis AI Hub - Google Cloud Setup${NC}"
echo -e "${BLUE}==============================================================================${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not found${NC}"
    echo "Please install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# =============================================================================
# Configuration
# =============================================================================

echo -e "${YELLOW}Please provide the following information:${NC}"
echo ""

read -p "Google Cloud Project ID: " PROJECT_ID
read -p "Region (e.g., us-central1): " REGION
read -p "Database instance name (default: genesis-ai-hub-db): " INSTANCE_NAME
INSTANCE_NAME=${INSTANCE_NAME:-genesis-ai-hub-db}
read -sp "PostgreSQL password: " DB_PASSWORD
echo ""
read -p "Storage bucket name (default: genesis-ai-hub-uploads): " BUCKET_NAME
BUCKET_NAME=${BUCKET_NAME:-genesis-ai-hub-uploads}
read -p "Service account name (default: genesis-ai-hub-sa): " SA_NAME
SA_NAME=${SA_NAME:-genesis-ai-hub-sa}

echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Project ID: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Database: $INSTANCE_NAME"
echo "  Bucket: $BUCKET_NAME"
echo "  Service Account: $SA_NAME"
echo ""

read -p "Proceed with setup? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Setup cancelled"
    exit 0
fi

# =============================================================================
# Set Project
# =============================================================================

echo ""
echo -e "${YELLOW}Setting up project...${NC}"
gcloud config set project $PROJECT_ID

# =============================================================================
# Enable Required APIs
# =============================================================================

echo ""
echo -e "${YELLOW}Enabling required APIs...${NC}"
gcloud services enable sqladmin.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable compute.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
echo -e "${GREEN}✓ APIs enabled${NC}"

# =============================================================================
# Create Cloud SQL Instance
# =============================================================================

echo ""
echo -e "${YELLOW}Creating Cloud SQL PostgreSQL instance...${NC}"
echo -e "${YELLOW}This will take 5-10 minutes...${NC}"

if gcloud sql instances describe $INSTANCE_NAME 2>/dev/null; then
    echo -e "${YELLOW}Instance $INSTANCE_NAME already exists${NC}"
else
    gcloud sql instances create $INSTANCE_NAME \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region=$REGION \
        --storage-type=SSD \
        --storage-size=10GB \
        --storage-auto-increase \
        --backup-start-time=03:00 \
        --maintenance-window-day=SUN \
        --maintenance-window-hour=04 \
        --availability-type=zonal \
        --no-assign-ip
    
    echo -e "${GREEN}✓ Cloud SQL instance created${NC}"
fi

# Set password
gcloud sql users set-password postgres \
    --instance=$INSTANCE_NAME \
    --password=$DB_PASSWORD

# Create database
gcloud sql databases create webui --instance=$INSTANCE_NAME || echo "Database already exists"

# Enable PgVector
CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME --format="value(connectionName)")
echo -e "${YELLOW}To enable PgVector extension, run:${NC}"
echo "  gcloud sql connect $INSTANCE_NAME --user=postgres --database=webui"
echo "  Then in psql: CREATE EXTENSION IF NOT EXISTS vector;"

# =============================================================================
# Create Storage Bucket
# =============================================================================

echo ""
echo -e "${YELLOW}Creating Cloud Storage bucket...${NC}"

if gcloud storage buckets describe gs://$BUCKET_NAME 2>/dev/null; then
    echo -e "${YELLOW}Bucket $BUCKET_NAME already exists${NC}"
else
    gcloud storage buckets create gs://$BUCKET_NAME \
        --location=$REGION \
        --uniform-bucket-level-access
    
    gcloud storage buckets update gs://$BUCKET_NAME --versioning
    echo -e "${GREEN}✓ Storage bucket created${NC}"
fi

# =============================================================================
# Create Service Account
# =============================================================================

echo ""
echo -e "${YELLOW}Creating service account...${NC}"

SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL 2>/dev/null; then
    echo -e "${YELLOW}Service account already exists${NC}"
else
    gcloud iam service-accounts create $SA_NAME \
        --display-name="Genesis AI Hub Service Account"
    echo -e "${GREEN}✓ Service account created${NC}"
fi

# Grant permissions
echo -e "${YELLOW}Granting permissions...${NC}"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/cloudsql.client" \
    --condition=None

gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.objectAdmin"

# Create key
KEY_FILE="$HOME/${SA_NAME}-key.json"
if [ -f "$KEY_FILE" ]; then
    echo -e "${YELLOW}Key file already exists at $KEY_FILE${NC}"
    read -p "Overwrite? (yes/no): " OVERWRITE
    if [ "$OVERWRITE" == "yes" ]; then
        gcloud iam service-accounts keys create "$KEY_FILE" \
            --iam-account=$SA_EMAIL
    fi
else
    gcloud iam service-accounts keys create "$KEY_FILE" \
        --iam-account=$SA_EMAIL
fi

echo -e "${GREEN}✓ Service account configured${NC}"

# =============================================================================
# Download Cloud SQL Proxy
# =============================================================================

echo ""
echo -e "${YELLOW}Downloading Cloud SQL Proxy...${NC}"

PROXY_FILE="$HOME/cloud_sql_proxy"
if [ -f "$PROXY_FILE" ]; then
    echo -e "${YELLOW}Cloud SQL Proxy already exists${NC}"
else
    # Detect architecture
    ARCH=$(uname -m)
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    
    if [ "$OS" == "darwin" ] && [ "$ARCH" == "arm64" ]; then
        PROXY_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.2/cloud-sql-proxy.darwin.arm64"
    elif [ "$OS" == "darwin" ]; then
        PROXY_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.2/cloud-sql-proxy.darwin.amd64"
    elif [ "$OS" == "linux" ]; then
        PROXY_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.2/cloud-sql-proxy.linux.amd64"
    else
        echo -e "${RED}Unsupported platform: $OS $ARCH${NC}"
        exit 1
    fi
    
    curl -o "$PROXY_FILE" "$PROXY_URL"
    chmod +x "$PROXY_FILE"
    echo -e "${GREEN}✓ Cloud SQL Proxy downloaded${NC}"
fi

# =============================================================================
# Generate Configuration
# =============================================================================

echo ""
echo -e "${YELLOW}Generating configuration files...${NC}"

ENV_FILE="$(dirname "$0")/front/.env.cloud.generated"
cat > "$ENV_FILE" << EOF
# =============================================================================
# Generated Google Cloud Configuration
# Generated: $(date)
# =============================================================================

# Database Configuration
DATABASE_URL=postgresql://postgres:${DB_PASSWORD}@localhost:5432/webui
DATABASE_POOL_SIZE=5
DATABASE_POOL_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600

# Vector Database
VECTOR_DB=pgvector
PGVECTOR_DB_URL=postgresql://postgres:${DB_PASSWORD}@localhost:5432/webui
PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH=1536

# Storage
STORAGE_PROVIDER=gcs
GCS_BUCKET_NAME=${BUCKET_NAME}
GOOGLE_APPLICATION_CREDENTIALS=${KEY_FILE}

# Application
WEBUI_NAME='OSU Genesis AI Hub'
ENV=prod
WEBUI_AUTH=True
ENABLE_SIGNUP=True
DEFAULT_USER_ROLE=user

# AI Services
OLLAMA_BASE_URL=http://localhost:11434

# Privacy
SCARF_NO_ANALYTICS=true
DO_NOT_TRACK=true
ANONYMIZED_TELEMETRY=false

# Performance
UVICORN_WORKERS=2

# =============================================================================
# Cloud SQL Connection Name: ${CONNECTION_NAME}
# =============================================================================
# To start Cloud SQL Proxy, run:
#   ${PROXY_FILE} --port 5432 ${CONNECTION_NAME}
# =============================================================================
EOF

echo -e "${GREEN}✓ Configuration saved to: $ENV_FILE${NC}"

# Create proxy start script
PROXY_SCRIPT="$(dirname "$0")/start_cloud_sql_proxy.sh"
cat > "$PROXY_SCRIPT" << EOF
#!/bin/bash
# Start Cloud SQL Proxy for local development
${PROXY_FILE} --port 5432 ${CONNECTION_NAME}
EOF
chmod +x "$PROXY_SCRIPT"

echo -e "${GREEN}✓ Proxy script created: $PROXY_SCRIPT${NC}"

# =============================================================================
# Summary
# =============================================================================

echo ""
echo -e "${GREEN}==============================================================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}==============================================================================${NC}"
echo ""
echo -e "${YELLOW}Resources Created:${NC}"
echo "  ✓ Cloud SQL Instance: $INSTANCE_NAME"
echo "  ✓ Database: webui"
echo "  ✓ Storage Bucket: gs://$BUCKET_NAME"
echo "  ✓ Service Account: $SA_EMAIL"
echo "  ✓ Service Account Key: $KEY_FILE"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. Enable PgVector extension:"
echo "   gcloud sql connect $INSTANCE_NAME --user=postgres --database=webui"
echo "   In psql: CREATE EXTENSION IF NOT EXISTS vector;"
echo ""
echo "2. Start Cloud SQL Proxy (in a separate terminal):"
echo "   $PROXY_SCRIPT"
echo ""
echo "3. Copy the generated environment file:"
echo "   cp $ENV_FILE $(dirname "$0")/front/.env"
echo ""
echo "4. Run the migration script:"
echo "   ./migrate_to_postgres.sh"
echo ""
echo "5. Start the application:"
echo "   cd front/backend && ./start.sh"
echo ""
echo -e "${YELLOW}Important Files:${NC}"
echo "  Environment: $ENV_FILE"
echo "  Service Key: $KEY_FILE"
echo "  Proxy Script: $PROXY_SCRIPT"
echo "  Connection: ${CONNECTION_NAME}"
echo ""
echo -e "${YELLOW}Security Notes:${NC}"
echo "  • Keep service account key secure"
echo "  • Never commit credentials to git"
echo "  • Rotate keys regularly"
echo "  • Enable Cloud SQL audit logging"
echo ""
echo -e "${GREEN}Setup complete!${NC}"
