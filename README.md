# 🚗 Hamroh Taksi Bot

Telegram asosida ishlovchi taksi agregatori: yo‘lovchi va haydovchilarni moslashtirish, admin panel, monitoring va fonda ishlovchi Celery worker’lari.

## 📋 Texnologiyalar
- Python 3.12, aiogram 3.x (bot)
- FastAPI (admin panel)
- PostgreSQL 15 + PostGIS, Redis 7
- Celery + Flower
- Docker Compose, Prometheus, Grafana

## ⚙️ Tezkor ishga tushirish (Docker)
1) Klon va sozlamalar:
```bash
git clone https://github.com/Baxrom0311/hamroh_taksi.git
cd hamroh_taksi
cp .env.example .env
# .env ni to‘ldiring (tokenlar, DB, Redis parollar)
```

2) Konteynerlarni ko‘tarish:
```bash
docker compose up -d
```

3) Migratsiyalar va seed:
```bash
docker compose exec bot alembic upgrade head
docker compose exec bot python scripts/seed_system_settings.py
docker compose exec bot python scripts/seed_routes.py
```

4) Admin yaratish:
```bash
docker compose exec bot python scripts/create_admin.py
```

## 🌐 Xizmatlar va portlar
- Bot: ichki
- Admin panel: `http://<host>:8000`
- Postgres: `5433` (host port) → container `5432`
- Redis: `6379`
- Prometheus: `9090`
- Grafana: `3000` (login: admin / .env dagi parol)
- Flower: `5555`

## 🧭 Asosiy komandalar
- Loglar: `docker compose logs -f bot` (yoki service nomi)
- Workerlar: `docker compose logs -f celery_worker`
- Stop/clean: `docker compose down -v`
- Rebuild: `docker compose up -d --build`

## 🧪 Testlar (local venv)
```bash
pip install -r requirements.txt
pytest
```

## 🛠 Muhim environment kalitlari (.env)
- `BOT_TOKEN`, `BOT_ADMIN_IDS`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `JWT_SECRET_KEY`
- `ADMIN_ALLOWED_IPS`
- `GRAFANA_ADMIN_PASSWORD` (agar override qilsangiz)

## 🔍 Troubleshooting
- **`relation "users" does not exist`**: migratsiyalarni qayta ishlating (`alembic upgrade head`) va seed skriptlarni ishga tushiring.
- **bcrypt ogohlantirishlari**: requirements-da `bcrypt==4.0.1` bor, konteynerlarda `pip install -r requirements.txt` avtomatik qo‘yiladi; muammo bo‘lsa `docker compose exec bot pip install "bcrypt==4.0.1"`.
- **Divergent branches (git pull)**: `git pull --rebase origin main` yoki `git pull --no-rebase origin main`.

## 📈 Monitoring
- Prometheus targets: `http://<host>:9090/targets`
- Grafana: `http://<host>:3000` → Prometheus datasource `http://prometheus:9090`
- Flower: `http://<host>:5555` (basic auth agar qo‘yilgan bo‘lsa)

## 📜 License
MIT
