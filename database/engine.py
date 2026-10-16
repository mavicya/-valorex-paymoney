from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from database.models import Base
from config import settings

# Railway віддає DATABASE_URL як postgresql:// — замінюємо на asyncpg-сумісний драйвер
_db_url = settings.DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Створює всі таблиці якщо вони ще не існують (dev/staging).
    На production використовуйте Alembic міграції."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
