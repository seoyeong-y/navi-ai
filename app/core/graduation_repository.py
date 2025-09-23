from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.user.user_models import UserProfile
from app.core.graduation_models import GraduationRequirement

class GraduationRequirementCrud:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_requirement_by_student_id(self, student_id: str) -> GraduationRequirement:
        # student_id 앞 4자리 추출
        entry_year = int(student_id[:4])

        stmt = (
            select(GraduationRequirement)
            .where(
                GraduationRequirement.entry_year_start <= entry_year,
                (GraduationRequirement.entry_year_end.is_(None)) | (GraduationRequirement.entry_year_end >= entry_year)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
