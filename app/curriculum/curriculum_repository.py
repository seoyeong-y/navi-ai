from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.curriculum.curriculum_models import Curriculum, CurriLecture
from typing import List, Optional

class CurriculumCrud:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 사용자의 커리큘럼 이름 목록 조회
    async def get_curriculum_names_by_user(self, user_id: int) -> List[str]:
        stmt = select(Curriculum.name).where(Curriculum.user_id == user_id)
        result = await self.db.execute(stmt)
        return [row.name for row in result]

    # 커리큘럼 이름으로 ID 조회
    async def get_curriculum_id_by_name(self, user_id: int, name: str) -> Optional[int]:
        stmt = select(Curriculum.id).where(
            Curriculum.user_id == user_id,
            Curriculum.name == name
        )
        result = await self.db.execute(stmt)
        row = result.first()
        return row.id if row else None

    # ID로 커리큘럼 조회
    async def get_curriculum_by_id(self, curriculum_id: int) -> Optional[Curriculum]:
        return await self.db.get(Curriculum, curriculum_id)

    # ID로 커리큘럼 강의 조회
    async def get_curri_lecture_by_id(self, curri_lecture_id: int) -> Optional[CurriLecture]:
        return await self.db.get(CurriLecture, curri_lecture_id)