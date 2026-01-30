# Quick Start: Google Cloud Migration

This is a simplified guide to get you started quickly. For detailed instructions, see [CLOUD_MIGRATION_GUIDE.md](./CLOUD_MIGRATION_GUIDE.md).

## Prerequisites

- Google Cloud account with billing enabled
- `gcloud` CLI installed
- PostgreSQL client installed

## One-Line Setup

```bash
./setup_google_cloud.sh
```

This automated script will:
- Create a Cloud SQL PostgreSQL instance
- Set up a Cloud Storage bucket  
- Configure a service account with proper permissions
- Download Cloud SQL Proxy
- Generate environment configuration

## Step-by-Step (15 minutes)

### 1. Run Google Cloud Setup (5 min)

```bash
./setup_google_cloud.sh
```

Follow the prompts to configure your project.

### 2. Enable PgVector Extension (1 min)

```bash
gcloud sql connect YOUR-INSTANCE-NAME --user=postgres --database=webui
```

In psql prompt:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

### 3. Start Cloud SQL Proxy (Terminal 1)

```bash
./start_cloud_sql_proxy.sh
```

Keep this running.

### 4. Copy Environment Configuration (1 min)

```bash
cp front/.env.cloud.generated front/.env
```

Review and adjust as needed.

### 5. Migrate Data (5 min)

```bash
./migrate_to_postgres.sh
```

This will:
- Backup your SQLite database
- Convert and import data to PostgreSQL
- Verify the migration

### 6. Start Application (Terminal 2)

```bash
cd front/backend
./start.sh
```

### 7. Verify Everything Works (3 min)

- Open http://localhost:8080
- Login with your existing credentials
- Check that chats, files, and models are accessible
- Upload a test file to verify GCS integration

## What Changes?

### Storage Locations

| Data Type | Before | After |
|-----------|--------|-------|
| User data, chats, messages | SQLite (`webui.db`) | PostgreSQL (Cloud SQL) |
| Vector embeddings | ChromaDB (`chroma.sqlite3`) | PgVector (in PostgreSQL) |
| Uploaded files | Local filesystem | Google Cloud Storage |
| Cache (temp files) | Local filesystem | Local filesystem |

### Environment Variables

Key changes in `.env`:

```bash
# Before
DATABASE_URL=sqlite:///front/backend/data/webui.db
VECTOR_DB=chroma
STORAGE_PROVIDER=local

# After
DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/webui
VECTOR_DB=pgvector
STORAGE_PROVIDER=gcs
GCS_BUCKET_NAME=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

## Cost Estimate

Monthly costs for small deployment:
- Cloud SQL (db-f1-micro): ~$7-10
- Cloud Storage (10GB): ~$0.20
- **Total: ~$10-15/month**

For production, upgrade to db-n1-standard-1 (~$50/month).

## Rollback

If anything goes wrong:

```bash
# 1. Stop the application
# 2. Restore .env
cp front/.env.backup front/.env

# 3. Restore SQLite from backup
cp front/backend/data/backups/TIMESTAMP/webui.db.backup front/backend/data/webui.db

# 4. Restart
cd front/backend && ./start.sh
```

## Common Issues

### "Cannot connect to PostgreSQL"

- **Solution**: Make sure Cloud SQL Proxy is running
  ```bash
  ./start_cloud_sql_proxy.sh
  ```

### "Permission denied" on GCS

- **Solution**: Check service account has Storage Object Admin role
  ```bash
  gcloud storage buckets add-iam-policy-binding gs://BUCKET \
    --member=serviceAccount:EMAIL \
    --role=roles/storage.objectAdmin
  ```

### "PgVector extension not found"

- **Solution**: Install extension manually
  ```bash
  gcloud sql connect INSTANCE --user=postgres --database=webui
  CREATE EXTENSION vector;
  ```

## Next Steps

1. **Test thoroughly** before deploying to production
2. **Set up monitoring** via Google Cloud Console
3. **Configure backups** (automatic with Cloud SQL)
4. **Deploy to Cloud Run** for production (see full guide)
5. **Set up domain & SSL** with Cloud Load Balancer

## Support

- Full Documentation: [CLOUD_MIGRATION_GUIDE.md](./CLOUD_MIGRATION_GUIDE.md)
- Open WebUI Docs: https://docs.openwebui.com
- Google Cloud SQL: https://cloud.google.com/sql/docs

## Compatibility

✅ **Yes**, Google Cloud SQL for PostgreSQL is fully compatible!

The application has built-in support for:
- PostgreSQL (with connection pooling)
- PgVector for embeddings
- Google Cloud Storage for files
- All features work identically to SQLite

The codebase handles database differences automatically through SQLAlchemy's dialect system.
