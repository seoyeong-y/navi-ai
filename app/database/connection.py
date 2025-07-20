from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

# 비동기 엔진 생성
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG
)

# 비동기 세션 팩토리
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    async with async_engine.begin() as conn:
        pass

async def close_db():
    await async_engine.dispose()