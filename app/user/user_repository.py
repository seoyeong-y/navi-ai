from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.user.user_models import UserProfile


class UserCrud:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_profile(self, userId: int) -> UserProfile:
        stmt = select(UserProfile).where(UserProfile.userId == userId)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()