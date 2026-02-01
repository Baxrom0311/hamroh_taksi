#!/bin/bash
# Docker Cleanup Script - Serverning RAM va disk bo'shatish
# Har kuni avtomatik ishga tushadi (cron)

set -e

echo "🧹 Starting Docker cleanup..."

# 1. Unused containers
echo "🗑️  Removing unused containers..."
docker container prune -f

# 2. Unused images (dangling)
echo "🗑️  Removing dangling images..."
docker image prune -f

# 3. Unused volumes (DIQQAT: Backup olganingizdan keyin ishlatish!)
# echo "🗑️  Removing unused volumes..."
# docker volume prune -f

# 4. Build cache (eski build cache'lar)
echo "🗑️  Removing build cache..."
docker builder prune -f --filter "until=24h"

# 5. Logs tozalash (30 kundan eski)
echo "📝 Cleaning old logs..."
find logs/ -name "*.log" -type f -mtime +30 -delete 2>/dev/null || true

# 6. Docker logs truncate (container logs haddan tashqari kattalashmaslik uchun)
echo "📝 Truncating container logs..."
for container in $(docker ps -q); do
    docker inspect --format='{{.LogPath}}' $container | xargs truncate -s 10M 2>/dev/null || true
done

# 7. System-wide cleanup
echo "🧹 System-wide Docker cleanup..."
docker system prune -f --volumes=false

# 8. Statistika
echo ""
echo "📊 Current Docker disk usage:"
docker system df

echo ""
echo "✅ Cleanup completed!"
