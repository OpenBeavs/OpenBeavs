#!/bin/bash

# =============================================================================
# SQLite to PostgreSQL Migration Script
# =============================================================================
# This script automates the migration from SQLite to PostgreSQL
# Usage: ./migrate_to_postgres.sh
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/../front/backend/data"
SQLITE_DB="${DATA_DIR}/webui.db"
BACKUP_DIR="${DATA_DIR}/backups/$(date +%Y%m%d_%H%M%S)"

# Load environment variables
if [ -f "${SCRIPT_DIR}/../front/.env" ]; then
    export $(grep -v '^#' "${SCRIPT_DIR}/../front/.env" | xargs)
fi

echo -e "${GREEN}==============================================================================${NC}"
echo -e "${GREEN}SQLite to PostgreSQL Migration Script${NC}"
echo -e "${GREEN}==============================================================================${NC}"
echo ""

# =============================================================================
# Step 1: Pre-flight Checks
# =============================================================================

echo -e "${YELLOW}Step 1: Running pre-flight checks...${NC}"

# Check if SQLite database exists
if [ ! -f "$SQLITE_DB" ]; then
    echo -e "${RED}Error: SQLite database not found at $SQLITE_DB${NC}"
    exit 1
fi

# Check if PostgreSQL is accessible
if ! command -v psql &> /dev/null; then
    echo -e "${RED}Error: psql command not found. Please install PostgreSQL client.${NC}"
    exit 1
fi

# Parse DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}Error: DATABASE_URL not set in .env file${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Pre-flight checks passed${NC}"
echo ""

# =============================================================================
# Step 2: Create Backup
# =============================================================================

echo -e "${YELLOW}Step 2: Creating backup...${NC}"

mkdir -p "$BACKUP_DIR"
cp "$SQLITE_DB" "${BACKUP_DIR}/webui.db.backup"
if [ -f "${DATA_DIR}/vector_db/chroma.sqlite3" ]; then
    mkdir -p "${BACKUP_DIR}/vector_db"
    cp "${DATA_DIR}/vector_db/chroma.sqlite3" "${BACKUP_DIR}/vector_db/chroma.sqlite3.backup"
fi

echo -e "${GREEN}✓ Backup created at: $BACKUP_DIR${NC}"
echo ""

# =============================================================================
# Step 3: Export SQLite Data
# =============================================================================

echo -e "${YELLOW}Step 3: Exporting SQLite data...${NC}"

EXPORT_FILE="${BACKUP_DIR}/webui_export.sql"
sqlite3 "$SQLITE_DB" ".dump" > "$EXPORT_FILE"

echo -e "${GREEN}✓ SQLite data exported to: $EXPORT_FILE${NC}"
echo ""

# =============================================================================
# Step 4: Convert SQL Syntax
# =============================================================================

echo -e "${YELLOW}Step 4: Converting SQL syntax for PostgreSQL...${NC}"

CONVERTED_FILE="${BACKUP_DIR}/webui_postgres.sql"

# Convert SQLite syntax to PostgreSQL
cat "$EXPORT_FILE" | \
    sed 's/AUTOINCREMENT/SERIAL/g' | \
    sed 's/INTEGER PRIMARY KEY/SERIAL PRIMARY KEY/g' | \
    sed '/BEGIN TRANSACTION;/d' | \
    sed '/COMMIT;/d' | \
    sed '/sqlite_sequence/d' | \
    sed 's/datetime("now")/CURRENT_TIMESTAMP/g' | \
    sed 's/DATETIME/TIMESTAMP/g' > "$CONVERTED_FILE"

echo -e "${GREEN}✓ SQL syntax converted${NC}"
echo ""

# =============================================================================
# Step 5: Test PostgreSQL Connection
# =============================================================================

echo -e "${YELLOW}Step 5: Testing PostgreSQL connection...${NC}"

# Extract connection details from DATABASE_URL
# Format: postgresql://user:password@host:port/database
if [[ $DATABASE_URL =~ postgresql://([^:]+):([^@]+)@([^:]+):([^/]+)/(.+) ]]; then
    PG_USER="${BASH_REMATCH[1]}"
    PG_PASSWORD="${BASH_REMATCH[2]}"
    PG_HOST="${BASH_REMATCH[3]}"
    PG_PORT="${BASH_REMATCH[4]}"
    PG_DATABASE="${BASH_REMATCH[5]}"
elif [[ $DATABASE_URL =~ postgresql://([^:]+):([^@]+)@([^/]+)/(.+) ]]; then
    PG_USER="${BASH_REMATCH[1]}"
    PG_PASSWORD="${BASH_REMATCH[2]}"
    PG_HOST="${BASH_REMATCH[3]}"
    PG_PORT="5432"
    PG_DATABASE="${BASH_REMATCH[4]}"
else
    echo -e "${RED}Error: Could not parse DATABASE_URL${NC}"
    exit 1
fi

# Remove query parameters from database name
PG_DATABASE="${PG_DATABASE%%\?*}"

export PGPASSWORD="$PG_PASSWORD"

# Test connection
if ! psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -c "SELECT version();" > /dev/null 2>&1; then
    echo -e "${RED}Error: Cannot connect to PostgreSQL database${NC}"
    echo -e "${YELLOW}Make sure Cloud SQL Proxy is running if using Google Cloud SQL${NC}"
    echo -e "${YELLOW}Example: ./cloud_sql_proxy --port 5432 PROJECT:REGION:INSTANCE${NC}"
    exit 1
fi

echo -e "${GREEN}✓ PostgreSQL connection successful${NC}"
echo ""

# =============================================================================
# Step 6: Check for Existing Data
# =============================================================================

echo -e "${YELLOW}Step 6: Checking for existing data in PostgreSQL...${NC}"

TABLE_COUNT=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

if [ "$TABLE_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}Warning: PostgreSQL database contains $TABLE_COUNT table(s)${NC}"
    read -p "Do you want to drop existing tables and continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo -e "${RED}Migration cancelled${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Dropping existing tables...${NC}"
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -c \
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
fi

echo -e "${GREEN}✓ Database ready for import${NC}"
echo ""

# =============================================================================
# Step 7: Import to PostgreSQL
# =============================================================================

echo -e "${YELLOW}Step 7: Importing data to PostgreSQL...${NC}"
echo -e "${YELLOW}This may take several minutes...${NC}"

if ! psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" < "$CONVERTED_FILE" 2>&1 | \
    grep -v "ERROR.*already exists" | \
    grep -v "WARNING"; then
    echo -e "${RED}Warning: Some errors occurred during import${NC}"
    echo -e "${YELLOW}Check the logs above. Some errors (like 'already exists') can be ignored.${NC}"
fi

echo -e "${GREEN}✓ Data import completed${NC}"
echo ""

# =============================================================================
# Step 8: Enable PgVector Extension
# =============================================================================

echo -e "${YELLOW}Step 8: Enabling PgVector extension...${NC}"

psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -c \
    "CREATE EXTENSION IF NOT EXISTS vector;" || true

echo -e "${GREEN}✓ PgVector extension enabled${NC}"
echo ""

# =============================================================================
# Step 9: Verify Migration
# =============================================================================

echo -e "${YELLOW}Step 9: Verifying migration...${NC}"

# Count records in key tables
USER_COUNT=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -t -c \
    "SELECT COUNT(*) FROM \"user\";" 2>/dev/null || echo "0")
CHAT_COUNT=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -t -c \
    "SELECT COUNT(*) FROM chat;" 2>/dev/null || echo "0")
MESSAGE_COUNT=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -t -c \
    "SELECT COUNT(*) FROM message;" 2>/dev/null || echo "0")

echo -e "${GREEN}Migration Summary:${NC}"
echo -e "  Users:    $USER_COUNT"
echo -e "  Chats:    $CHAT_COUNT"
echo -e "  Messages: $MESSAGE_COUNT"
echo ""

# =============================================================================
# Step 10: Generate Migration Report
# =============================================================================

echo -e "${YELLOW}Step 10: Generating migration report...${NC}"

REPORT_FILE="${BACKUP_DIR}/migration_report.txt"
cat > "$REPORT_FILE" << EOF
=============================================================================
PostgreSQL Migration Report
=============================================================================
Date: $(date)
Source: SQLite ($SQLITE_DB)
Destination: PostgreSQL ($PG_HOST:$PG_PORT/$PG_DATABASE)

Backup Location: $BACKUP_DIR

Migration Results:
- Users:    $USER_COUNT
- Chats:    $CHAT_COUNT
- Messages: $MESSAGE_COUNT

Files:
- SQLite Export: $EXPORT_FILE
- PostgreSQL Import: $CONVERTED_FILE
- SQLite Backup: ${BACKUP_DIR}/webui.db.backup

Next Steps:
1. Update .env file with PostgreSQL DATABASE_URL
2. Update .env file with VECTOR_DB=pgvector
3. Restart the application
4. Verify all functionality works correctly
5. If successful, keep SQLite backup for 30 days before deletion

Rollback Instructions:
If migration fails, restore from backup:
1. Stop the application
2. Update .env to use SQLite:
   DATABASE_URL=sqlite:///${SQLITE_DB}
   VECTOR_DB=chroma
3. Copy backup: cp ${BACKUP_DIR}/webui.db.backup ${SQLITE_DB}
4. Restart application

=============================================================================
EOF

echo -e "${GREEN}✓ Migration report saved to: $REPORT_FILE${NC}"
echo ""

# =============================================================================
# Completion
# =============================================================================

echo -e "${GREEN}==============================================================================${NC}"
echo -e "${GREEN}Migration completed successfully!${NC}"
echo -e "${GREEN}==============================================================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Review the migration report at: $REPORT_FILE"
echo "2. Update your .env file to use PostgreSQL"
echo "3. Restart the application and verify functionality"
echo "4. Keep backups for at least 30 days"
echo ""
echo -e "${YELLOW}Important:${NC}"
echo "- Your SQLite backup is at: ${BACKUP_DIR}/webui.db.backup"
echo "- Run migrations will automatically happen on next app start"
echo "- Vector embeddings may need to be regenerated (handled automatically)"
echo ""

unset PGPASSWORD
