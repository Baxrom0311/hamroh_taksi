from logging.config import fileConfig
import asyncio
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
import sys
from pathlib import Path

# ============================================
# IMPORT QO'SHISH
# ============================================

root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))

from config.settings import settings
from app.core.database import Base

# Barcha modellarni import qilish
from app.models.user import User
from app.models.driver import Driver
from app.models.passenger import Passenger
from app.models.route import Route
from app.models.order import Order
from app.models.transaction import Transaction, TransactionLog
from app.models.system_settings import SystemSettings
from app.models.driver_ban import DriverBanRecord
from app.models.feedback import Feedback
# ============================================
# ALEMBIC CONFIG
# ============================================

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# ============================================
# POSTGIS FILTER (MUHIM!)
# ============================================

def include_object(object, name, type_, reflected, compare_to):
    # WHITELIST STRATEGY: Faqat bizning modellar va alembic
    if type_ == "table":
        # 1. Bizning modellar
        if name in target_metadata.tables:
            return True
        
        # 2. Alembic versiyasi
        if name == "alembic_version":
            return True
            
        # 3. Boshqa barcha jadvallar (PostGIS, system tables) -> IGNORE
        # Ular bizning modelda yo'q, demak ularni o'chirishga urinma
        return False
            
    return True

# ============================================
# OFFLINE MODE
# ============================================

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,  # <--- SHU YERGA QO'SHILDI
    )

    with context.begin_transaction():
        context.run_migrations()

# ============================================
# ONLINE MODE
# ============================================

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        include_object=include_object,  # <--- SHU YERGA HAM QO'SHILDI
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section)
    if configuration is None:
        configuration = {}
    configuration["sqlalchemy.url"] = settings.database_url
    
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()