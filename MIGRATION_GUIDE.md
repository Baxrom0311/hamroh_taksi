# ALEMBIC MIGRATION GUIDE

## ✅ YARATILGAN MIGRATION

**Fayl:** `alembic/versions/45ac19888cb1_add_system_settings_and_driver_ban_.py`

**Jadvallar:**
1. `system_settings` - Tizim sozlamalari
2. `driver_ban_records` - Haydovchi ban yozuvlari

---

## 🚀 MIGRATION ISHGA TUSHIRISH

### 1. .env faylni tekshirish

`.env` fayl mavjudligini va to'g'riligini tekshiring:

```bash
# Database sozlamalari
DB_HOST=192.168.1.7
DB_PORT=5432
DB_NAME=hamroh_bot
DB_USER=hamroh_user
DB_PASSWORD=root
```

### 2. Migration'ni ishga tushirish

```bash
# Migration holatini ko'rish
python -m alembic current

# Migration'ni upgrade qilish
python -m alembic upgrade head

# Yoki ma'lum bir revision'ga
python -m alembic upgrade 45ac19888cb1
```

### 3. Migration'ni tekshirish

```bash
# Barcha migration'larni ko'rish
python -m alembic history

# Joriy migration'ni ko'rish
python -m alembic current
```

### 4. Default sozlamalarni yuklash

Migration'dan keyin default sozlamalarni yuklash:

```bash
python scripts/seed_system_settings.py
```

---

## 📋 MIGRATION TAFSILOTLARI

### system_settings jadvali

**Ustunlar:**
- `setting_key` (PK) - Sozlama kaliti
- `setting_value` - Sozlama qiymati
- `description` - Tavsif
- `created_at` - Yaratilgan vaqt
- `updated_at` - Yangilangan vaqt

**Default sozlamalar:**
- `commission_amount` = 5000
- `bot_is_free` = true
- `ban_percentage_threshold` = 50
- `ban_count_threshold` = 5
- `max_driver_change_per_hour` = 3

### driver_ban_records jadvali

**Ustunlar:**
- `ban_id` (PK) - Ban ID
- `driver_id` (FK) - Haydovchi ID
- `passenger_id` (FK) - Yo'lovchi ID
- `order_id` (FK) - Buyurtma ID
- `reason` - Ban sababi
- `reviewed_by_admin` - Admin ko'rib chiqdimi?
- `admin_id` (FK) - Admin ID
- `reviewed_at` - Ko'rib chiqilgan vaqt
- `created_at` - Yaratilgan vaqt

---

## ⚠️ MUAMMOLAR VA YECHIMLAR

### 1. NumPy/Shapely xatosi

Agar migration yaratishda NumPy xatosi bo'lsa:

```bash
pip install "numpy<2"
```

Yoki:

```bash
pip install --upgrade shapely geoalchemy2
```

### 2. Database ulanish xatosi

`.env` faylda database sozlamalarini tekshiring:

```env
DB_HOST=192.168.1.7
DB_PORT=5432
DB_NAME=hamroh_bot
DB_USER=hamroh_user
DB_PASSWORD=root
```

### 3. Migration rollback

Agar xato bo'lsa, rollback qilish:

```bash
# Birinchi oldingi migration'ga qaytish
python -m alembic downgrade -1

# Yoki ma'lum bir revision'ga
python -m alembic downgrade d0de3df238a3
```

---

## ✅ TEKSHIRUV

Migration muvaffaqiyatli bo'lganini tekshirish:

```sql
-- PostgreSQL'da
\dt system_settings
\dt driver_ban_records

-- Yoki
SELECT * FROM system_settings;
SELECT * FROM driver_ban_records LIMIT 5;
```

---

## 📝 KEYINGI QADAMLAR

1. ✅ Migration yaratildi
2. ⏳ Migration'ni ishga tushirish (`alembic upgrade head`)
3. ⏳ Default sozlamalarni yuklash
4. ⏳ Test qilish
