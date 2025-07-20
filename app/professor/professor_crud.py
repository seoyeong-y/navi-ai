from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.professor.professor_models import Professor
from app.lecture.lecture_models import Lectures
from typing import List, Optional


class ProfessorCrud:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 교수 ID로 강의 목록 조회
    async def get_lectures_by_professor_ids(self, professor_ids: List[int]) -> List[tuple]:
        stmt = select(Lectures).where(Lectures.professor_id.in_(professor_ids))
        result = await self.db.execute(stmt)
        lectures = result.scalars().all()

        return [(lec.name, lec.credits, lec.type, lec.grade, lec.semester,
                 '', '', lec.code, '') for lec in lectures]

    # ID로 교수 조회
    async def get_professor_by_id(self, professor_id: int) -> Optional[Professor]:
        return await self.db.get(Professor, professor_id)

    # 교수명으로 교수 조회
    async def get_professor_by_name(self, name: str) -> Optional[Professor]:
        stmt = select(Professor).where(Professor.name == name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()