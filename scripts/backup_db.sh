#!/bin/bash

################################################################################
# scripts/backup_db.sh
#
# DATABASE BACKUP SCRIPT
#
# BU SCRIPT NIMA QILADI:
# - PostgreSQL database'ni backup qiladi
# - Compressed (gzip) format
# - Timestamp bilan nomlash
# - Old backup'larni tozalash (30 kundan eski)
#
# ISHLATISH:
#   chmod +x scripts/backup_db.sh
#   ./scripts/backup_db.sh
#
# CRON SETUP (har kuni 03:00):
#   0 3 * * * /path/to/hamroh_bot/scripts/backup_db.sh
################################################################################

set -e  # Exit on error

# ============================================
# CONFIGURATION
# ============================================

# Load .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Database config
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-hamroh_bot}"
DB_USER="${DB_USER:-hamroh_user}"
DB_PASSWORD="${DB_PASSWORD}"

# Backup config
BACKUP_DIR="backups"
RETENTION_DAYS=30

# ============================================
# COLORS
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================
# FUNCTIONS
# ============================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================
# MAIN
# ============================================

echo ""
echo "========================================"
echo "🗄️  DATABASE BACKUP"
echo "========================================"
echo ""

# Check if database password is set
if [ -z "$DB_PASSWORD" ]; then
    log_error "DB_PASSWORD not set in .env file!"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Generate timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/hamroh_${TIMESTAMP}.sql.gz"

log_info "Starting backup..."
log_info "Database: $DB_NAME@$DB_HOST:$DB_PORT"
log_info "User: $DB_USER"
log_info "Backup file: $BACKUP_FILE"

# Export password
export PGPASSWORD="$DB_PASSWORD"

# Create backup
if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    log_info "✅ Backup completed successfully!"
    
    # Get file size
    FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_info "Backup size: $FILE_SIZE"
else
    log_error "❌ Backup failed!"
    exit 1
fi

# Clean old backups
log_info "Cleaning old backups (older than $RETENTION_DAYS days)..."

DELETED_COUNT=$(find "$BACKUP_DIR" -name "hamroh_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete -print | wc -l)

if [ $DELETED_COUNT -gt 0 ]; then
    log_info "Deleted $DELETED_COUNT old backup(s)"
else
    log_info "No old backups to delete"
fi

# List all backups
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/hamroh_*.sql.gz 2>/dev/null | wc -l)
log_info "Total backups: $BACKUP_COUNT"

echo ""
echo "========================================"
echo "✅ BACKUP COMPLETED"
echo "========================================"
echo ""

# Unset password
unset PGPASSWORD

exit 0