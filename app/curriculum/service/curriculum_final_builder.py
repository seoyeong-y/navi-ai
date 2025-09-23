from app.core.graduation_repository import GraduationRequirementCrud
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
        student_id: str,
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

    grad_crud = GraduationRequirementCrud(db)
    requirement = await grad_crud.get_requirement_by_student_id(student_id)

    print(">>> 졸업 요건 조회 완료")
    print(f"총 이수 학점 요건: {requirement.total_credits}")
    print(f"전공 학점 요건: {requirement.major}")
    print(f"교양 학점 요건: {requirement.liberal_arts}")

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
        total_required_credits=requirement.total_credits,
        major_required_credits=requirement.major,
        general_required_credits=requirement.liberal_arts,
        lecture_list=lecture_list,
        conditions=conditions,
        retake_codes=retake_codes
    )

    return curriculum, total_credits, filtered_lecture_list


def get_uncompleted_required_lectures(completed_codes, lecture_list, student_grade):
    uncompleted_mr = []
    uncompleted_gr = []

    print(f">>> get_uncompleted_required_lectures 시작")
    print(f">>> lecture_list 길이: {len(lecture_list)}")

    for i, lecture in enumerate(lecture_list):
        try:
            # 디버깅: 각 lecture의 길이 확인
            if len(lecture) != 10:
                print(f">>> [경고] lecture[{i}] 길이가 {len(lecture)}개: {lecture}")
                continue

            name, credit, lec_type, grade, semester, prereq, required_know, team_project, code, major = lecture

            if code in completed_codes:
                continue

            if int(grade) > student_grade:
                continue

            if lec_type == 'MR':
                uncompleted_mr.append(name)
            elif lec_type == 'GR':
                uncompleted_gr.append(name)

        except ValueError as e:
            print(f">>> [에러] lecture[{i}] 언패킹 실패: {e}")
            print(f">>> lecture[{i}] 내용: {lecture}")
            print(f">>> lecture[{i}] 길이: {len(lecture)}")
            raise e

    return uncompleted_mr, uncompleted_gr