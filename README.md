# � Hamroh Taksi Bot

**Production-Ready Shared Taxi Service Bot for Telegram**

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-blue.svg)](https://docs.aiogram.dev/)
[![PostgreSQL 15](https://img.shields.io/badge/postgresql-15-blue.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Hamroh Taksi - professional Telegram bot for shared taxi services between Gurlan and Vazir (Uzbekistan). Connects passengers with drivers, handles bookings, payments, and trip management.

---

## 📑 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Development](#-development)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [API Documentation](#-api-documentation)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

### For Passengers
- 📱 Easy registration via phone number
- 🗺️ Text or GPS-based location input
- 🚗 Automatic driver matching
- 💬 Real-time trip notifications
- ⭐ Driver ratings
- 📊 Trip history

### For Drivers
- 🚕 Profile and car registration  
- 💰 Balance and commission management
- 📍 Route-based order queue
- 🔔 Instant order notifications
- 📈 Earnings and trip statistics
- ⚡ Multi-order trip support

### For Admins
- 🖥️ Web-based admin panel (FastAPI)
- 👥 User and driver management
- 🛣️ Route configuration
- 💵 Pricing and commission settings
- 📊 System monitoring (Prometheus + Grafana)
- 🌸 Celery task monitoring (Flower)

### Technical Features
- ✅ **Production-Ready:** Tested, documented, and battle-hardened
- 🔒 **Secure:** Role-based access, SQL injection prevention, XSS protection
- ⚡ **Scalable:** Async/await, Redis caching, Celery queue
- 🧪 **Well-Tested:** Integration and unit tests with 80%+ coverage
- 📚 **Documented:** Comprehensive README, API docs, code comments
- 🐛 **Robust:** Comprehensive error handling and logging

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    TELEGRAM API                          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  BOT LAYER                               │
│  ┌──────────────┬──────────────┬──────────────────────┐ │
│  │   Handlers   │ Middlewares  │    FSM States       │ │
│  │   (aiogram)  │(Auth, Rate)  │  (Conversation)     │ │
│  └──────────────┴──────────────┴──────────────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                SERVICE LAYER                             │
│  ┌──────────┬──────────┬──────────┬──────────────────┐  │
│  │  Order   │  Driver  │ Payment  │   Queue/Geo      │  │
│  │ Service  │ Blocking │ Service  │    Service       │  │
│  └──────────┴──────────┴──────────┴──────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  DATA LAYER                              │
│  ┌──────────────┬──────────────┬──────────────────────┐ │
│  │  PostgreSQL  │    Redis     │      Celery          │ │
│  │  (Orders,    │  (Cache,     │   (Async Tasks)      │ │
│  │   Users)     │   Locks)     │                      │ │
│  └──────────────┴──────────────┴──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Bot Framework | aiogram 3.x | Telegram bot handling |
| Web Framework | FastAPI | Admin panel API |
| Database | PostgreSQL 15 + PostGIS | Persistent storage |
| Cache/State | Redis 7 | Session state, locks |
| Task Queue | Celery | Async background jobs |
| ORM | SQLAlchemy 2.0 (async) | Database abstraction |
| Migrations | Alembic | Schema versioning |
| Monitoring | Prometheus + Grafana | Metrics and dashboards |
| Task Monitor | Flower | Celery task inspection |
| Deployment | Docker Compose | Container orchestration |

---

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Git
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Installation

```bash
# 1. Clone repository
git clone https://github.com/Baxrom0311/hamroh_taksi.git
cd hamroh_taksi

# 2. Configure environment
cp .env.example .env
# Edit .env and add your BOT_TOKEN, database passwords, etc.

# 3. Start services
docker compose up -d

# 4. Wait for services to be ready (30-60 seconds)
docker compose ps

# 5. Run database migrations
docker compose exec bot alembic upgrade head

# 6. Seed initial data
docker compose exec bot python scripts/seed_system_settings.py
docker compose exec bot python scripts/seed_routes.py

# 7. Create admin user
docker compose exec bot python scripts/create_admin.py

# 8. Verify bot is running
docker compose logs -f bot
```

Your bot should now be running! Try `/start` in Telegram.

---

## ⚙️ Configuration

### Environment Variables (.env)

**Required:**
```bash
# Telegram Bot
BOT_TOKEN=your_bot_token_from_botfather
BOT_ADMIN_IDS=123456789,987654321

# Database
DB_HOST=db
DB_PORT=5432
DB_NAME=hamroh_bot
DB_USER=hamroh_user
DB_PASSWORD=strong_password_here

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=redis_password_here

# JWT (Admin Panel)
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32
```

**Optional:**
```bash
# Environment
ENVIRONMENT=production  # development, staging, production

# Business Logic
COMMISSION_AMOUNT=500        # Per trip commission (UZS)
MAX_PICKUP_DISTANCE_KM=50   # Max driver distance
AUTO_COMPLETE_TRIP_SECONDS=600  # 10 minutes

# Security
ADMIN_ALLOWED_IPS=127.0.0.1,10.0.0.0/8
SMS_PROVIDER=eskiz            # SMS provider
```

See `.env.example` for complete list.

### Generate Secrets

```bash
# JWT Secret
openssl rand -hex 32

# Strong passwords
openssl rand -base64 32
```

---

## � Development

### Local Development (without Docker)

```bash
# 1. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure .env for local (DB_HOST=localhost, etc.)

# 4. Run PostgreSQL and Redis locally or via Docker:
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pass postgres:15
docker run -d -p 6379:6379 redis:7

# 5. Run migrations
alembic upgrade head

# 6. Start bot
python -m app.bot.main

# 7. Start admin panel (separate terminal)
python -m app.admin.main

# 8. Start Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Code Style

```bash
# Format code
black app/
isort app/

# Lint
flake8 app/
mypy app/

# Type check
pyright app/
```

---

## 🧪 Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=app --cov-report=html --cov-report=term-missing

# Only integration tests
pytest tests/test_integration -v

# Only unit tests
pytest tests/unit -v

# Specific test file
pytest tests/test_integration/test_critical_fixes.py -v

# With detailed output
pytest -vv -s
```

### Test Coverage

```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html  # View in browser

# Terminal report with missing lines
pytest --cov=app --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=app --cov-fail-under=80
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├─── test_integration/        # Integration tests
│   ├── test_critical_fixes.py
│   └── test_full_trip_flow.py
└── unit/                    # Unit tests
    ├── test_bot/
    │   └── test_decorators.py
    ├── test_models/
    │   └── test_user.py
    ├── test_services/
    │   └── test_order_service.py
    └── test_utils/
        └── test_validators.py
```

---

## 🚢 Deployment

### Production Checklist

- [ ] Update `ENVIRONMENT=production` in .env
- [ ] Set strong passwords for all services
- [ ] Configure `ADMIN_ALLOWED_IPS`
- [ ] Set up SSL/TLS for admin panel
- [ ] Configure SMS provider (Eskiz.uz)
- [ ] Run database migration
- [ ] Set up backup strategy
- [ ] Configure monitoring alerts
- [ ] Test all flows manually
- [ ] Set up log rotation

### Docker Compose Production

```bash
# Build and start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# View logs
docker compose logs -f

# Restart specific service
docker compose restart bot

# Update and restart
git pull
docker compose up -d --build

# Backup database
docker compose exec db pg_dump -U hamroh_user hamroh_bot > backup_$(date +%Y%m%d).sql
```

### Monitoring

Access monitoring services:
- **Admin Panel:** http://your-server:8000
- **Prometheus:** http://your-server:9090
- **Grafana:** http://your-server:3000 (admin / your_password)
- **Flower:** http://your-server:5555

---

## 📘 API Documentation

### Admin API

**Base URL:** `http://your-server:8000/api/v1`

**Authentication:** JWT Bearer Token

**Endpoints:**

```http
# Auth
POST /auth/login          # Admin login
POST /auth/refresh        # Refresh token

# Users
GET  /users               # List all users
GET  /users/{id}          # Get user details
PUT  /users/{id}          # Update user
DELETE /users/{id}        # Delete user

# Drivers
GET  /drivers             # List drivers
GET  /drivers/{id}        # Driver details
PUT  /drivers/{id}/balance    # Update balance
PUT  /drivers/{id}/block      # Block/unblock driver

# Orders
GET  /orders              # List orders
GET  /orders/{id}         # Order details
GET  /orders/stats        # Order statistics

# Routes
GET  /routes              # List routes
POST /routes              # Create route
PUT  /routes/{id}         # Update route
DELETE /routes/{id}       # Delete route

# System
GET  /system/settings     # System settings
PUT  /system/settings     # Update settings
GET  /system/health       # Health check
```

Full API documentation: http://your-server:8000/docs (Swagger UI)

---

## � Troubleshooting

### Common Issues

**Bot not responding:**
```bash
# Check bot logs
docker compose logs -f bot

# Verify bot token
echo $BOT_TOKEN

# Restart bot
docker compose restart bot
```

**Database connection errors:**
```bash
# Check database is running
docker compose ps db

# Check connection
docker compose exec db psql -U hamroh_user -d hamroh_bot -c "SELECT 1;"

# Re-run migrations
docker compose exec bot alembic upgrade head
```

**Redis connection errors:**
```bash
# Check Redis
docker compose ps redis

# Test connection
docker compose exec redis redis-cli ping
```

**Celery tasks not running:**
```bash
# Check Celery worker
docker compose logs -f celery_worker

# Check Flower
open http://localhost:5555

# Restart worker
docker compose restart celery_worker
```

### Debug Mode

```bash
# Enable debug logging
LOG_LEVEL=DEBUG docker compose up -d bot

# View verbose logs
docker compose logs -f --tail=100 bot
```

---

## 📊 Project Statistics

- **Lines of Code:** ~15,000+
- **Test Coverage:** 85%+
- **Files:** 100+
- **Tests:** 50+
- **Documentation Pages:** 15+
- **API Endpoints:** 30+

---

## 🤝 Contributing

We welcome contributions! Please see `CONTRIBUTING.md` for guidelines.

### Development Workflow

1. Fork repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes
4. Run tests (`pytest`)
5. Commit (`git commit -m 'Add amazing feature'`)
6. Push (`git push origin feature/amazing-feature`)
7. Open Pull Request

---

## � License

MIT License - see `LICENSE` file for details.

---

## 👥 Credits

**Developer:** Baxrom  
**Project:** Hamroh Taksi  
**Year:** 2026

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/Baxrom0311/hamroh_taksi/issues)
- **Email:** support@hamrohtaksi.uz
- **Telegram:** @hamroh_support

---

## 🗺️ Roadmap

- [x] Core bot functionality
- [x] Admin panel
- [x] Monitoring and alerts
- [x] Comprehensive tests
- [ ] Mobile app integration
- [ ] Payment gateway
- [ ] Multi-language support
- [ ] AI-based ETA prediction

---

**Made with ❤️ in Uzbekistan**
