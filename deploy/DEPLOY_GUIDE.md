# Hamroh Taksi — Northflank Deploy Yo'riqnomasi

## Arxitektura

```
┌─── Akkaunt 1 ───────────────┐     ┌─── Akkaunt 2 ───────────────┐
│ Service 1: Bot (aiogram)     │     │ Service 1: Celery Worker     │
│ Service 2: Admin Panel       │     │ Service 2: Celery Beat       │
│ DB: PostgreSQL (public TLS)──│──┐  │ DB: Redis (public TLS)───────│──┐
└──────────────────────────────┘  │  └──────────────────────────────┘  │
                                  │                                     │
            Hammasi ulanadi ◄─────┴─────────────────────────────────────┘
```

- Akkaunt 1 dagi service lar Redis ga **tashqi TLS** orqali ulanadi
- Akkaunt 2 dagi service lar PostgreSQL ga **tashqi TLS** orqali ulanadi

---

## 1-qadam: GitHub Repository

Kod GitHub da bo'lishi kerak (Northflank GitHub dan build qiladi):

```bash
git remote add origin https://github.com/YOUR_USERNAME/hamroh-taksi.git
git push -u origin main
```

> ⚠️ `.env` faylni PUSH QILMANG! `.gitignore` da bo'lishi kerak.

---

## 2-qadam: Akkaunt 1 — Bot + Admin + PostgreSQL

### 2.1. Northflank akkaunt ochish
1. https://northflank.com ga boring → Sign Up (email 1)
2. Yangi project yarating: `hamroh-bot`

### 2.2. PostgreSQL addon yaratish
1. Project ichida → **Add addon** → **PostgreSQL**
2. Sozlamalar:
   - Name: `hamroh-postgres`
   - Version: 15+
   - Storage: default (0.5 GB)
3. Yaratgandan keyin → **Settings** → **Networking**:
   - ✅ **Deploy with TLS** — yoqing
   - ✅ **Publicly accessible** — yoqing
4. **Connection Details** dan yozib oling:
   - Internal: `host`, `port`, `user`, `password`, `database`
   - External: `host`, `port` (akkaunt 2 uchun kerak)

### 2.3. Database migration
Northflank da **Job** yarating (bir martalik):
- Name: `db-migrate`
- Type: **Manual Job**
- Docker build from repo
- Start command: `alembic upgrade head && python scripts/seed_routes.py`
- Env vars: PostgreSQL internal connection

Yoki lokaldagi kompyuterdan:
```bash
DATABASE_URL=postgresql://<user>:<pass>@<external-host>:<port>/<db>?sslmode=require \
alembic upgrade head
```

### 2.4. Bot service yaratish
1. **Add service** → **Combined** (build + run)
2. Sozlamalar:
   - Name: `bot`
   - GitHub repo: tanlang
   - Branch: `main`
   - Dockerfile path: `./Dockerfile`
   - Start command: `python -m app.bot.main`
   - Port: **none** (bot webhook emas, polling)
   - Resources: kichik (0.1 vCPU, 256-512 MB)
3. **Environment variables** → `account1.env.example` dagi barcha qiymatlarni kiriting
   - `DB_HOST` = PostgreSQL addon **internal** host
   - `REDIS_URL` = akkaunt 2 dagi Redis **external** URL

### 2.5. Admin Panel service yaratish
1. **Add service** → **Combined**
2. Sozlamalar:
   - Name: `admin-panel`
   - Same repo, same Dockerfile
   - Start command: `uvicorn app.admin.main:app --host 0.0.0.0 --port 8000`
   - Port: `8000` (HTTP)
   - Resources: kichik
3. **Environment variables** → Bot bilan bir xil (account1.env.example)
4. **Networking** → Public URL yoqing (admin panel uchun)

### 2.6. Admin foydalanuvchi yaratish
Northflank da bir martalik Job:
```bash
python scripts/create_admin.py
```

---

## 3-qadam: Akkaunt 2 — Celery + Redis

### 3.1. Northflank akkaunt ochish
1. https://northflank.com ga boring → Sign Up (email 2)
2. Yangi project yarating: `hamroh-celery`

### 3.2. Redis addon yaratish
1. **Add addon** → **Redis**
2. Sozlamalar:
   - Name: `hamroh-redis`
   - Version: 7+
3. Yaratgandan keyin → **Settings** → **Networking**:
   - ✅ **Deploy with TLS** — yoqing
   - ✅ **Publicly accessible** — yoqing
4. **Connection Details** dan yozib oling:
   - Internal: `host`, `port`, `password`
   - External: `host`, `port`, full URL (akkaunt 1 uchun kerak)

### 3.3. Celery Worker service yaratish
1. **Add service** → **Combined**
2. Sozlamalar:
   - Name: `celery-worker`
   - Same GitHub repo
   - Start command: `celery -A app.core.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=500`
   - Port: **none**
   - Resources: kichik (0.1 vCPU, 256-512 MB)
3. **Environment variables** → `account2.env.example` dagi qiymatlar
   - `DATABASE_URL` = akkaunt 1 dagi PostgreSQL **external** URL + `?ssl=require`
   - `REDIS_HOST` = Redis addon **internal** host

### 3.4. Celery Beat service yaratish
1. **Add service** → **Combined**
2. Sozlamalar:
   - Name: `celery-beat`
   - Same repo
   - Start command: `celery -A app.core.celery_app beat --loglevel=info`
   - Port: **none**
   - Resources: eng kichik
3. **Environment variables** → Celery Worker bilan bir xil

---

## 4-qadam: Cross-Account Ulanishlarni Sozlash

### Akkaunt 1 → Akkaunt 2 Redis
1. Akkaunt 2 da Redis addon → Connection Details → **External** URL ni ko'chirib oling
2. Format: `rediss://:<password>@<host>:<port>`
3. Akkaunt 1 da ikkala service ga env var qo'shing:
   ```
   REDIS_URL=rediss://:<password>@<host>:<port>/0
   ```

### Akkaunt 2 → Akkaunt 1 PostgreSQL
1. Akkaunt 1 da PostgreSQL addon → Connection Details → **External** ni ko'chirib oling
2. Format: `postgresql://<user>:<password>@<host>:<port>/<db>`
3. Akkaunt 2 da ikkala service ga env var qo'shing:
   ```
   DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:<port>/hamroh_bot?ssl=require
   ```

---

## 5-qadam: Tekshirish

1. **Akkaunt 2** service larni avval ishga tushiring (Redis kerak)
2. **Akkaunt 1** service larni ishga tushiring
3. Telegram botga `/start` yuboring — ishlashi kerak
4. Admin panel URL ni oching — login sahifasi ko'rinishi kerak
5. Northflank Logs orqali xatolarni tekshiring

---

## Muhim Eslatmalar

- 🔐 **BOT_TOKEN** va boshqa secrets ni hech qachon Git ga push qilmang
- 🔄 **Deploy**: GitHub ga push qilsangiz, Northflank avtomatik rebuild qiladi
- 📊 **Monitoring**: Northflank dashboard dan CPU/RAM/Logs ni ko'ring
- 💾 **Backup**: PostgreSQL addon da avtomatik backup bor
- ⚠️ **Free tier**: Production uchun emas, test/MVP uchun yetarli
- 🌐 **SSL**: Tashqi DB ulanishlar har doim TLS orqali (rediss://, ?ssl=require)

---

## Env Vars Xulosa Jadvali

| Env Var | Akkaunt 1 (Bot+Admin) | Akkaunt 2 (Celery) |
|---------|----------------------|---------------------|
| DB_HOST | PostgreSQL **ichki** host | - |
| DATABASE_URL | - | PostgreSQL **tashqi** URL |
| REDIS_URL | Redis **tashqi** URL | - |
| REDIS_HOST | - | Redis **ichki** host |
| BOT_TOKEN | ✅ bir xil | ✅ bir xil |
| JWT_SECRET_KEY | ✅ bir xil | ✅ bir xil |
