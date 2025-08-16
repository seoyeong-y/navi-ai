from sqlalchemy.ext.asyncio import AsyncSession
from app.curriculum.service.curriculum_utils import expand_with_missing_prerequisites, filter_lecture_data
from app.curriculum.service.curriculum_builder import CurriculumBuilder
from app.lecture.lecture_service import LectureService
from app.core.constants import *


class CurriculumFinalBuilder:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.lecture_service = LectureService(db)
        self.curriculum_builder = CurriculumBuilder(db)


async def build_final_curriculum(
        completed_data,
        completed_codes,
        completed_names,
        lecture_list,
        major_recommendations,
        general_recommendations,
        student_grade,
        student_semester,
        major_interest,
        general_interest,
        conditions=None,
        retake_codes=None,
        db: AsyncSession = None
):
    final_builder = CurriculumFinalBuilder(db) if db else None

    uncompleted_mr, uncompleted_gr = get_uncompleted_required_lectures(
        completed_codes,
        lecture_list,
        student_grade
    )

    base_final_majors = list(set(major_recommendations + uncompleted_mr))
    expanded_major = expand_with_missing_prerequisites(
        base_final_majors,
        lecture_list,
        completed_names
    )

    print("general: ", general_recommendations)
    all_needed_names = set(expanded_major + general_recommendations + uncompleted_gr)

    filtered_lecture_list = filter_lecture_data(
        lecture_list,
        all_needed_names
    )

    print(f">>> 설계에 포함될 강의 수: {len(filtered_lecture_list)}")
    print(f">>> 설계에 포함될 강의 목록: {filtered_lecture_list}")

    curriculum, total_credits, filtered_lecture_list = await final_builder.curriculum_builder.build_curriculum(
        completed_data=completed_data,
        completed_codes=completed_codes,
        completed_names=completed_names,
        lectures=filtered_lecture_list,
        full_lectures=lecture_list,
        general_recommendations=general_recommendations,
        final_recommendations=all_needed_names,
        student_grade=student_grade,
        student_semester=student_semester,
        required_major_names=uncompleted_mr,
        required_general_names=uncompleted_gr,
        major_interest=major_interest,
        general_interest=general_interest,
        total_required_credits=total_graduation_credits,
        lecture_list=lecture_list,
        conditions=conditions,
        retake_codes=retake_codes
    )

    return curriculum, total_credits, filtered_lecture_list


def get_uncompleted_required_lectures(completed_codes, lecture_list, student_grade):
    uncompleted_mr = []
    uncompleted_gr = []

    for lecture in lecture_list:
        name, credit, lec_type, grade, semester, prereq, required_know, team_project, code, major, _ = lecture

        if code in completed_codes:
            continue

        if int(grade) > student_grade:
            continue

        if lec_type == 'MR':
            uncompleted_mr.append(name)
        elif lec_type == 'GR':
            uncompleted_gr.append(name)

    return uncompleted_mr, uncompleted_gr