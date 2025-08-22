from typing import Tuple, Dict, List, Set
from app.utils.completed_data import completed_data
from app.core.constants import *
from app.recommendation.service.gpt_service import GPTService
from app.professor.professor_repository import ProfessorCrud
from sqlalchemy.ext.asyncio import AsyncSession

def calculate_credits(lecture_data: Dict) -> Tuple[int, int, int, int, int, Set[str]]:
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
                if lecture_type in ("전선", "전필"):
                    major_credits += credit
                elif lecture_type in ("교선", "교필"):
                    general_credits += credit
                if lecture_type == "전필":
                    major_required_credits_earned += credit
                if "현장실습" in name:
                    field_practice_credits += 1

    return (total_credits, major_credits, general_credits, field_practice_credits, major_required_credits_earned,
            completed_lecture_codes)

def check_graduation_requirements(
    total_credits: int,
    major_credits: int,
    general_credits: int,
    field_practice_credits: int,
    major_required_credits_earned: int
) -> None:
    print(f"총 학점: {total_credits} / {total_graduation_credits}")
    print(f"전공 학점: {major_credits} / {major_required_credits}")
    print(f"교양 학점: {general_credits} / {general_required_credits}")
    print(f"현장실습: {field_practice_credits} / {field_practice_required}")
    print(f"전공 필수 과목 학점: {major_required_credits_earned} / {major_required_lectures}")

    if total_credits >= total_graduation_credits:
        print("총 학점 요건 충족!")
    else:
        print(f"총 학점 부족! 부족 학점: {total_graduation_credits - total_credits}")

    if major_credits >= major_required_credits:
        print("전공 학점 요건 충족!")
    else:
        print(f"전공 학점 부족! 부족 학점: {major_required_credits - major_credits}")

    if general_credits >= general_required_credits:
        print("교양 학점 요건 충족!")
    else:
        print(f"교양 학점 부족! 부족 학점: {general_required_credits - general_credits}")

    if field_practice_credits >= field_practice_required:
        print("현장실습 요건 충족!")
    else:
        print(f"현장실습 부족! 부족 수: {field_practice_required - field_practice_credits}")

    if major_required_credits_earned >= major_required_lectures:
        print("전공 필수 과목 요건 충족!")
    else:
        print(f"전공 필수 과목 부족! 부족 과목 수: {major_required_lectures - major_required_credits_earned}")

def expand_with_missing_prerequisites(final_lectures, lecture_data, completed_names):
    expanded = set(final_lectures)
    for name, _, _, _, _, prereq, required_know, _, _, _ in lecture_data:
        if name not in final_lectures:
            continue
        for field in [prereq, required_know]:
            if not field:
                continue
            for item in [s.strip() for s in field.split(',') if s.strip()]:
                if item not in completed_names:
                    expanded.add(item)
    return list(expanded)

def filter_lecture_data(lecture_data, needed_names):
    return [
        (name, credit, lec_type, grade, semester, prereq, required_know, team_project, code, major)
        for name, credit, lec_type, grade, semester, prereq, required_know, team_project, code, major in lecture_data
        if name in needed_names
    ]

async def add_extra_lectures(
    curriculum,
    interest_keywords,
    available_lectures,
    needed_credits,
    types,
    used_names,
    student_grade,
    student_semester,
    conditions=None
):
    added = []

    interest_list = interest_keywords if isinstance(interest_keywords, list) else [interest_keywords]
    all_alt_lectures = set()
    for interest in interest_list:
        try:
            gpt_service = GPTService()
            alt = await gpt_service.suggest_other_similar_lectures(
                user_input=interest,
                deleted_lectures=available_lectures,
                interest=interest_list,
                available_lectures=available_lectures,
            )
            all_alt_lectures.update(alt)
        except Exception as e:
            print(f"[GPT 추천 실패 - fallback 사용] {e}")

    candidate_lectures = []
    used_set = set(used_names)

    use_preferred = False
    if conditions:
        use_preferred = ("professor" in conditions)
    preferred_prof_ids = set([prof["id"] for prof in preferred_professors]) if use_preferred else set()

    if all_alt_lectures:
        candidate_lectures = [
            l for l in available_lectures
            if l[0] in all_alt_lectures and l[2] in types and l[0] not in used_set and l[3] != '1'
        ]

    if not candidate_lectures and use_preferred:
        # 임시로 None 전달, 실제 사용 시 적절한 session 주입 필요
        professor_crud = ProfessorCrud(None)
        preferred_lectures = await professor_crud.get_lectures_by_professor_ids(list(preferred_prof_ids))
        candidate_lectures = [
            l for l in preferred_lectures
            if l[3] in types
               and l[1] not in used_set
               and l[4] != '1'
               and (
                       (str(l[5]) == "1" and str(l[8]) == "2025") or
                       (str(l[5]) == "2" and str(l[8]) == "2024")
               )
        ]

    if not candidate_lectures:
        candidate_lectures = [
            l for l in available_lectures
            if l[2] in types and l[0] not in used_set and l[3] != '1'
        ]

    for lec in candidate_lectures:
        name, credit, lec_type, grade, sem, *_ = lec

        if not credit or not grade or not sem:
            continue

        if int(grade) < student_grade or (int(grade) == student_grade and int(sem) < student_semester):
            continue

        semester_key = f"{grade}학년 {sem}학기"
        current_credits = sum(c for _, c, _ in curriculum.get(semester_key, []))

        if current_credits + credit > 21:
            continue

        curriculum.setdefault(semester_key, []).append((name, credit, lec_type))
        used_set.add(name)
        added.append((name, credit))
        needed_credits -= credit

        if needed_credits <= 0:
            break

    return added