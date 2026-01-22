"""
app/admin/main.py

ADMIN PANEL - FastAPI Application

BU NIMA:
- Web-based admin panel
- Driver/Passenger management
- Transaction approval
- Statistics dashboard

ISHLATISH:
    uvicorn app.admin.main:app --host 0.0.0.0 --port 8000
"""
from app.core.database import get_session
from sqlalchemy.orm import selectinload # SHUNI QO'SHING

from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from loguru import logger
import httpx

from config.settings import settings
from app.admin.auth import get_current_user, create_access_token, router as auth_router
from app.models.driver import Driver
from app.models.passenger import Passenger
from app.models.transaction import Transaction, TransactionStatus
from sqlalchemy import select
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.metrics import API_RESPONSE_TIME
# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="Hamroh Admin Panel",
    description="Taxi bot admin panel",
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None
)


# ============================================
# MIDDLEWARE
# ============================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else ["https://admin.hamroh.uz"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# IP Whitelist Middleware
@app.middleware("http")
async def ip_whitelist_middleware(request: Request, call_next):
    """
    IP whitelist tekshiruvi
    
    Production'da faqat ruxsat berilgan IP'lardan
    """
    # Development'da skip
    if settings.is_development:
        return await call_next(request)
    
    # Health check skip
    if request.url.path in ["/health", "/api/auth/login"]:
        return await call_next(request)
    
    # Whitelist
    allowed_ips = settings.admin_allowed_ips_list
    
    if not allowed_ips:
        # Whitelist bo'sh - barchaga ruxsat
        return await call_next(request)
    
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    
    if client_ip not in allowed_ips:
        logger.warning(f"Access denied from IP: {client_ip}")
        return JSONResponse(
            status_code=403,
            content={"detail": f"Access denied from IP: {client_ip}"}
        )
    
    return await call_next(request)


# Request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Request logging"""
    start_time = datetime.now()
    
    response = await call_next(request)
    
    duration = (datetime.now() - start_time).total_seconds()
    try:
        API_RESPONSE_TIME.labels(
            endpoint=request.url.path,
            method=request.method
        ).observe(duration)
    except Exception as metrics_err:
        logger.debug(f"Metrics observe failed: {metrics_err}")
    
    logger.info(
        f"{request.method} {request.url.path} - "
        f"{response.status_code} - {duration:.3f}s"
    )
    
    return response


# ============================================
# TEMPLATES
# ============================================

templates = Jinja2Templates(directory="app/admin/templates")


# ============================================
# ROUTES
# ============================================

# Auth routes
app.include_router(auth_router)


# Dashboard routes
from app.admin.routes import dashboard, drivers, passengers, transactions
from app.admin.routes import settings as settings_routes
from app.admin.routes import admins, broadcast, feedback as feedback_api

app.include_router(dashboard.router, prefix="/api")
app.include_router(drivers.router, prefix="/api")
app.include_router(passengers.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(settings_routes.router, prefix="/api")
app.include_router(admins.router, prefix="/api")
app.include_router(broadcast.router, prefix="/api")
app.include_router(feedback_api.router, prefix="/api")


# ============================================
# MAIN ROUTES
# ============================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

@app.get("/admins", response_class=HTMLResponse)
async def admins_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Adminlar sahifasi
    """
    return templates.TemplateResponse(
        "admins.html",
        {
            "request": request,
            "user": current_user,
            "page": "admins",
            "now": datetime.now()
        }
    )

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Sozlamalar sahifasi
    """
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": current_user,
            "page": "settings",
            "now": datetime.now()
        }
    )

@app.get("/system-settings", response_class=HTMLResponse)
async def system_settings_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    System settings page (free/pullik, komissiya va boshqalar) - Legacy route
    """
    return RedirectResponse(url="/settings", status_code=301)

@app.get("/routes", response_class=HTMLResponse)
async def routes_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Marshrut/hududlar sahifasi
    """
    return templates.TemplateResponse(
        "routes.html",
        {
            "request": request,
            "user": current_user,
            "page": "routes",
            "now": datetime.now()
        }
    )


# ============================================
# METRICS ENDPOINT (PROMETHEUS SCRAPE)
# ============================================

@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus scraping endpoint for Grafana dashboards.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Xabar yuborish sahifasi (Faqat Glavni Admin)
    """
    if current_user.get('role') != 'glavni_admin':
        raise HTTPException(
            status_code=403,
            detail="Bu sahifa faqat Glavni Admin uchun"
        )
    
    return templates.TemplateResponse(
        "broadcast.html",
        {
            "request": request,
            "user": current_user,
            "page": "broadcast",
            "now": datetime.now()
        }
    )

@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:8000/api/auth/login",
            json={
                "username": username,
                "password": password
            }
        )

    if resp.status_code != 200:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Login yoki parol noto‘g‘ri"
            }
        )

    data = resp.json()
    token = data["access_token"]

    is_secure = request.url.scheme == "https"
    
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=is_secure, # Avtomatik aniqlash
        samesite="lax",
        path="/" # MUHIM: Har doim path="/" bo'lishi kerak
    )
    return response



@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Root redirect to dashboard
    """
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Dashboard page
    """
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "page": "dashboard"
        }
    )

@app.get("/drivers", response_class=HTMLResponse)
async def drivers_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    from app.models.driver import Driver
    
    async with get_session() as session:
        # 1. Haydovchilarni User ma'lumotlari bilan birga yuklaymiz
        stmt = select(Driver).options(selectinload(Driver.user)).order_by(Driver.created_at.desc())
        result = await session.execute(stmt)
        drivers_list = result.scalars().all()
        
        # 2. SENIOR TRICK: Ma'lumotlarni lug'atga o'tkazamiz (Session yopilishidan oldin!)
        # Bu orqali Jinja2 bazaga qayta murojaat qila olmaydi va xato yo'qoladi.
        formatted_drivers = []
        for d in drivers_list:
            formatted_drivers.append({
                "driver_id": d.driver_id,  # ID qo'shildi
                "full_name": d.full_name,
                "phone_number": d.user.phone_number if d.user else "Tel yo'q",
                "car_model": d.car_model,
                "car_color": d.car_color,
                "car_number": d.car_number,
                "balance": float(d.balance),
                "rating": float(d.rating),
                "is_active": d.is_active,
                "is_blocked": d.is_blocked
            })
            
        logger.info(f"Drivers found and formatted: {len(formatted_drivers)}")

    return templates.TemplateResponse(
        "drivers.html",
        {
            "request": request,
            "user": current_user,
            "drivers": formatted_drivers, # Endi lug'at yuboramiz
            "page": "drivers",
            "now": datetime.now()
        }
    )


@app.get("/passengers", response_class=HTMLResponse)
async def passengers_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    from app.models.passenger import Passenger
    async with get_session() as session:
        result = await session.execute(
            select(Passenger).options(selectinload(Passenger.user)).order_by(Passenger.created_at.desc())
        )
        passengers_list = result.scalars().all()

        formatted_passengers = []
        for p in passengers_list:
            gender_value = p.gender.value if hasattr(p.gender, "value") else p.gender
            formatted_passengers.append({
                "passenger_id": p.passenger_id,  # ID qo'shildi
                "full_name": p.full_name,
                "phone_number": p.user.phone_number if p.user else "Noma'lum",
                "gender": "Erkak" if str(gender_value).upper() == "MALE" else "Ayol",
                "age": p.age,
                "total_trips": p.total_trips,
                "is_blocked": p.user.is_blocked if p.user else False,
                "created_at": p.created_at.strftime("%d.%m.%Y")
            })

    return templates.TemplateResponse(
        "passengers.html",
        {
            "request": request,
            "user": current_user,
            "passengers": formatted_passengers,
            "page": "passengers",
            "now": datetime.now()
        }
    )


@app.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    from app.models.transaction import Transaction, TransactionStatus
    async with get_session() as session:
        # Faqat kutilayotgan (PENDING) to'lovlarni yoki hammasini chiqarish mumkin
        result = await session.execute(
            select(Transaction).options(selectinload(Transaction.driver))
            .order_by(Transaction.created_at.desc())
        )
        tx_list = result.scalars().all()
        
        formatted_tx = []
        for tx in tx_list:
            formatted_tx.append({
                "id": tx.transaction_id,
                "driver_name": tx.driver.full_name if tx.driver else "Noma'lum",
                "amount": float(tx.amount),
                "type": tx.type.value,
                "status": tx.status.value,
                "receipt_url": tx.receipt_file_id, # Telegram file_id
                "created_at": tx.created_at.strftime("%H:%M / %d.%m.%Y")
            })
        
        # BOT_TOKEN ni template'ga uzatish
        from config.settings import settings

    return templates.TemplateResponse(
        "transactions.html",
        {
            "request": request,
            "user": current_user,
            "transactions": formatted_tx,
            "page": "transactions",
            "now": datetime.now(),
            "settings": settings  # BOT_TOKEN uchun
        }
    )


# ============================================
# FEEDBACK PAGE
# ============================================

@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    from app.models.feedback import Feedback, FeedbackStatus
    from sqlalchemy.orm import selectinload
    from sqlalchemy import desc, func
    
    async with get_session() as session:
        # All feedbacks
        stmt = (
            select(Feedback)
            .options(selectinload(Feedback.user))
            .order_by(desc(Feedback.created_at))
        )
        result = await session.execute(stmt)
        all_feedbacks_db = result.scalars().all()
        
        # Format data
        all_feedbacks = []
        open_feedbacks = []
        
        open_count = 0
        resolved_count = 0
        today_start = datetime.now().replace(hour=0, minute=0, second=0)
        today_count = 0
        
        for fb in all_feedbacks_db:
            
            fb_dict = {
                "id": fb.feedback_id,
                "user_name": fb.user.full_name if fb.user else "Noma'lum",
                "user_phone": fb.user.phone_number if fb.user else "N/A",
                "user_role": fb.user.role.value if fb.user else "unknown",
                "message": fb.message,
                "type": fb.type.value,
                "status": fb.status.value,
                "admin_reply": fb.admin_reply,
                "resolved_by": fb.resolved_by,
                "created_at": fb.created_at.strftime("%H:%M / %d.%m.%Y"),
                "raw_date": fb.created_at.isoformat() if fb.created_at else None
            }
            
            all_feedbacks.append(fb_dict)
            
            if fb.status == FeedbackStatus.OPEN:
                open_feedbacks.append(fb_dict)
                open_count += 1
            elif fb.status == FeedbackStatus.RESOLVED:
                resolved_count += 1
                
            # Timezone comparison fix
            fb_date = fb.created_at
            if fb_date.tzinfo:
                fb_date = fb_date.replace(tzinfo=None)
                
            if fb_date >= today_start:
                today_count += 1

    return templates.TemplateResponse(
        "feedback.html",
        {
            "request": request,
            "user": current_user,
            "all_feedbacks": all_feedbacks,
            "open_feedbacks": open_feedbacks,
            "open_count": open_count,
            "resolved_count": resolved_count,
            "today_count": today_count,
            "page": "feedback",
            "now": datetime.now()
        }
    )


# ============================================
# HEALTH CHECK
# ============================================

@app.get("/health")
async def health_check():
    """
    System health check
    """
    try:
        from app.core.database import check_database_health
        from app.core.redis_client import redis_client
        
        # Database
        db_health = await check_database_health()
        
        # Redis
        redis_health = await redis_client.ping()
        
        # Celery
        from app.core.celery_app import get_celery_stats
        celery_stats = get_celery_stats()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": db_health['status'],
                "redis": "ok" if redis_health else "error",
                "celery": "ok" if celery_stats['worker_count'] > 0 else "error"
            },
            "celery": celery_stats
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


# ============================================
# PERFORMANCE METRICS
# ============================================

@app.get("/api/metrics/stats")
async def get_metrics_stats(
    current_user: dict = Depends(get_current_user)
):
    """
    Performance metrics
    
    Returns:
        {
            'api_calls': {...},
            'memory': {...}
        }
    """
    from app.utils.metrics import api_metrics, get_memory_usage
    
    stats = api_metrics.get_stats()
    memory = get_memory_usage()
    
    return {
        'success': True,
        'metrics': {
            'api_calls': stats,
            'memory': {
                'rss_mb': round(memory['rss'] / 1024 / 1024, 2),
                'vms_mb': round(memory['vms'] / 1024 / 1024, 2),
                'percent': round(memory['percent'], 2)
            }
        }
    }



# ============================================
# ERROR HANDLERS
# ============================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP exception handler"""
    
    # Agar 401 bo'lsa va API bo'lmasa -> Loginga redirect
    if exc.status_code == 401:
        # API requestmi?
        if request.url.path.startswith("/api"):
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.detail}
            )
        
        # HTML Page -> Redirect to login
        return RedirectResponse(
            url="/login",
            status_code=302
        )
            
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.is_development else None
        }
    )


# ============================================
# STARTUP / SHUTDOWN
# ============================================

@app.on_event("startup")
async def startup():
    """Application startup"""
    logger.info("🚀 Admin panel starting...")
    
    # Database
    from app.core.database import init_database
    await init_database()
    
    # Redis
    from app.core.redis_client import init_redis
    await init_redis()
    
    logger.success("✅ Admin panel started!")


@app.on_event("shutdown")
async def shutdown():
    """Application shutdown"""
    logger.info("🔄 Admin panel shutting down...")
    
    # Database
    from app.core.database import close_database
    await close_database()
    
    # Redis
    from app.core.redis_client import close_redis
    await close_redis()
    
    logger.info("✅ Admin panel stopped!")


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.admin.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level="info"
    )
