from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.curriculum.curriculum_models import Curriculum, CurriLecture
from typing import List, Optional
from app.lecture.lecture_models import LectureCode


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

    # 커리큘럼 저장
    async def save_curriculum(self, user_id: int, name: str, total_credits: int, description: str = "") -> int:
        curriculum = Curriculum(
            user_id=user_id,
            name=name,
            created_at=datetime.now(),
            total_credits=total_credits,
            description=description
        )
        self.db.add(curriculum)
        await self.db.commit()
        await self.db.refresh(curriculum)
        return curriculum.id

    # 커리큘럼 강의 저장
    async def save_curri_lectures(self, curri_id: int, lectures: list):
        # 강의 코드 매핑 조회
        lecture_codes = [lec[7] for lec in lectures if len(lec) > 7 and lec[7]]
        stmt = select(LectureCode.code, LectureCode.id).where(LectureCode.code.in_(lecture_codes))
        result = await self.db.execute(stmt)
        code_id_map = {row.code: row.id for row in result}

        curri_lectures = []
        for (name, credit, lec_type, grade, semester, _, _, code, _) in lectures:
            if code in code_id_map:
                curri_lecture = CurriLecture(
                    curri_id=curri_id,
                    lect_id=code_id_map[code],
                    name=name,
                    credits=credit,
                    semester=semester,
                    type=lec_type,
                    grade=grade
                )
                curri_lectures.append(curri_lecture)

        self.db.add_all(curri_lectures)
        await self.db.commit()

    # 커리큘럼 이름으로 삭제
    async def delete_curriculum_by_name(self, user_id: int, curriculum_name: str) -> bool:
        stmt = select(Curriculum).where(
            Curriculum.user_id == user_id,
            Curriculum.name == curriculum_name
        )
        result = await self.db.execute(stmt)
        curriculum = result.scalar_one_or_none()

        if not curriculum:
            return False

        # 관련 강의들 먼저 삭제
        delete_lectures_stmt = delete(CurriLecture).where(CurriLecture.curri_id == curriculum.id)
        await self.db.execute(delete_lectures_stmt)

        # 커리큘럼 삭제
        await self.db.delete(curriculum)
        await self.db.commit()
        return True