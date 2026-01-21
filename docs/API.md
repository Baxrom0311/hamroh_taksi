# 📚 API Documentation - Hamroh Taksi Bot

**Version:** 1.0.0  
**Last Updated:** 2026-01-20

---

## 🌐 Base URLs

- **Production:** `https://api.hamrohtaksi.uz/api/v1`
- **Staging:** `https://staging-api.hamrohtaksi.uz/api/v1`
- **Development:** `http://localhost:8000/api/v1`

---

## 🔐 Authentication

All API endpoints require JWT authentication except `/auth/login` and `/system/health`.

### Login

```http
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

### Using Token

```http
GET /users
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

---

## 👥 Users API

### List Users

```http
GET /users?page=1&limit=50&role=passenger
```

**Query Parameters:**
- `page` (int, optional): Page number (default: 1)
- `limit` (int, optional): Items per page (default: 50, max: 100)
- `role` (string, optional): Filter by role (`passenger`, `driver`, `admin`)
- `search` (string, optional): Search by name or phone

**Response:**
```json
{
  "total": 150,
  "page": 1,
  "limit": 50,
  "data": [
    {
      "user_id": 123456789,
      "phone_number": "+998901234567",
      "role": "passenger",
      "first_name": "Ali",
      "is_blocked": false,
      "created_at": "2026-01-15T10:30:00Z"
    }
  ]
}
```

### Get User Details

``` http
GET /users/{user_id}
```

**Response:**
```json
{
  "user_id": 123456789,
  "phone_number": "+998901234567",
  "role": "passenger",
  "first_name": "Ali",
  "last_name": "Karimov",
  "username": "ali_k",
  "is_blocked": false,
  "created_at": "2026-01-15T10:30:00Z",
  "passenger": {
    "passenger_id": 1,
    "full_name": "Ali Karimov",
    "gender": "male",
    "age": 25,
    "total_trips": 15,
    "average_rating": 4.8
  }
}
```

---

## 🚗 Drivers API

### List Drivers

```http
GET /drivers?status=active&route_id=1
```

**Query Parameters:**
- `status` (string): `active`, `on_trip`, `blocked`, `all`
- `route_id` (int): Filter by route
- `min_balance` (int): Minimum balance

**Response:**
```json
{
  "total": 45,
  "data": [
    {
      "driver_id": 1,
      "user_id": 987654321,
      "full_name": "Bobur Alimardonov",
      "car_model": "Chevrolet Cobalt",
      "car_color": "White",
      "car_number": "01 A 123 BC",
      "balance": 50000,
      "available_seats": 4,
      "is_active": true,
      "is_on_trip": false,
      "is_blocked": false,
      "rating": 4.9,
      "total_trips": 245
    }
  ]
}
```

### Update Driver Balance

```http
PUT /drivers/{driver_id}/balance
Content-Type: application/json

{
  "amount": 10000,
  "reason": "Balance top-up",
  "transaction_type": "credit"
}
```

**Response:**
```json
{
  "driver_id": 1,
  "old_balance": 50000,
  "new_balance": 60000,
  "transaction_id": 12345
}
```

### Block/Unblock Driver

```http
PUT /drivers/{driver_id}/block
Content-Type: application/json

{
  "is_blocked": true,
  "reason": "Multiple violations"
}
```

---

## 📦 Orders API

### List Orders

```http
GET /orders?status=in_progress&date_from=2026-01-01
```

**Query Parameters:**
- `status`: `pending`, `accepted`, `in_progress`, `completed`, `cancelled`
- `date_from`: ISO date
- `date_to`: ISO date
- `driver_id`: Filter by driver
- `passenger_id`: Filter by passenger
- `route_id`: Filter by route

**Response:**
```json
{
  "total": 1250,
  "data": [
    {
      "order_id": 1001,
      "passenger_id": 1,
      "driver_id": 5,
      "route_id": 1,
      "status": "in_progress",
      "pickup_location": "Gurlan bozori",
      "pickup_lat": 41.3111,
      "pickup_lon": 69.2797,
      "passenger_count": 2,
      "commission_amount": 500,
      "created_at": "2026-01-20T14:30:00Z",
      "started_at": "2026-01-20T14:45:00Z"
    }
  ]
}
```

### Order Statistics

```http
GET /orders/stats?period=month
```

**Response:**
```json
{
  "period": "2026-01",
  "total_orders": 1250,
  "completed": 1100,
  "cancelled": 50,
  "in_progress": 100,
  "total_revenue": 625000,
  "average_trip_duration": 42,
  "completion_rate": 0.88
}
```

---

## 🛣️ Routes API

### List Routes

```http
GET /routes?is_active=true
```

**Response:**
```json
{
  "data": [
    {
      "route_id": 1,
      "from_location": "Gurlan",
      "to_location": "Vazir",
      "distance_km": 45.5,
      "is_active": true,
      "active_drivers": 15,
      "pending_orders": 3
    }
  ]
}
```

### Create Route

```http
POST /routes
Content-Type: application/json

{
  "from_location": "Gurlan",
  "to_location": "Urgench",
  "distance_km": 35.0,
  "is_active": true
}
```

---

## ⚙️ System API

### System Settings

```http
GET /system/settings
```

**Response:**
```json
{
  "commission_amount": 500,
  "max_pickup_distance_km": 50,
  "auto_complete_trip_seconds": 600,
  "sms_rate_limit_per_day": 5
}
```

### Update Settings

```http
PUT /system/settings
Content-Type: application/json

{
  "commission_amount": 600
}
```

### Health Check

```http
GET /system/health
```

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "celery": "running",
  "uptime_seconds": 86400
}
```

---

## 📊 Response Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## 🔄 Rate Limiting

- **Default:** 100 requests/minute per IP
- **Auth endpoints:** 10 requests/minute
- **Admin panel:** 1000 requests/minute

---

## 📝 Changelog

### v1.0.0 (2026-01-20)
- Initial API release
- All CRUD endpoints
- Authentication
- Statistics

---

**Interactive Docs:** http://your-server:8000/docs  
**Redoc:** http://your-server:8000/redoc
