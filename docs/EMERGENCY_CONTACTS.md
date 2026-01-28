# 📞 Emergency Contacts & Support

## 🚨 Critical Emergency Contacts

### Development Team

| Role | Name | Phone | Telegram | Email | Availability |
|------|------|-------|----------|-------|--------------|
| **Lead Developer** | Baxrom | +998-XX-XXX-XXXX | @baxrom | baxrom@example.com | 24/7 |
| **Backend Developer** | TBD | +998-XX-XXX-XXXX | @dev2 | dev2@example.com | 9AM-6PM |
| **DevOps** | TBD | +998-XX-XXX-XXXX | @devops | devops@example.com | On-call |

### External Services

| Service | Support | Contact | Response Time |
|---------|---------|---------|---------------|
| **SMS Provider (Eskiz.uz)** | Eskiz Support | support@eskiz.uz | 24-48h |
| **Hosting Provider** | TBD | support@host.com | 1-4h |
| **Database Backup** | TBD | backup@service.com | 1h |

---

## 🔥 Emergency Procedures

### 1. Bot Not Responding

**Contact:** Lead Developer  
**Expected Response:** < 30 minutes

**Quick Checks:**
```bash
# Check bot container
docker ps | grep hamroh_bot

# Check logs
docker logs hamroh_bot --tail 50

# Restart
docker-compose restart bot
```

**Escalation:** If not resolved in 1 hour, contact DevOps

---

### 2. Database Down

**Contact:** DevOps  
**Expected Response:** < 15 minutes

**Quick Checks:**
```bash
# Check PostgreSQL
docker exec hamroh_postgres pg_isready -U hamroh_user

# Restore from backup
./scripts/backup_db.sh restore
```

**Escalation:** If data loss suspected, immediately restore latest backup

---

### 3. High Error Rate (>100 errors/min)

**Contact:** Lead Developer  
**Expected Response:** < 1 hour

**Quick Checks:**
```bash
# Check error logs
tail -f logs/hamroh_*.log | grep ERROR

# Check Grafana dashboard
# http://localhost:3000
```

**Escalation:** If critical bug, rollback to last stable version

---

### 4. Redis Connection Issues

**Contact:** DevOps  
**Expected Response:** < 30 minutes

**Quick Checks:**
```bash
# Check Redis
docker exec hamroh_redis redis-cli -a $REDIS_PASSWORD ping

# Restart Redis
docker-compose restart redis
```

**Escalation:** If persistent, switch to in-memory fallback

---

### 5. SMS Service Failure

**Contact:** Eskiz.uz Support  
**Expected Response:** 24-48 hours

**Workaround:**
- Temporarily disable SMS verification
- Use manual verification via admin panel

---

## 📊 Monitoring & Alerts

### Dashboard URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / ${GRAFANA_ADMIN_PASSWORD} |
| **Prometheus** | http://localhost:9090 | - |
| **Flower (Celery)** | http://localhost:5555 | ${FLOWER_USER} / ${FLOWER_PASSWORD} |
| **Admin Panel** | http://localhost:8000 | See database |

### Critical Metrics

Monitor these in Grafana:

- **Bot Response Time:** < 1s (normal), > 5s (alert)
- **Database Connections:** < 80% pool (normal), > 90% (alert)
- **Redis Memory:** < 80% (normal), > 90% (alert)
- **Celery Queue Length:** < 100 (normal), > 500 (alert)
- **Error Rate:** < 10/min (normal), > 100/min (critical)

---

## 🛠️ Common Issues & Solutions

### Issue 1: "Message Too Long" Error

**Symptoms:** Bot crashes when sending long messages  
**Solution:**
```python
# Truncate long messages in error handler
# app/utils/error_sanitizer.py
```

**Contact:** Backend Developer

---

### Issue 2: Driver Not Receiving Orders

**Symptoms:** Orders stuck in PENDING  
**Quick Fix:**
```bash
# Check Redis queue
docker exec hamroh_redis redis-cli -a $REDIS_PASSWORD ZRANGE queue:route:1 0 -1 WITHSCORES

# Clear stale locks
docker exec hamroh_redis redis-cli -a $REDIS_PASSWORD DEL order:lock:*
```

**Contact:** Lead Developer

---

### Issue 3: Database Connection Pool Exhausted

**Symptoms:** "Too many connections" error  
**Quick Fix:**
```bash
# Restart services to free connections
docker-compose restart bot admin_panel celery_worker

# Check active connections
docker exec hamroh_postgres psql -U hamroh_user hamroh_bot -c "SELECT count(*) FROM pg_stat_activity;"
```

**Contact:** DevOps

---

### Issue 4: Celery Workers Not Processing

**Symptoms:** Tasks stuck in queue  
**Quick Fix:**
```bash
# Check workers
curl http://localhost:5555/api/workers

# Restart workers
docker-compose restart celery_worker celery_beat
```

**Contact:** Backend Developer

---

### Issue 5: Prometheus Metrics Missing

**Symptoms:** Grafana shows no data  
**Quick Fix:**
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Restart Prometheus
docker-compose restart prometheus
```

**Contact:** DevOps

---

## 📱 Notification Channels

### Critical Alerts
- **Telegram:** @hamroh_alerts_bot (if configured)
- **SMS:** Team lead only
- **Email:** All team members

### Warning Alerts
- **Telegram:** Development channel
- **Email:** Team lead

### Info Notifications
- **Grafana Dashboard:** View only
- **Logs:** Rotated daily

---

## 🔐 Access & Credentials

### Production Servers

| Server | IP | SSH Key | Location |
|--------|----|---------| ---------|
| Main App | TBD | `~/.ssh/hamroh_prod` | See hosting docs |
| Database | TBD | Same as app | See hosting docs |

### Service Credentials

**Location:** `.env` file (DO NOT COMMIT!)

```env
BOT_TOKEN=6xxxxxxxxx:AAxxxxxxxxx
DB_PASSWORD=strong_password_here
REDIS_PASSWORD=strong_password_here
JWT_SECRET_KEY=32_char_secret
SMS_API_EMAIL=email@example.com
SMS_API_PASSWORD=sms_password
FLOWER_USER=admin
FLOWER_PASSWORD=flower_password
GRAFANA_ADMIN_PASSWORD=grafana_password
```

**Backup Location:** Password manager (1Password/Bitwarden)

---

## 📋 Escalation Matrix

| Severity | Response Time | Who to Contact | Action |
|----------|---------------|----------------|--------|
| **Critical** (Service down) | < 15 min | Lead Dev + DevOps | Immediate fix/rollback |
| **High** (Major bug) | < 1 hour | Lead Dev | Fix in next deploy |
| **Medium** (Minor bug) | < 4 hours | Backend Dev | Fix in sprint |
| **Low** (Feature request) | Next sprint | Team discussion | Backlog |

---

## 🆘 When All Else Fails

1. **Stop the bleeding:** `docker-compose down`
2. **Notify users:** Telegram broadcast (if possible)
3. **Restore from backup:** See `ROLLBACK.md`
4. **Contact team lead:** Immediate call
5. **Document incident:** `docs/incident_reports/`

---

## 📝 Incident Report Template

```markdown
# Incident Report - [DATE]

## Summary
Brief description of the issue

## Timeline
- HH:MM - Issue detected
- HH:MM - Team notified
- HH:MM - Fix deployed
- HH:MM - Service restored

## Impact
- Users affected: XX
- Downtime: XX minutes
- Data loss: Yes/No

## Root Cause
What caused the issue

## Resolution
How it was fixed

## Prevention
Steps to prevent recurrence

## Action Items
- [ ] Task 1
- [ ] Task 2
```

Save in `docs/incident_reports/YYYY-MM-DD-incident.md`

---

*Last updated: 2026-01-28*  
*Review quarterly and after major incidents*
