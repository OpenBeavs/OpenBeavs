# Google Cloud Migration Guide
## PostgreSQL + Google Cloud Storage Integration

This guide walks you through migrating from local SQLite storage to Google Cloud SQL (PostgreSQL) and Google Cloud Storage.

---

## 📋 Prerequisites

- **Google Cloud Account** with billing enabled
- **gcloud CLI** installed and configured
- **PostgreSQL client** (`psql`) installed locally
- **Existing data** in SQLite to migrate

---

## 🏗️ Architecture Overview

### Before (Current):
```
┌─────────────────────────────┐
│   Open WebUI Application   │
├─────────────────────────────┤
│ SQLite (webui.db)          │
│ ChromaDB (chroma.sqlite3)  │
│ Local uploads/             │
│ Local cache/               │
└─────────────────────────────┘
```

### After (Cloud):
```
┌─────────────────────────────────────┐
│     Open WebUI Application          │
├─────────────────────────────────────┤
│ ↓ Google Cloud SQL (PostgreSQL)     │
│ ↓ PgVector (embeddings in Postgres) │
│ ↓ Google Cloud Storage (files)      │
│ ↓ Local cache/ (temporary only)     │
└─────────────────────────────────────┘
```

---

## 📦 Part 1: Google Cloud SQL Setup

### Step 1.1: Create PostgreSQL Instance

```bash
# Set your project variables
export PROJECT_ID="your-project-id"
export REGION="us-central1"  # Choose closest region
export INSTANCE_NAME="genesis-ai-hub-db"
export DB_PASSWORD="your-secure-password-here"

# Set project
gcloud config set project $PROJECT_ID

# Create Cloud SQL PostgreSQL instance
gcloud sql instances create $INSTANCE_NAME \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=10GB \
  --storage-auto-increase \
  --backup-start-time=03:00 \
  --enable-bin-log \
  --availability-type=zonal

# Set root password
gcloud sql users set-password postgres \
  --instance=$INSTANCE_NAME \
  --password=$DB_PASSWORD
```

**For Production:** Use `db-n1-standard-2` or higher tier instead of `db-f1-micro`

### Step 1.2: Enable PgVector Extension

```bash
# Create database
gcloud sql databases create webui --instance=$INSTANCE_NAME

# Enable PgVector (requires connecting to the instance)
gcloud sql connect $INSTANCE_NAME --user=postgres --database=webui

# In psql prompt:
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

### Step 1.3: Configure Networking

**Option A: Cloud SQL Proxy (Recommended for Development)**
```bash
# Download Cloud SQL Proxy
curl -o cloud_sql_proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.2/cloud-sql-proxy.darwin.arm64
chmod +x cloud_sql_proxy

# Get connection name
gcloud sql instances describe $INSTANCE_NAME --format="value(connectionName)"

# Run proxy (in separate terminal)
./cloud_sql_proxy --port 5432 $PROJECT_ID:$REGION:$INSTANCE_NAME
```

**Option B: Public IP with Authorized Networks**
```bash
# Add your IP address
gcloud sql instances patch $INSTANCE_NAME \
  --authorized-networks="YOUR_IP_ADDRESS/32"
```

**Option C: Private IP (Production)**
```bash
# Enable Private IP (requires VPC configuration)
gcloud sql instances patch $INSTANCE_NAME \
  --network=projects/$PROJECT_ID/global/networks/default
```

---

## 📦 Part 2: Google Cloud Storage Setup

### Step 2.1: Create Storage Bucket

```bash
export BUCKET_NAME="genesis-ai-hub-uploads"
export BUCKET_REGION="us-central1"

# Create bucket
gcloud storage buckets create gs://$BUCKET_NAME \
  --location=$BUCKET_REGION \
  --uniform-bucket-level-access

# Enable versioning (recommended)
gcloud storage buckets update gs://$BUCKET_NAME --versioning
```

### Step 2.2: Create Service Account

```bash
export SERVICE_ACCOUNT_NAME="genesis-ai-hub-sa"

# Create service account
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
  --display-name="Genesis AI Hub Service Account"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
  --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Create and download key
gcloud iam service-accounts keys create ~/genesis-ai-hub-key.json \
  --iam-account=$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com
```

---

## 🔧 Part 3: Update Environment Configuration

### Step 3.1: Update `.env` file

Create or update `/front/.env`:

```bash
# ============================================
# Database Configuration - Google Cloud SQL
# ============================================

# PostgreSQL Connection (via Cloud SQL Proxy)
DATABASE_URL=postgresql://postgres:your-secure-password-here@localhost:5432/webui

# For direct connection (public IP):
# DATABASE_URL=postgresql://postgres:password@PUBLIC_IP:5432/webui

# For Unix socket (when running on GCP):
# DATABASE_URL=postgresql://postgres:password@/webui?host=/cloudsql/PROJECT:REGION:INSTANCE

# Connection Pool Settings (important for Cloud SQL)
DATABASE_POOL_SIZE=5
DATABASE_POOL_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600

# ============================================
# Vector Database - PgVector
# ============================================

# Use PgVector instead of ChromaDB
VECTOR_DB=pgvector
PGVECTOR_DB_URL=postgresql://postgres:your-secure-password-here@localhost:5432/webui
PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH=1536

# ============================================
# Google Cloud Storage Configuration
# ============================================

STORAGE_PROVIDER=gcs
GCS_BUCKET_NAME=genesis-ai-hub-uploads

# Service account credentials (JSON content as string)
GOOGLE_APPLICATION_CREDENTIALS_JSON='paste-json-content-here'

# Or use file path (alternative)
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/genesis-ai-hub-key.json

# ============================================
# Data Directory (local cache only)
# ============================================

DATA_DIR=/Users/minsoup/Desktop/GENESIS-AI-Hub-App/front/backend/data

# ============================================
# Application Settings
# ============================================

WEBUI_NAME='OSU Genesis AI Hub'
ENABLE_SIGNUP=True
DEFAULT_USER_ROLE=user

# Security
WEBUI_AUTH=True

# ============================================
# Ollama & AI Services
# ============================================

OLLAMA_BASE_URL=http://localhost:11434

# Analytics
SCARF_NO_ANALYTICS=true
DO_NOT_TRACK=true
ANONYMIZED_TELEMETRY=false
```

### Step 3.2: Get Service Account JSON

```bash
# Display the JSON (copy this)
cat ~/genesis-ai-hub-key.json

# Format for environment variable (remove newlines)
cat ~/genesis-ai-hub-key.json | jq -c '.'
```

---

## 📊 Part 4: Data Migration

### Step 4.1: Export SQLite Data

```bash
cd /Users/minsoup/Desktop/GENESIS-AI-Hub-App/front/backend/data

# Export SQLite to SQL dump
sqlite3 webui.db .dump > webui_export.sql
```

### Step 4.2: Convert SQLite to PostgreSQL Format

SQLite and PostgreSQL have syntax differences. Create a conversion script:

```bash
# Clean up SQLite-specific syntax
sed -i '' 's/AUTOINCREMENT/SERIAL/g' webui_export.sql
sed -i '' 's/INTEGER PRIMARY KEY/SERIAL PRIMARY KEY/g' webui_export.sql
sed -i '' '/BEGIN TRANSACTION;/d' webui_export.sql
sed -i '' '/COMMIT;/d' webui_export.sql
sed -i '' '/sqlite_sequence/d' webui_export.sql
```

### Step 4.3: Import to PostgreSQL

**Option 1: Using Cloud SQL Proxy**
```bash
# Start proxy first (in another terminal)
./cloud_sql_proxy --port 5432 $PROJECT_ID:$REGION:$INSTANCE_NAME

# Import data
PGPASSWORD=$DB_PASSWORD psql -h localhost -U postgres -d webui < webui_export.sql
```

**Option 2: Using gcloud**
```bash
# Upload dump to Cloud Storage
gcloud storage cp webui_export.sql gs://$BUCKET_NAME/migration/

# Import via Cloud SQL
gcloud sql import sql $INSTANCE_NAME gs://$BUCKET_NAME/migration/webui_export.sql \
  --database=webui
```

### Step 4.4: Migrate Vector Embeddings

Since you're switching from ChromaDB to PgVector, you'll need to:

1. **Extract embeddings from ChromaDB**
2. **Re-import into PgVector** (or let the application recreate them)

The application will handle PgVector table creation via migrations automatically.

### Step 4.5: Upload Files to Cloud Storage

```bash
# Set credentials
export GOOGLE_APPLICATION_CREDENTIALS=~/genesis-ai-hub-key.json

# Upload existing files (if any)
gcloud storage cp -r uploads/* gs://$BUCKET_NAME/uploads/

# Cache can stay local (temporary)
```

---

## 🧪 Part 5: Testing

### Step 5.1: Test Database Connection

```bash
# Start Cloud SQL Proxy
./cloud_sql_proxy --port 5432 $PROJECT_ID:$REGION:$INSTANCE_NAME

# Test connection
PGPASSWORD=$DB_PASSWORD psql -h localhost -U postgres -d webui -c "SELECT version();"
```

### Step 5.2: Test Application

```bash
cd /Users/minsoup/Desktop/GENESIS-AI-Hub-App/front/backend

# Start application
./start.sh
```

Check logs for:
- ✅ Successful PostgreSQL connection
- ✅ PgVector extension loaded
- ✅ GCS bucket accessible
- ✅ Migrations completed

---

## 🚀 Part 6: Production Deployment

### Option 1: Google Cloud Run (Recommended)

```bash
# Build container
cd /Users/minsoup/Desktop/GENESIS-AI-Hub-App/front
gcloud builds submit --tag gcr.io/$PROJECT_ID/genesis-ai-hub

# Deploy to Cloud Run
gcloud run deploy genesis-ai-hub \
  --image gcr.io/$PROJECT_ID/genesis-ai-hub \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --add-cloudsql-instances=$PROJECT_ID:$REGION:$INSTANCE_NAME \
  --set-env-vars="DATABASE_URL=postgresql://postgres:$DB_PASSWORD@/webui?host=/cloudsql/$PROJECT_ID:$REGION:$INSTANCE_NAME" \
  --set-env-vars="VECTOR_DB=pgvector" \
  --set-env-vars="STORAGE_PROVIDER=gcs" \
  --set-env-vars="GCS_BUCKET_NAME=$BUCKET_NAME" \
  --service-account=$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300
```

### Option 2: Google Compute Engine

```bash
# Create VM instance
gcloud compute instances create genesis-ai-hub-vm \
  --zone=$REGION-a \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --scopes=cloud-platform \
  --service-account=$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com

# SSH and setup application
gcloud compute ssh genesis-ai-hub-vm --zone=$REGION-a
```

### Option 3: Google Kubernetes Engine (GKE)

For high availability and auto-scaling needs.

---

## 💰 Cost Estimation

### Google Cloud SQL (PostgreSQL)
- **db-f1-micro** (Development): ~$7-10/month
- **db-n1-standard-1** (Small Production): ~$45-60/month
- **db-n1-standard-2** (Medium Production): ~$90-120/month
- **Storage**: $0.17/GB/month
- **Backups**: $0.08/GB/month

### Google Cloud Storage
- **Standard Storage**: $0.02/GB/month
- **Operations**: $0.05 per 10,000 operations
- **Typical usage (10GB)**: ~$0.20-1/month

### Cloud Run (if used)
- **Free tier**: 2M requests/month
- **Compute**: $0.00002400/vCPU-second
- **Memory**: $0.00000250/GiB-second
- **Typical small app**: ~$5-20/month

### Total Estimated Monthly Cost
- **Development**: $10-15/month
- **Small Production**: $50-80/month
- **Medium Production**: $100-150/month

---

## 🔒 Security Best Practices

1. **Never commit credentials** to git
   ```bash
   echo ".env" >> .gitignore
   echo "*.json" >> .gitignore
   ```

2. **Use Secret Manager** (production)
   ```bash
   gcloud secrets create db-password --data-file=-
   ```

3. **Enable SSL** for database connections
   ```python
   DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
   ```

4. **Rotate credentials** regularly
5. **Enable Cloud SQL audit logging**
6. **Use Private IP** in production
7. **Set up VPC Service Controls**

---

## 🔄 Rollback Plan

If migration fails, revert to SQLite:

1. Stop application
2. Update `.env`:
   ```bash
   DATABASE_URL=sqlite:///front/backend/data/webui.db
   VECTOR_DB=chroma
   STORAGE_PROVIDER=local
   ```
3. Restart application

Keep SQLite backup for at least 30 days after migration.

---

## 📚 Additional Resources

- [Cloud SQL Documentation](https://cloud.google.com/sql/docs)
- [PgVector Extension](https://github.com/pgvector/pgvector)
- [Google Cloud Storage Client](https://cloud.google.com/storage/docs/reference/libraries)
- [Open WebUI Documentation](https://docs.openwebui.com)

---

## ✅ Migration Checklist

- [ ] Google Cloud project created and billing enabled
- [ ] Cloud SQL PostgreSQL instance created
- [ ] PgVector extension installed
- [ ] GCS bucket created
- [ ] Service account created with proper permissions
- [ ] Service account key downloaded
- [ ] `.env` file updated with cloud credentials
- [ ] Cloud SQL Proxy installed and running
- [ ] SQLite data exported
- [ ] PostgreSQL database import completed
- [ ] Vector embeddings migrated/recreated
- [ ] Files uploaded to GCS
- [ ] Application tested locally with cloud resources
- [ ] Production deployment completed
- [ ] Monitoring and alerts configured
- [ ] Backup strategy verified
- [ ] Documentation updated
