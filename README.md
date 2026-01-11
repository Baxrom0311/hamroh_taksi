# 🚗 Hamroh Bot - Taksi Agregator Bot

Professional taksi agregator bot tizimi Telegram uchun.

## 🎯 Xususiyatlar

- ✅ Yo'lovchi va haydovchilarni avtomatik birlashtirish
- ✅ Real-time geo-lokatsiya tracking
- ✅ To'lov va balans tizimi
- ✅ Admin panel (Web-based)
- ✅ Rating va ban tizimi
- ✅ SMS tasdiqlash
- ✅ Production-ready (scalable)

## 🛠 Texnologiyalar

- Python 3.10+
- aiogram 3.x (Telegram Bot)
- PostgreSQL 15 + PostGIS
- Redis 7
- Celery
- FastAPI (Admin Panel)
- Docker + Docker Compose

## 📦 O'rnatish

### 1. Clone repository
```bash
git clone https://github.com/your-repo/hamroh_bot.git
cd hamroh_bot
```

### 2. Environment o'rnatish
```bash
cp .env.example .env
nano .env  # O'zgarishlarni kiriting
```

### 3. Docker bilan ishga tushirish
```bash
docker-compose up -d
```

### 4. Database migration
```bash
docker-compose exec bot alembic upgrade head
```

### 5. Admin yaratish
```bash
docker-compose exec bot python scripts/create_admin.py
```

## 🚀 Ishga tushirish

### Development
```bash
python -m app.bot.main
```

### Production
```bash
docker-compose up -d
```

## 📊 Monitoring

- Admin Panel: http://localhost:8000
- Prometheus Metrics: http://localhost:8000/metrics
- Health Check: http://localhost:8000/health

## 🧪 Testing

```bash
pytest
pytest --cov=app tests/
```

## 📝 License

MIT License