from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.curriculum.curriculum_models import Records
from app.lecture.lecture_models import LectureReplacement, RecentLecture
from typing import List, Dict


class RetakeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_retake_eligible_courses(self, user_id: int) -> List[Dict]:
        retake_eligible_grades = {'C+', 'C0', 'C', 'D+', 'D0', 'D', 'F', 'NP'}
        completed_grades = {'B+', 'B0', 'A+', 'A0', 'A'}

        try:
            stmt = select(Records).where(Records.userId == user_id)
            result = await self.db.execute(stmt)
            records = result.scalars().all()

            retake_candidates = []
            seen_codes = set()

            for record in records:
                code = record.courseCode

                if code in seen_codes:
                    continue

                same_code_records = [r for r in records if r.courseCode == code]

                if any(r.grade in completed_grades for r in same_code_records):
                    seen_codes.add(code)
                    continue

                if any(r.grade in retake_eligible_grades for r in same_code_records):
                    retake_candidates.append({
                        "code": code,
                        "name": record.courseName,
                        "credit": record.credits,
                        "grade": record.grade,
                        "semester": record.semester,
                        "type": record.type
                    })

                seen_codes.add(code)

            return retake_candidates

        except Exception as e:
            print(f"[RetakeService] 재수강 가능 과목 조회 실패: {e}")
            return []

    async def check_retake_eligibility(self, user_id: int, course_code: str) -> bool:
        """
        특정 과목이 재수강 가능한지 확인
        """
        retake_eligible_grades = {'C+', 'C0', 'C', 'D+', 'D0', 'D', 'F', 'NP'}

        try:
            stmt = select(Records).where(
                Records.userId == user_id,
                Records.courseCode == course_code,
                Records.grade.in_(retake_eligible_grades)
            )

            result = await self.db.execute(stmt)
            record = result.scalars().first()

            return record is not None

        except Exception as e:
            print(f"[RetakeService] 재수강 가능 여부 확인 실패: {e}")
            return False

    async def resolve_final_code(self, course_code: str) -> str | None:
        """
        주어진 course_code가 대체 교과목으로 이어져 있는 경우,
        최종적으로 RecentLecture에 존재하는 코드 반환
        """
        visited = set()
        current_code = course_code

        while current_code and current_code not in visited:
            visited.add(current_code)

            stmt = select(RecentLecture.code).where(RecentLecture.code == current_code)
            result = await self.db.execute(stmt)
            codes = list(set(result.scalars().all()))

            if codes:
                unique_codes = list(set(codes))
                return unique_codes[0]

            stmt = select(LectureReplacement.replacement_code).where(
                LectureReplacement.original_code == current_code
            )
            result = await self.db.execute(stmt)
            replacement_code = result.scalar_one_or_none()

            if not replacement_code:
                return None

            current_code = replacement_code

        return None