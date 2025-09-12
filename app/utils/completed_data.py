from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, List, Tuple
from app.curriculum.curriculum_models import Records
from app.utils.format_utils import build_semester_mapping
import re

async def get_completed_data(db: AsyncSession, user_id: int) -> Dict[str, Dict[str, List[Tuple]]]:
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
    for semester, code, name, credit, grade, lec_type in rows:
        if not re.match(r"^\d{4}-(1학기|2학기|여름학기|겨울학기)$", str(semester)):
            continue

        raw_completed_data.setdefault(semester, {}).setdefault(lec_type, []).append(
            (code, name, credit, grade)
        )

    all_semesters = set(raw_completed_data.keys())
    semester_mapping = build_semester_mapping(all_semesters)

    remapped_completed_data: Dict[str, Dict[str, List[Tuple]]] = {}
    for sem, types in raw_completed_data.items():
        grade, sem_num = semester_mapping.get(sem, ("?", "?"))
        new_key = f"{grade}학년 {sem_num}학기"
        remapped_completed_data[new_key] = types

    return remapped_completed_data