from typing import Dict, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.completed_data import completed_data
from app.curriculum.curriculum_repository import CurriculumCrud


class CurriculumService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.curriculum_repo = CurriculumCrud(db)

    # 학점 계산 함수
    def calculate_credits(self, lecture_data: Dict = None) -> Tuple[int, int, int, int, int, Set[str]]:
        if lecture_data is None:
            lecture_data = completed_data

        total_credits = 0
        major_credits = 0
        general_credits = 0
        field_practice_credits = 0
        major_required_credits_earned = 0
        completed_lecture_codes = set()

        for semester, lectures in lecture_data.items():
            for lecture_type, lectures_list in lectures.items():
                for code, name, credit, _ in lectures_list:
                    total_credits += credit
                    completed_lecture_codes.add(code)
                    if lecture_type in ("전선", "전필", "ME", "MR"):
                        major_credits += credit
                    elif lecture_type in ("교선", "교필", "GE", "GR"):
                        general_credits += credit
                    if lecture_type in ("전필", "MR"):
                        major_required_credits_earned += credit
                    if "현장실습" in name:
                        field_practice_credits += 1

        return (total_credits, major_credits, general_credits, field_practice_credits,
                major_required_credits_earned, completed_lecture_codes)

    # 커리큘럼 이름 생성 함수
    async def generate_curriculum_name(self, user_id: int) -> str:
        existing_names = await self.curriculum_repo.get_curriculum_names_by_user(user_id)
        existing_names_set = set(existing_names)

        # 커리큘럼 숫자 중 가장 작은 빈 번호 찾기
        i = 1
        while True:
            candidate = f"커리큘럼 {i}"
            if candidate not in existing_names_set:
                return candidate
            i += 1