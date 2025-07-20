from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.lecture.lecture_models import LectureCode, RecentLecture, LectureReplacement
from typing import List, Optional, Set


class LectureCrud:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 강의명으로 강의 정보 조회
    async def get_lecture_by_name(self, name: str) -> Optional[tuple]:
        stmt = select(RecentLecture).where(RecentLecture.name == name)
        result = await self.db.execute(stmt)
        lecture = result.scalar_one_or_none()

        if lecture:
            return (lecture.name, lecture.credits, lecture.type,
                    lecture.grade, lecture.semester, '', '', lecture.code, lecture.major)
        return None


    # 전체 강의 목록 조회
    async def get_lecture_list(self) -> List[tuple]:
        stmt = select(RecentLecture)
        result = await self.db.execute(stmt)
        lectures = result.scalars().all()

        return [(lec.name, lec.credits, lec.type, lec.grade, lec.semester,
                 '', '', '', lec.code, lec.major, '') for lec in lectures]


    # 강의 코드-ID 매핑 조회
    async def get_lecture_code_id_map(self) -> dict:
        stmt = select(LectureCode.code, LectureCode.id)
        result = await self.db.execute(stmt)
        return {row.code: row.id for row in result}


    # 대체 교과목 포함 완료 과목 코드 조회
    async def get_all_completed_codes_with_replacement(self, original_codes: Set[str]) -> Set[str]:
        all_codes = set(original_codes)

        for code in original_codes:
            stmt = select(LectureReplacement.replacement_code).where(
                LectureReplacement.original_code == code
            )
            result = await self.db.execute(stmt)
            replacements = [row.replacement_code for row in result]
            all_codes.update(replacements)

            stmt = select(LectureReplacement.original_code).where(
                LectureReplacement.replacement_code == code
            )
            result = await self.db.execute(stmt)
            originals = [row.original_code for row in result]
            all_codes.update(originals)

        return all_codes


    # 미이수 필수 과목 조회
    async def get_uncompleted_required_lectures(self, completed_codes: Set[str], student_grade: int) -> tuple:
        uncompleted_mr = []
        uncompleted_gr = []

        # MR, GR 타입의 강의만 조회
        stmt = select(RecentLecture).where(
            RecentLecture.type.in_(['MR', 'GR']),
            RecentLecture.code.notin_(completed_codes),
            RecentLecture.grade <= str(student_grade)
        )
        result = await self.db.execute(stmt)
        lectures = result.scalars().all()

        for lecture in lectures:
            if lecture.type == 'MR':
                uncompleted_mr.append(lecture.name)
            else:
                uncompleted_gr.append(lecture.name)

        return uncompleted_mr, uncompleted_gr