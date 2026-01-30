# 🚀 PostgreSQL & Google Cloud Integration

Complete setup for migrating Genesis AI Hub from local SQLite to Google Cloud SQL (PostgreSQL) and Google Cloud Storage.

## 📚 Documentation Index

1. **[CLOUD_INTEGRATION_SUMMARY.md](./CLOUD_INTEGRATION_SUMMARY.md)** ⭐ START HERE
   - Executive summary answering all your questions
   - Compatibility information
   - What it takes to integrate
   - Cost analysis
   - Complete overview

2. **[QUICKSTART_CLOUD.md](./QUICKSTART_CLOUD.md)** ⚡ 15-MINUTE SETUP
   - Step-by-step quick guide
   - Get running in 15 minutes
   - Perfect for first-time setup

3. **[CLOUD_MIGRATION_GUIDE.md](./CLOUD_MIGRATION_GUIDE.md)** 📖 DETAILED GUIDE
   - Comprehensive documentation
   - All configuration options
   - Production deployment strategies
   - Troubleshooting guide

4. **[ARCHITECTURE_DIAGRAM.md](./ARCHITECTURE_DIAGRAM.md)** 🏗️ VISUAL GUIDE
   - Before/after architecture
   - Data flow diagrams
   - Network topology
   - Security model visualization

## 🎯 Quick Answer to Your Questions

### ✅ Is Google Cloud SQL for PostgreSQL compatible?

**YES! 100% compatible.** Your application has built-in support for:
- PostgreSQL (already has driver installed)
- PgVector for vector embeddings
- Google Cloud Storage for files
- All features work identically

**No code changes required!**

### ✅ What does it take to integrate?

**Time: 15-20 minutes**

```bash
# 1. Setup (5 min)
./setup_google_cloud.sh

# 2. Enable PgVector (1 min)
gcloud sql connect INSTANCE --user=postgres --database=webui
CREATE EXTENSION vector;

# 3. Start proxy (keeps running)
./start_cloud_sql_proxy.sh

# 4. Migrate data (5 min)
./migrate_to_postgres.sh

# 5. Configure (2 min)
cp front/.env.cloud.generated front/.env

# 6. Start app (1 min)
cd front/backend && ./start.sh

# Done! ✨
```

### ✅ How to deploy to cloud?

**After migration, choose deployment:**

- **Development**: Run locally (current setup)
- **Production**: Deploy to Cloud Run (1 command)
- **Advanced**: Deploy to GKE (Kubernetes)

---

## 🛠️ Automated Scripts Provided

### 1. Google Cloud Setup
```bash
./setup_google_cloud.sh
```
Creates:
- Cloud SQL PostgreSQL instance
- Google Cloud Storage bucket
- Service account with proper permissions
- Cloud SQL Proxy
- Environment configuration

### 2. Data Migration
```bash
./migrate_to_postgres.sh
```
Handles:
- SQLite backup (automatic)
- Data export and conversion
- PostgreSQL import
- Data verification
- Migration report

---

## 📊 What Changes?

| Component | Before | After |
|-----------|--------|-------|
| **Main Database** | SQLite (260KB local file) | PostgreSQL (Cloud SQL, scalable) |
| **Vector DB** | ChromaDB (164KB SQLite) | PgVector (in PostgreSQL) |
| **File Storage** | Local filesystem | Google Cloud Storage |
| **Cache** | Local filesystem | Local filesystem (unchanged) |

---

## 💰 Cost

| Deployment | Monthly Cost |
|------------|--------------|
| **Development** (db-f1-micro) | $10-15 |
| **Small Production** (db-n1-standard-1) | $60-80 |
| **Medium Production** (db-n1-standard-2) | $130-180 |

**Free tier**: $300 credit for first 90 days!

---

## 🎁 Benefits

✅ **Scalability**: Handle millions of users  
✅ **Reliability**: 99.95% uptime SLA  
✅ **Automatic Backups**: Daily + point-in-time recovery  
✅ **Multi-Instance**: Run multiple app instances  
✅ **Security**: Enterprise-grade encryption & audit logs  
✅ **Performance**: Optimized for concurrent access  
✅ **Unlimited Storage**: No file size limits  

---

## 🚦 Getting Started

### Prerequisites
- Google Cloud account (free $300 credit)
- `gcloud` CLI installed
- PostgreSQL client installed

### Quick Start

1. **Read the summary** (2 min)
   ```bash
   cat CLOUD_INTEGRATION_SUMMARY.md
   ```

2. **Run automated setup** (5 min)
   ```bash
   ./setup_google_cloud.sh
   ```

3. **Follow quickstart guide** (15 min)
   ```bash
   cat QUICKSTART_CLOUD.md
   ```

4. **Migrate your data** (5 min)
   ```bash
   ./migrate_to_postgres.sh
   ```

**Total time: ~30 minutes to fully migrated cloud setup!**

---

## 📁 Files Overview

```
├── CLOUD_INTEGRATION_SUMMARY.md     ⭐ START HERE - Answers all questions
├── QUICKSTART_CLOUD.md              ⚡ 15-min setup guide
├── CLOUD_MIGRATION_GUIDE.md         📖 Comprehensive documentation
├── ARCHITECTURE_DIAGRAM.md          🏗️ Visual architecture guide
│
├── setup_google_cloud.sh            🤖 Automated Cloud setup
├── migrate_to_postgres.sh           🤖 Automated data migration
├── start_cloud_sql_proxy.sh         🤖 Generated proxy launcher
│
├── front/.env.cloud.example         📝 Configuration template
└── front/.env.cloud.generated       📝 Auto-generated config (ready-to-use)
```

---

## 🔄 Migration Process

```
Current State                    Target State
┌──────────────┐                ┌──────────────┐
│   SQLite     │  Migration     │  PostgreSQL  │
│   ChromaDB   │  =========>    │  PgVector    │
│   Local FS   │  15 minutes    │  Cloud GCS   │
└──────────────┘                └──────────────┘

Your Mac                         Google Cloud
```

**Safety**: Original SQLite database is backed up and never modified!

---

## ✅ Compatibility Matrix

| Feature | SQLite | PostgreSQL | Status |
|---------|--------|------------|--------|
| User Management | ✅ | ✅ | Compatible |
| Chat History | ✅ | ✅ | Compatible |
| File Uploads | ✅ | ✅ | Compatible |
| Vector Search | ✅ (ChromaDB) | ✅ (PgVector) | Compatible |
| Embeddings | ✅ | ✅ | Compatible |
| Models | ✅ | ✅ | Compatible |
| Functions | ✅ | ✅ | Compatible |
| Tools | ✅ | ✅ | Compatible |
| Knowledge Bases | ✅ | ✅ | Compatible |
| OAuth | ✅ | ✅ | Compatible |
| Multi-Instance | ❌ | ✅ | **Upgrade** |
| Auto-Backup | ❌ | ✅ | **Upgrade** |
| Scalability | Limited | Unlimited | **Upgrade** |

---

## 🆘 Need Help?

1. **Read the docs** in order:
   - [CLOUD_INTEGRATION_SUMMARY.md](./CLOUD_INTEGRATION_SUMMARY.md)
   - [QUICKSTART_CLOUD.md](./QUICKSTART_CLOUD.md)
   - [CLOUD_MIGRATION_GUIDE.md](./CLOUD_MIGRATION_GUIDE.md)

2. **Check troubleshooting** sections in each guide

3. **Common issues**:
   - Can't connect: Make sure Cloud SQL Proxy is running
   - Permission denied: Check service account IAM roles
   - Import failed: Check conversion logs

---

## 🎓 Learning Path

### Beginner (Just Getting Started)
1. Read [CLOUD_INTEGRATION_SUMMARY.md](./CLOUD_INTEGRATION_SUMMARY.md)
2. Follow [QUICKSTART_CLOUD.md](./QUICKSTART_CLOUD.md)
3. Run `./setup_google_cloud.sh`
4. Test with development database

### Intermediate (Ready to Migrate)
1. Review [CLOUD_MIGRATION_GUIDE.md](./CLOUD_MIGRATION_GUIDE.md)
2. Run `./migrate_to_postgres.sh`
3. Verify all functionality
4. Monitor costs in Google Cloud Console

### Advanced (Production Deployment)
1. Study production deployment section
2. Set up Cloud Run or GKE
3. Configure monitoring and alerts
4. Implement backup strategy
5. Set up CI/CD pipeline

---

## 📈 Next Steps After Migration

1. ✅ **Verify functionality** (all features work)
2. ✅ **Monitor costs** (should be ~$10/month for dev)
3. ✅ **Set up monitoring** (Cloud Console)
4. ✅ **Configure alerts** (cost, errors, uptime)
5. ✅ **Plan production** (deployment strategy)
6. ✅ **Document custom setup** (your specific config)
7. ✅ **Train team** (access procedures)

---

## 🔐 Security Checklist

- [ ] Service account key stored securely
- [ ] `.env` file in `.gitignore`
- [ ] SSL/TLS enabled for database
- [ ] Private IP configured (production)
- [ ] Audit logging enabled
- [ ] Regular credential rotation scheduled
- [ ] Backup verification tested
- [ ] Access logging enabled for GCS
- [ ] IAM roles following least privilege
- [ ] Multi-factor authentication enabled

---

## 💡 Pro Tips

1. **Start small**: Use db-f1-micro for development
2. **Monitor first**: Watch metrics before scaling
3. **Test rollback**: Practice restore procedure
4. **Use staging**: Test changes before production
5. **Document custom**: Note any custom configurations
6. **Automate backup**: Verify backups work
7. **Set cost alerts**: Get notified at $20, $50, $100
8. **Use Secret Manager**: For production credentials
9. **Enable versioning**: On GCS bucket
10. **Review regularly**: Check security & costs monthly

---

## 🎉 Success Metrics

After migration, you should have:

- ✅ Application running on PostgreSQL
- ✅ Files stored in Google Cloud Storage
- ✅ Automatic daily backups
- ✅ All original data migrated successfully
- ✅ No data loss or corruption
- ✅ Same or better performance
- ✅ Cost under $15/month (dev)
- ✅ Ability to scale to any size
- ✅ Professional backup strategy
- ✅ Enterprise security

---

## 📞 Resources

- **Google Cloud SQL**: https://cloud.google.com/sql
- **PgVector Extension**: https://github.com/pgvector/pgvector
- **Cloud Storage**: https://cloud.google.com/storage
- **Open WebUI**: https://docs.openwebui.com
- **PostgreSQL**: https://www.postgresql.org/docs/

---

**Ready to start?** 

```bash
./setup_google_cloud.sh
```

**Questions?** Read [CLOUD_INTEGRATION_SUMMARY.md](./CLOUD_INTEGRATION_SUMMARY.md)

---

*Created for Genesis AI Hub - OSU Digital Transformation*
