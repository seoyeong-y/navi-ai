from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, List, Tuple, Any
from app.curriculum.curriculum_models import Records
from app.user.user_models import UserProfile
from app.utils.format_utils import build_semester_mapping
import re


def determine_status(grade: int, sem_in_grade: int, current_grade: int, current_sem: int,
                     has_record: bool, record_grade: str | None) -> str:
    try:
        sem = int(sem_in_grade)
    except (TypeError, ValueError):
        sem = current_sem

    if grade == current_grade and sem == current_sem and has_record:
        return "current"

    if (grade < current_grade or (grade == current_grade and sem < current_sem)) and not has_record:
        return "off-track"

    if has_record and record_grade in ("NP", "F"):
        return "off-track"

    if has_record:
        return "completed"

    return "planned"

async def get_completed_data(db: AsyncSession, user_id: int) -> Dict[str, Dict[str, List[Tuple]]]:
    profile = await db.get(UserProfile, user_id)
    current_grade = profile.grade if profile and profile.grade else 1
    current_sem = profile.semester if profile and profile.semester else 1
    enrollment_year = profile.enrollment_year if profile and profile.enrollment_year else current_grade

    result = await db.execute(
        select(
            Records.semester,
            Records.courseCode,
            Records.courseName,
            Records.credits,
            Records.grade,
            Records.type
        ).where(Records.userId == user_id)
    )
    rows = result.fetchall()

    raw_completed_data: Dict[str, Dict[str, List[Tuple]]] = {}

    # 입학년도 기반 학기 매핑
    all_semesters = {row[0] for row in rows if re.match(r"^\d{4}-(1학기|2학기|여름학기|겨울학기)$", str(row[0]))}
    semester_mapping = build_semester_mapping(all_semesters, enrollment_year)

    for semester, code, name, credit, record_grade, lec_type in rows:
        if semester not in semester_mapping:
            continue

        lec_grade, sem_num = semester_mapping[semester]

        status = determine_status(
            grade=int(lec_grade),
            sem_in_grade=int(sem_num),
            current_grade=current_grade,   # ← 실제 현재학기 반영
            current_sem=current_sem,
            has_record=True,
            record_grade=record_grade,
        )

        raw_completed_data.setdefault(semester, {}).setdefault(lec_type, []).append(
            (code, name, credit, record_grade, status)
        )

    remapped_completed_data: Dict[str, Dict[str, List[Tuple]]] = {}
    for sem, types in raw_completed_data.items():
        lec_grade, sem_num = semester_mapping.get(sem, ("?", "?"))
        new_key = f"{lec_grade}학년 {sem_num}학기"
        remapped_completed_data[new_key] = types

    return remapped_completed_data