from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.professor.professor_models import PreferredProfessor, Professor
from typing import List, Dict

total_graduation_credits = 140
major_required_credits = 75
general_required_credits = 42
field_practice_required = 1
major_required_lectures = 33
general_required_lectures = 13

GRADE_POINT = {
    'A+': 4.5, 'A0': 4.0,
    'B+': 3.5, 'B0': 3.0,
    'C+': 2.5, 'C0': 2.0,
    'D+': 1.5, 'D0': 1.0,
    'F': 0
}

CONDITION_CODES = {
    'graduation': 'G',
    'no_team_project': 'T',
    'preferred_professor': 'P',
    'retake': 'R'
}

CONDITION_NAMES = {
    'G': '졸업',
    'T': '팀플 제외',
    'P': '선호 교수',
    'R': '재수강 포함'
}

async def get_preferred_professors(db: AsyncSession, user_id: int) -> List[Dict]:
    result = await db.execute(
        select(
            PreferredProfessor.id,
            Professor.id,
            Professor.name
        )
        .join(Professor, PreferredProfessor.professor_id == Professor.id)
        .where(PreferredProfessor.user_id == user_id)
    )
    rows = result.fetchall()

    return [
        {
            "preferred_id": pref_id,
            "professor_id": prof_id,
            "name": name
        }
        for pref_id, prof_id, name in rows
    ]