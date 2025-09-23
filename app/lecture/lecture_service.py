from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.lecture.lecture_repository import LectureCrud
from app.lecture.lecture_models import RecentLecture, LectureCode
from typing import List


class LectureService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.lecture_crud = LectureCrud(db)

    async def fetch_all_lectures(self, student_grade: int = 1):
        stmt = select(RecentLecture.name).where(
            RecentLecture.type.in_(['ME', 'MR'])
        )

        if student_grade >= 2:
            stmt = stmt.where(RecentLecture.grade != '1')

        stmt = stmt.group_by(RecentLecture.name)

        try:
            result = await self.db.execute(stmt)
            return [row.name.strip() for row in result]
        except Exception as e:
            print(f"[강의 목록 조회 오류] {e}")
            return []

    async def fetch_major_lectures(self, student_grade: int = 1):
        stmt = select(RecentLecture.name).where(
            RecentLecture.type == 'ME',
            RecentLecture.major != 'LA'
        )

        if student_grade >= 2:
            stmt = stmt.where(RecentLecture.grade != '1')

        stmt = stmt.group_by(RecentLecture.name)

        try:
            result = await self.db.execute(stmt)
            return [row.name.strip() for row in result]
        except Exception as e:
            print(f"[전공 강의 조회 오류] {e}")
            return []

    async def fetch_general_lectures(self, student_grade: int = 1):
        stmt = select(RecentLecture.name).where(
            RecentLecture.type == 'GE',
            RecentLecture.major == 'LA',
        )

        if student_grade >= 2:
            stmt = stmt.where(RecentLecture.grade != '1')

        stmt = stmt.group_by(RecentLecture.name)

        try:
            result = await self.db.execute(stmt)
            return [row.name.strip() for row in result]
        except Exception as e:
            print(f"[교양 강의 조회 오류] {e}")
            return []

    async def fetch_lecture_infos_for_recommendation(self):
        from sqlalchemy import join

        stmt = select(
            RecentLecture.name,
            LectureCode.lecture_description,
            LectureCode.lecture_objectives
        ).select_from(
            join(RecentLecture, LectureCode, RecentLecture.code == LectureCode.code)
        ).where(
            LectureCode.lecture_description.isnot(None),
            LectureCode.lecture_objectives.isnot(None)
        )

        try:
            result = await self.db.execute(stmt)
            return [(row.name, row.lecture_description, row.lecture_objectives) for row in result]
        except Exception as e:
            print(f"[강의 정보 조회 오류] {e}")
            return []

    async def add_replacement_codes(self, completed_codes: set):
        if not completed_codes:
            return set()

        from app.lecture.lecture_models import LectureReplacement

        stmt = select(
            LectureReplacement.original_code,
            LectureReplacement.replacement_code
        ).where(
            LectureReplacement.original_code.in_(completed_codes) |
            LectureReplacement.replacement_code.in_(completed_codes)
        )

        try:
            result = await self.db.execute(stmt)
            replacement = set(completed_codes)

            for original, replacement_code in result:
                if original in completed_codes:
                    replacement.add(replacement_code)
                if replacement_code in completed_codes:
                    replacement.add(original)

            return replacement
        except Exception as e:
            print(f"[대체 교과목 조회 오류] {e}")
            return completed_codes