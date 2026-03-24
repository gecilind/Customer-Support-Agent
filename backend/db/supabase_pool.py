from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config import get_settings


settings = get_settings()
engine = create_async_engine(
    settings.supabase_db_url,
    pool_pre_ping=True,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_engine() -> AsyncEngine:
    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_session_factory
