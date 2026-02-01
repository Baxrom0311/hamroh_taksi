#!/bin/bash

# Configuration
CONTAINER_NAME="hamroh_postgres"
DB_USER="hamroh_user"
DB_NAME="hamroh_bot"  # Default DB name
BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="$BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"

# Create backup directory if not exists
mkdir -p $BACKUP_DIR

# Run backup
echo "Creating backup of $DB_NAME from $CONTAINER_NAME..."
docker exec -t $CONTAINER_NAME pg_dump -U $DB_USER $DB_NAME | gzip > $FILENAME

# Check if backup was successful
if [ $? -eq 0 ]; then
    echo "✅ Backup successfully created: $FILENAME"
    
    # Delete backups older than 7 days
    find $BACKUP_DIR -type f -name "db_backup_*.sql.gz" -mtime +7 -delete
    echo "🧹 Cleaned up old backups (older than 7 days)"
    
    # --- AWS S3 UPLOAD (Optional) ---
    # Agar AWS S3 ga yuklamoqchi bo'lsangiz, pastdagi qatorni activlashtiring:
    # BUCKET="s3://my-taxi-backups"
    # aws s3 cp $FILENAME $BUCKET --quiet && echo "☁️ Uploaded to S3" || echo "❌ S3 Upload warning"
    
else
    echo "❌ Backup failed!"
    exit 1
fi