#!/bin/bash
# Quick Reference Commands for Google Cloud PostgreSQL Migration

echo "════════════════════════════════════════════════════════════"
echo "  Genesis AI Hub - Cloud Migration Quick Reference"
echo "════════════════════════════════════════════════════════════"
echo ""

cat << 'EOF'
📋 PREREQUISITES
─────────────────────────────────────────────────────────────────
□ Google Cloud account with billing
□ gcloud CLI installed and authenticated
□ PostgreSQL client (psql) installed
□ Current working directory is repository root

🚀 SETUP COMMANDS (One-time)
─────────────────────────────────────────────────────────────────
# 1. Google Cloud Setup (automated)
./setup_google_cloud.sh

# 2. Enable PgVector
gcloud sql connect <INSTANCE> --user=postgres --database=webui
CREATE EXTENSION IF NOT EXISTS vector;
\q

# 3. Start Cloud SQL Proxy (keep running)
./start_cloud_sql_proxy.sh

# 4. Migrate Data
./migrate_to_postgres.sh

# 5. Configure Application
cp front/.env.cloud.generated front/.env

# 6. Start Application
cd front/backend && ./start.sh

🔧 DAILY COMMANDS
─────────────────────────────────────────────────────────────────
# Start Cloud SQL Proxy (Terminal 1)
./start_cloud_sql_proxy.sh

# Start Application (Terminal 2)
cd front/backend && ./start.sh

# Check Database Connection
psql -h localhost -U postgres -d webui -c "SELECT version();"

# Check GCS Access
gcloud storage ls gs://YOUR-BUCKET-NAME/

🔍 VERIFICATION COMMANDS
─────────────────────────────────────────────────────────────────
# Count records in PostgreSQL
psql -h localhost -U postgres -d webui << SQL
SELECT 'users' as table_name, COUNT(*) FROM "user"
UNION ALL
SELECT 'chats', COUNT(*) FROM chat
UNION ALL
SELECT 'messages', COUNT(*) FROM message;
SQL

# Check Cloud SQL Instance Status
gcloud sql instances describe <INSTANCE>

# Check Storage Bucket
gcloud storage buckets describe gs://YOUR-BUCKET-NAME

# List Cloud SQL Backups
gcloud sql backups list --instance=<INSTANCE>

💰 COST MONITORING
─────────────────────────────────────────────────────────────────
# Current month costs
gcloud billing accounts list
gcloud billing projects describe <PROJECT-ID>

# Check in console (recommended)
https://console.cloud.google.com/billing

🛠️ TROUBLESHOOTING
─────────────────────────────────────────────────────────────────
# Cloud SQL Proxy not connecting?
ps aux | grep cloud_sql_proxy
lsof -i :5432
./start_cloud_sql_proxy.sh

# Database connection issues?
export PGPASSWORD=<password>
psql -h localhost -U postgres -d webui

# GCS permission denied?
gcloud storage buckets add-iam-policy-binding gs://BUCKET \
  --member=serviceAccount:EMAIL@PROJECT.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin

# Check application logs
tail -f front/backend/data/webui.log

🔄 BACKUP & RESTORE
─────────────────────────────────────────────────────────────────
# Manual PostgreSQL Backup
pg_dump -h localhost -U postgres webui > backup_$(date +%Y%m%d).sql

# Restore from Backup
psql -h localhost -U postgres -d webui < backup_20260128.sql

# List SQLite Backups (from migration)
ls -la front/backend/data/backups/

# Restore SQLite (rollback)
cp front/backend/data/backups/TIMESTAMP/webui.db.backup \
   front/backend/data/webui.db

# Cloud SQL Automated Backups
gcloud sql backups list --instance=<INSTANCE>
gcloud sql backups restore <BACKUP-ID> --backup-instance=<INSTANCE>

📊 MONITORING
─────────────────────────────────────────────────────────────────
# Cloud SQL CPU/Memory Usage
gcloud sql instances describe <INSTANCE> --format="table(state,cpuUsage,memoryUsage)"

# Database Size
psql -h localhost -U postgres -d webui -c \
  "SELECT pg_size_pretty(pg_database_size('webui'));"

# Connection Count
psql -h localhost -U postgres -d webui -c \
  "SELECT count(*) FROM pg_stat_activity;"

# Storage Bucket Size
gcloud storage du gs://YOUR-BUCKET-NAME/

🔐 SECURITY
─────────────────────────────────────────────────────────────────
# List Service Accounts
gcloud iam service-accounts list

# Rotate Service Account Key
gcloud iam service-accounts keys create new-key.json \
  --iam-account=EMAIL@PROJECT.iam.gserviceaccount.com

# Delete Old Key
gcloud iam service-accounts keys delete KEY-ID \
  --iam-account=EMAIL@PROJECT.iam.gserviceaccount.com

# Change Database Password
gcloud sql users set-password postgres \
  --instance=<INSTANCE> \
  --password=<NEW-PASSWORD>

# Enable Cloud SQL SSL
gcloud sql instances patch <INSTANCE> --require-ssl

📈 SCALING
─────────────────────────────────────────────────────────────────
# Upgrade Database Tier
gcloud sql instances patch <INSTANCE> --tier=db-n1-standard-1

# Increase Storage
gcloud sql instances patch <INSTANCE> --storage-size=20GB

# Enable High Availability
gcloud sql instances patch <INSTANCE> --availability-type=REGIONAL

# Add Read Replica
gcloud sql instances create replica-1 \
  --master-instance-name=<INSTANCE> \
  --region=<REGION>

🚢 DEPLOYMENT
─────────────────────────────────────────────────────────────────
# Deploy to Cloud Run
cd front
gcloud run deploy genesis-ai-hub \
  --source . \
  --region=us-central1 \
  --add-cloudsql-instances=PROJECT:REGION:INSTANCE \
  --set-env-vars=DATABASE_URL=postgresql://... \
  --allow-unauthenticated

# Deploy to Compute Engine
gcloud compute instances create genesis-vm \
  --zone=us-central1-a \
  --machine-type=e2-medium \
  --scopes=cloud-platform

🔗 USEFUL URLS
─────────────────────────────────────────────────────────────────
Google Cloud Console:
  https://console.cloud.google.com

Cloud SQL Instances:
  https://console.cloud.google.com/sql/instances

Cloud Storage Buckets:
  https://console.cloud.google.com/storage

Billing & Costs:
  https://console.cloud.google.com/billing

IAM & Admin:
  https://console.cloud.google.com/iam-admin

📚 DOCUMENTATION
─────────────────────────────────────────────────────────────────
Quick Start:           QUICKSTART_CLOUD.md
Full Guide:            CLOUD_MIGRATION_GUIDE.md
Architecture:          ARCHITECTURE_DIAGRAM.md
Summary:              CLOUD_INTEGRATION_SUMMARY.md

Cloud SQL Docs:        https://cloud.google.com/sql/docs
PgVector:             https://github.com/pgvector/pgvector
Open WebUI:           https://docs.openwebui.com

🎯 COMMON WORKFLOWS
─────────────────────────────────────────────────────────────────
DAILY STARTUP:
  1. ./start_cloud_sql_proxy.sh (Terminal 1)
  2. cd front/backend && ./start.sh (Terminal 2)
  3. Open http://localhost:8080

MANUAL BACKUP:
  1. pg_dump -h localhost -U postgres webui > backup.sql
  2. gcloud storage cp backup.sql gs://BUCKET/backups/

CHECK HEALTH:
  1. psql -h localhost -U postgres -d webui -c "SELECT 1;"
  2. gcloud sql instances describe <INSTANCE>
  3. Check Cloud Console billing

EMERGENCY ROLLBACK:
  1. Stop application
  2. Update .env to use SQLite
  3. Restore SQLite from backup
  4. Restart application

💡 PRO TIPS
─────────────────────────────────────────────────────────────────
• Keep Cloud SQL Proxy running in a tmux/screen session
• Set up cost alerts in Google Cloud Console
• Test backup restore procedure monthly
• Use staging environment for testing changes
• Monitor database connections (don't exceed pool size)
• Enable Cloud SQL Insights for query analysis
• Use connection pooling (PgBouncer) for high traffic
• Schedule backups before major changes
• Document any custom configurations
• Review IAM permissions quarterly

🆘 EMERGENCY CONTACTS
─────────────────────────────────────────────────────────────────
Google Cloud Support:  https://cloud.google.com/support
Stack Overflow:        Tag: google-cloud-sql, postgresql
Community Forums:      https://www.googlecloudcommunity.com

════════════════════════════════════════════════════════════════
           Type './setup_google_cloud.sh' to start!
════════════════════════════════════════════════════════════════
EOF
