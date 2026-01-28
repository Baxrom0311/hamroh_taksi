# 🚨 Rollback Procedure - Emergency Recovery

## ⚡ Quick Reference

**CRITICAL:** Follow steps in order. Do not skip!

---

## 🔴 Emergency Rollback (Full System)

### Step 1: Stop All Services
```bash
cd /Users/baxrom/ish_full/URDU_ISH/taksi
docker-compose down
```

### Step 2: Restore Database
```bash
# Find latest backup
ls -lh ./backups/ | grep hamroh_

# Restore (replace DATE with actual backup date)
docker-compose up -d postgres
docker exec -i hamroh_postgres psql -U hamroh_user hamroh_bot < ./backups/hamroh_YYYYMMDD.sql

# Or from compressed backup
gunzip -c ./backups/hamroh_YYYYMMDD.sql.gz | docker exec -i hamroh_postgres psql -U hamroh_user hamroh_bot
```

### Step 3: Downgrade Migrations (if needed)
```bash
# Check current migration
docker-compose run --rm bot alembic current

# Downgrade 1 step
docker-compose run --rm bot alembic downgrade -1

# Or to specific revision
docker-compose run --rm bot alembic downgrade <revision_id>
```

### Step 4: Restart Services
```bash
docker-compose up -d
```

### Step 5: Verify
```bash
# Check logs
docker-compose logs -f bot admin_panel

# Health check
curl http://localhost:8000/health

# Test bot
# Send /start to bot in Telegram
```

---

## 🟡 Code Rollback (Git)

### Revert Last Commit
```bash
cd /Users/baxrom/ish_full/URDU_ISH/taksi

# Revert (creates new commit)
git revert HEAD
git push origin main

# Rebuild and restart
docker-compose build
docker-compose up -d
```

### Rollback to Specific Commit
```bash
# Find commit hash
git log --oneline | head -10

# Reset (DESTRUCTIVE!)
git reset --hard <commit_hash>
git push -f origin main

# Rebuild
docker-compose build
docker-compose up -d
```

---

## 🟢 Partial Rollback

### Rollback Single Service

**Bot only:**
```bash
docker-compose up -d --build bot
```

**Admin panel only:**
```bash
docker-compose up -d --build admin_panel
```

**Celery worker only:**
```bash
docker-compose up -d --build celery_worker
```

### Rollback Database Migration Only
```bash
# Downgrade last migration
docker-compose run --rm bot alembic downgrade -1

# Restart services
docker-compose restart bot admin_panel celery_worker
```

### Clear Redis (if corrupted)
```bash
# Stop services using Redis
docker-compose stop bot celery_worker celery_beat

# Clear Redis
docker exec hamroh_redis redis-cli -a $REDIS_PASSWORD FLUSHALL

# Restart
docker-compose up -d
```

---

## 📊 Verification Checklist

After rollback, verify:

- [ ] **Database:** `docker exec hamroh_postgres psql -U hamroh_user hamroh_bot -c "SELECT COUNT(*) FROM users;"`
- [ ] **Redis:** `docker exec hamroh_redis redis-cli -a $REDIS_PASSWORD ping` → PONG
- [ ] **Bot:** Send `/start` in Telegram → Response
- [ ] **Admin:** Open http://localhost:8000 → Login works
- [ ] **Celery:** Check http://localhost:5555 (Flower) → Workers active
- [ ] **Prometheus:** Open http://localhost:9090 → Targets up
- [ ] **Grafana:** Open http://localhost:3000 → Dashboards loading

---

## 🔧 Common Rollback Scenarios

### Scenario 1: Bad Migration
```bash
docker-compose run --rm bot alembic downgrade -1
docker-compose restart
```

### Scenario 2: Code Bug
```bash
git revert HEAD
git push
docker-compose up -d --build
```

### Scenario 3: Database Corruption
```bash
docker-compose down
# Restore from backup (see Step 2 above)
docker-compose up -d
```

### Scenario 4: Redis Issues
```bash
docker exec hamroh_redis redis-cli -a $REDIS_PASSWORD FLUSHALL
docker-compose restart
```

### Scenario 5: Full System Failure
```bash
# Follow "Emergency Rollback (Full System)" above
```

---

## 🎯 Rollback Decision Matrix

| Problem | Action | Rollback Type |
|---------|--------|---------------|
| Bot not responding | Check logs first | Partial (bot) |
| Admin panel error | Check DB connection | Partial (admin) |
| Migration failure | Downgrade migration | Migration only |
| Data corruption | Restore from backup | Full system |
| Code bug | Git revert | Code only |
| Redis down | Restart Redis | Service restart |

---

## ⏱️ Estimated Recovery Times

| Rollback Type | Duration | Downtime |
|---------------|----------|----------|
| Code rollback | 2-5 min | ~2 min |
| Migration rollback | 1-3 min | ~1 min |
| Database restore | 5-15 min | ~10 min |
| Full system | 10-20 min | ~15 min |

---

## 🆘 Emergency Contacts

See [`EMERGENCY_CONTACTS.md`](./EMERGENCY_CONTACTS.md)

---

## 📝 Rollback Logs

After rollback, document:

```markdown
Date: YYYY-MM-DD HH:MM
Performed by: [Name]
Issue: [Description]
Rollback action: [What was done]
Result: [Success/Failure]
Notes: [Any observations]
```

Save in `docs/rollback_logs/YYYY-MM-DD.md`

---

*Last updated: 2026-01-28*
