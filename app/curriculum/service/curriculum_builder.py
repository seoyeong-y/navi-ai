import re
from collections import defaultdict
from typing import Tuple, Dict, List
from app.core.constants import *
from app.lecture.lecture_repository import LectureCrud
from app.professor.professor_repository import ProfessorCrud
from app.utils.format_utils import format_curriculum, normalize_semester
from app.curriculum.service.curriculum_utils import add_extra_lectures


class CurriculumBuilder:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.lecture_crud = LectureCrud(db)
        self.professor_crud = ProfessorCrud(db)

    async def build_curriculum(
            self,
            completed_data: dict,
            completed_codes: set,
            completed_names: set,
            lectures: list,
            full_lectures: list,
            final_recommendations: list,
            general_recommendations: list,
            student_grade: int,
            student_semester: int,
            required_major_names: list,
            required_general_names: list,
            major_interest: list,
            general_interest: list,
            total_required_credits: int,
            lecture_list: list,
            conditions: dict = None,
            retake_codes: list = None
    ) -> Tuple[Dict[str, List[Tuple[str, int, str]]], int, List[Tuple]]:

        conditions = conditions or []

        graduation_mode = "graduation" in conditions
        no_team_project_mode = "no_team_project" in conditions
        preferred_professor_mode = "professor" in conditions
        retake_mode = "retake" in conditions

        def log_curriculum_snapshot(curriculum):
            print(format_curriculum(curriculum, {}))

        def log_total_credits(curriculum):
            all_lectures = sum(curriculum.values(), [])
            major = sum(c for _, c, t in all_lectures if t in ("MR", "ME"))
            general = sum(c for _, c, t in all_lectures if t in ("GR", "GE"))
            total = major + general
            print(f"누적 학점: 총 {total}, 전공 {major}, 교양 {general}")

        def sort_key(semester_str):
            match = re.match(r"(\d+)학년 (\d)학기", semester_str)
            if match:
                return int(match.group(1)), int(match.group(2))
            return 999, 999

        def assign_with_prerequisites(lec, lec_year, lec_semester, lec_sem_key, parent_stack=None):
            nonlocal total_credits
            name_local, credit_local, type_local, grade_local, sem_local, prereq_local, _, _, code_local, _ = lec

            if parent_stack is None:
                parent_stack = set()
            if name_local in parent_stack:
                return False

            if code_local in assigned_codes or name_local in assigned_names:
                return True

            if semester_credit_map[lec_sem_key] + credit_local > 21:
                return False

            if prereq_local:
                required_list = [p.strip() for p in prereq_local.split(',') if p.strip()]
                latest_year, latest_semester = 0, 0

                for req_name in required_list:
                    if req_name in assigned_names:
                        prereq_lec = next((l for l in lectures if l[0] == req_name), None)
                        if prereq_lec:
                            prereq_year = int(prereq_lec[3])
                            prereq_sem = int(prereq_lec[4]) if prereq_lec[4] in ("1", "2") else 1
                            if (prereq_year, prereq_sem) > (latest_year, latest_semester):
                                latest_year, latest_semester = prereq_year, prereq_sem
                        continue

                    prereq_lec = next((l for l in lectures if l[0] == req_name), None)
                    if prereq_lec:
                        prereq_year = int(prereq_lec[3])
                        prereq_semester = int(prereq_lec[4]) if prereq_lec[4] in ("1", "2") else 1

                        prereq_sem_key = f"{prereq_year}학년 {prereq_semester}학기"
                        success_local = assign_with_prerequisites(
                            prereq_lec, prereq_year, prereq_semester, prereq_sem_key, parent_stack
                        )

                        if success_local:
                            if (prereq_year, prereq_semester) > (latest_year, latest_semester):
                                latest_year, latest_semester = prereq_year, prereq_semester
                        else:
                            print(f"[선수 과목 실패 스킵] {req_name}")
                            continue
                    else:
                        continue

                if (lec_year, lec_semester) <= (latest_year, latest_semester):
                    return False

            curriculum.setdefault(lec_sem_key, [])
            curriculum[lec_sem_key].append((name_local, credit_local, type_local))

            assigned_names.add(name_local)
            used_names.add(name_local)
            assigned_codes.add(code_local)
            semester_credit_map[lec_sem_key] += credit_local
            total_credits += credit_local
            return True

        curriculum = {}
        total_credits = 0
        current_semester_index = 1
        max_semester_limit = 18
        if graduation_mode:
            max_semester_limit = 8

        # 종합설계 과목 정의
        design_planning = "종합설계기획"
        design1 = "종합설계1"
        design2 = "종합설계2"
        design_courses = [design_planning, design1, design2]

        # 종합설계 과목들을 lectures에서 찾기
        design_lectures = {}
        for lec in lectures:
            name = lec[0]
            if name in design_courses:
                design_lectures[name] = lec

        # 만약 lectures에서 찾을 수 없다면 full_lectures에서 찾기
        for lec in full_lectures:
            name = lec[0]
            if name in design_courses and name not in design_lectures:
                design_lectures[name] = lec

        # 이수 완료된 과목들 반영
        for semester_key, lec_by_type in completed_data.items():
            curriculum[semester_key] = []
            for lec_type, lec_list in lec_by_type.items():
                for _, name, credit, _, status in lec_list:
                    curriculum[semester_key].append((name, credit, lec_type))
                    total_credits += credit

        print("1. 이수 과목 반영 완료: ")
        log_total_credits(curriculum)

        # 종합설계 과목들을 미리 배정 (가장 우선순위)
        design_schedule = [
            (3, 2, design_planning),  # 3학년 2학기: 종합설계기획
            (4, 1, design1),  # 4학년 1학기: 종합설계1
            (4, 2, design2),  # 4학년 2학기: 종합설계2
        ]

        assigned_codes = set(completed_codes)
        assigned_names = set(completed_names)
        used_names = set(assigned_names)
        semester_credit_map = defaultdict(int)

        leftover_general = set(general_recommendations)
        scheduled_names = {name for sem in curriculum.values() for name, _, _ in sem}

        # 기존 커리큘럼의 학점 계산
        for sem_key, lectures_in_sem in curriculum.items():
            semester_credit_map[sem_key] = sum(c for _, c, _ in lectures_in_sem)

        # 종합설계 과목들 강제 배정
        for design_year, design_sem, design_name in design_schedule:
            # 이미 이수했거나 배정된 경우 스킵
            if design_name in assigned_names:
                print(f"[종합설계] {design_name} 이미 이수/배정됨 -> 스킵")
                continue

            # 해당 종합설계 과목 정보 찾기
            design_lec = design_lectures.get(design_name)
            if not design_lec:
                print(f"[종합설계 경고] {design_name} 강의 정보를 찾을 수 없음")
                # 강의 정보가 없어도 기본값으로 추가
                credit = 3  # 기본 학점
                lec_type = "ME"  # 기본 타입
                code = f"DEFAULT_{design_name}"
            else:
                name, credit, lec_type, _, _, _, _, _, code, _ = design_lec

            sem_key = f"{design_year}학년 {design_sem}학기"

            # 해당 학기가 아직 생성되지 않았다면 생성
            curriculum.setdefault(sem_key, [])

            # 종합설계 과목 우선 배정
            current_credits = semester_credit_map[sem_key]
            curriculum[sem_key].append((design_name, credit, lec_type))
            assigned_names.add(design_name)
            used_names.add(design_name)
            if design_lec:
                assigned_codes.add(code)
            semester_credit_map[sem_key] += credit
            total_credits += credit
            print(f"[종합설계 우선배정] {design_name} -> {sem_key} ({credit}학점, 현재 학기: {semester_credit_map[sem_key]}학점)")

        print("2. 종합설계 과목 배정 완료: ")
        log_total_credits(curriculum)

        # 미이수 필수 과목 반영
        uncompleted_mr, uncompleted_gr = await self.lecture_crud.get_uncompleted_required_lectures(
            assigned_codes, student_grade
        )

        for name in uncompleted_mr + uncompleted_gr:
            lec = next((l for l in lectures if l[0] == name), None)
            if not lec:
                lec = next((l for l in full_lectures if l[0] == name), None)
            if not lec:
                print(f"[미이수 필수 경고] {name} 강의 정보를 찾을 수 없음 -> 스킵")
                continue

            name, credit, lec_type, grade, semester, _, _, team_project, code, _ = lec

            if name == "진로와미래(취업과창직)":
                placed = False
                for gy in range(2, 10):  # 2학년부터 시작
                    for gs in [1, 2]:
                        candidate = f"{gy}학년 {gs}학기"
                        # 이미 그 학기 이수 완료라면 스킵
                        if candidate in completed_data and any(completed_data[candidate].values()):
                            continue
                        if semester_credit_map[candidate] + credit <= 21:
                            if assign_with_prerequisites(lec, gy, gs, candidate):
                                print(f"[예외 배정] {name} -> {candidate} ({credit}학점)")
                                placed = True
                                break
                    if placed:
                        break
                if not placed:
                    print(f"[예외 스킵] {name} -> 배정 실패 (21학점 초과)")
                continue

            if grade == '1' and student_grade != 1:
                continue

            if name in assigned_names or code in assigned_codes:
                print(f"[미이수 필수 중복 스킵] {name} 이미 배정됨")
                continue

            # 배정 가능한 학기
            if semester in ("1", "2"):
                candidate_sems = [f"{grade}학년 {semester}학기"]
            else:
                candidate_sems = [f"{grade}학년 1학기", f"{grade}학년 2학기"]

            placed = False
            for candidate in candidate_sems:
                if candidate in completed_data and any(completed_data[candidate].values()):
                    print(f"[미이수 필수 스킵] {name}: {candidate} 이수 완료 학기 -> 건너뜀")
                    continue

                if semester_credit_map[candidate] + credit <= 21:
                    if assign_with_prerequisites(lec, int(grade), int(semester), candidate):
                        print(f"[미이수 필수 배정+선수 확인] {name} -> {candidate} ({credit}학점)")
                        placed = True
                        break

            if not placed:
                if semester in ("1", "2"):
                    for gy in range(int(grade) + 1, 10):
                        candidate = f"{gy}학년 {semester}학기"
                        if semester_credit_map[candidate] + credit <= 21:
                            if assign_with_prerequisites(lec, int(grade), int(semester), candidate):
                                print(f"[미이수 필수 배정+선수 확인] {name} -> {candidate} ({credit}학점)")
                                placed = True
                                break

                else:
                    for gy in range(int(grade), 10):
                        for gs in [1, 2]:
                            candidate = f"{gy}학년 {gs}학기"
                            if semester_credit_map[candidate] + credit <= 21:
                                if assign_with_prerequisites(lec, int(grade), int(semester), candidate):
                                    print(f"[미이수 필수 배정+선수 확인] {name} -> {candidate} ({credit}학점)")
                                    placed = True
                                    break
                        if placed:
                            break

            if not placed:
                print(f"[미이수 필수 스킵] {name} -> 배정 가능한 학기 없음 (21학점 초과)")

        print("4. 미이수 필수 과목 배정 완료: ")
        log_total_credits(curriculum)

        # 강의 우선순위 설정
        lecture_priority = {}
        for lec in lectures:
            name, _, lec_type, _, _, _, _, _, code, _ = lec
            if name in required_major_names:
                lecture_priority[name] = 0
            elif name in final_recommendations:
                lecture_priority[name] = 1
            else:
                lecture_priority[name] = 2

        deferred_lectures = []
        general_iter = iter(general_recommendations)

        already_retake_assigned = set()

        # 메인 커리큘럼 생성 루프
        while (
                (graduation_mode and current_semester_index <= 8 and total_credits < total_required_credits) or
                (not graduation_mode and (len(curriculum) < 8 or current_semester_index <= 18))
        ):

            year = (current_semester_index + 1) // 2
            semester = 1 if current_semester_index % 2 else 2
            semester_key = f"{year}학년 {semester}학기"

            if (year < student_grade) or (year == student_grade and semester < student_semester):
                current_semester_index += 1
                continue

            current_semester_key = f"{year}학년 {semester}학기"
            if (year == student_grade and semester == student_semester
                    and current_semester_key in completed_data
                    and any(completed_data[current_semester_key].values())):
                current_semester_index += 1
                continue

            allowed_grades = [g for g in range(1, year + 1)]
            curriculum.setdefault(semester_key, [])
            semester_credits = semester_credit_map[semester_key]

            current_lecture_pool = [
                lec for lec in sorted(lectures, key=lambda x: lecture_priority.get(x[0], 2)) + deferred_lectures
                if lec[0] not in assigned_names and (lec[8] and lec[8] not in assigned_codes)
            ]

            next_deferred = set()

            if no_team_project_mode:
                filtered_pool = []
                for lec in current_lecture_pool:
                    team_project = lec[7]
                    lec_type = lec[2]
                    if team_project == "Y" and lec_type not in ("MR", "GR"):
                        continue
                    filtered_pool.append(lec)
                current_lecture_pool = filtered_pool

            # 재수강 강의 배정
            if retake_mode and retake_codes:
                for retake_code in retake_codes:
                    if retake_code in already_retake_assigned:
                        print(f"[재수강 중복 스킵] {retake_code} 이미 배정 완료됨")
                        continue

                    retake_lec = next((l for l in lectures if l[8] == retake_code), None)
                    if not retake_lec:
                        retake_lec = next((l for l in full_lectures if l[8] == retake_code), None)

                    print(f"[재수강 후보 확인] code={retake_code}, retake_lec={retake_lec}")

                    if not retake_lec:
                        print(f"[재수강 경고] 코드 {retake_code}에 해당하는 강의를 찾을 수 없음")
                        continue

                    name, credit, lec_type, grade, semester, _, _, _, code, _ = retake_lec

                    # 과거 학기 이수 여부 확인
                    past_only = any(
                        sem_key in completed_data and
                        any(n == name for _, n, _, _, _ in sum(completed_data[sem_key].values(), []))
                        for sem_key in completed_data
                    )

                    # 이미 배정된 경우 스킵
                    if (name in assigned_names or code in assigned_codes) and not past_only:
                        print(f"[재수강 중복 스킵] {name} ({code}) 이미 미래 학기에 있음")
                        continue
                    elif past_only:
                        print(f"[재수강 허용] {name} ({code}) 과거 학기 존재 -> 미래 학기 배정 계속 진행")

                    # 현재 학기 이후에만 배정
                    retake_assigned = False
                    print(f"[재수강 배정 시도] {name} ({code}), DB semester={semester}")

                    for gy in range(student_grade, 10):
                        for gs in [1, 2]:
                            if (gy < student_grade) or (gy == student_grade and gs < student_semester):
                                continue

                            if int(semester) != gs:
                                print(f"[재수강 스킵] {name} ({code}) -> DB semester={semester}, 현재 루프 semester={gs}")
                                continue

                            sem_key = f"{gy}학년 {gs}학기"
                            curriculum.setdefault(sem_key, [])
                            semester_credits = semester_credit_map[sem_key]

                            if semester_credits + credit <= 21:
                                curriculum[sem_key].append((name, credit, lec_type))
                                assigned_names.add(name)
                                assigned_codes.add(code)

                                semester_credit_map[sem_key] += credit
                                total_credits += credit
                                print(f"[재수강 배정] {name} -> {sem_key} ({credit}학점)")
                                retake_assigned = True
                                break
                        if retake_assigned:
                            break

                    if retake_assigned:
                        already_retake_assigned.add(retake_code)
                    else:
                        print(f"[재수강 실패] {name} 배정할 수 있는 학기를 찾지 못함")

                print("5. 재수강 강의 배정 완료: ")
                log_total_credits(curriculum)

            # 메인 강의 배정
            for lec in current_lecture_pool:
                name, credit, lec_type, grade, lec_semester, prereq, _, team_project, code, _ = lec

                if name in design_courses:
                    continue
                if not retake_mode and (code in assigned_codes or name in assigned_names):
                    continue

                # 추천 강의 배정
                if lec_type in ("MR", "ME") and name in final_recommendations:
                    placed = False

                    if prereq:
                        print(f"[추천 강의 후보] {name} -> 선수과목 있음: {prereq}")
                    else:
                        print(f"[추천 강의 후보] {name} -> 선수과목 없음")

                    valid_semesters = [int(lec_semester)] if lec_semester in ("1", "2") else [1, 2]

                    for gy in range(int(grade), 10):
                        for gs in valid_semesters:
                            if gy < int(grade) or (gy == int(grade) and gs < int(lec_semester)):
                                continue

                            candidate = f"{gy}학년 {gs}학기"
                            print(f"[추천 강의 배정 시도] {name} -> {candidate} (선수={prereq if prereq else '없음'})")
                            if assign_with_prerequisites(lec, gy, gs, candidate):
                                if prereq:
                                    print(f"[추천 강의 (선수 후 개설학기)] {name} -> {candidate}")
                                else:
                                    print(f"[추천 강의 (개설학기 배정)] {name} -> {candidate}")
                                placed = True
                                break
                        if placed:
                            break

            print("6. 전공 추천 강의 배정 완료: ")
            log_curriculum_snapshot(curriculum)
            log_total_credits(curriculum)

            # 교양 추천 배정
            general_start_points = [(2, 1), (2, 2), (3, 1), (3, 2)]
            for year, semester in general_start_points:
                sem_key = f"{year}학년 {semester}학기"
                if sem_key in completed_data and any(completed_data[sem_key].values()):
                    continue

                curriculum.setdefault(sem_key, [])
                semester_credits = semester_credit_map[sem_key]

                needed = 9 - sum(
                    c for _, c, t in curriculum[sem_key] if t == "GE"
                )
                if needed <= 0:
                    continue

                added_general = []
                current_general = sum(
                    credit for _, credit, lec_type in sum(curriculum.values(), [])
                    if lec_type in ["GR", "GE"]
                )

                while needed > 0:
                    if total_credits >= total_required_credits and current_general >= general_required_credits:
                        print(f"[교양 추천 중단] 현재 총 학점 {total_credits}, 졸업 요건 {total_required_credits} 충족")
                        break

                    try:
                        next_name = next(general_iter)
                    except StopIteration:
                        break

                    lec_list = await self.lecture_crud.get_general_lectures_by_name(next_name)
                    if not lec_list:
                        continue

                    for lec in lec_list:
                        name, credit, lec_type, grade, sem = (
                            lec.name, lec.credits, lec.type, lec.grade, lec.semester
                        )

                        if total_credits + credit > total_required_credits:
                            print(
                                f"[교양 추천 스킵] {name} ({credit}학점) -> 추가 시 {total_credits + credit}, 졸업요건 {total_required_credits} 초과")
                            continue

                        if name in assigned_names or name in used_names:
                            continue

                        placed = False

                        if lec_type in ("GR", "GE"):
                            placed = False

                            if sem in ("1", "2"):
                                candidate = f"{year}학년 {int(sem)}학기"

                                if sum(1 for name, _, t in curriculum[sem_key]
                                       if t in ("GR", "GE") and name != "진로와미래(취업과창직)") >= 3:
                                    continue

                                if semester_credit_map[candidate] + credit <= 21 and \
                                        sum(c for _, c, t in curriculum[candidate] if t == "GE") < 9:
                                    curriculum[candidate].append((name, credit, lec_type))
                                    assigned_names.add(name)
                                    used_names.add(name)
                                    semester_credit_map[candidate] += credit
                                    total_credits += credit
                                    placed = True
                                    print(f"[교양 추천] {name} -> {candidate}")
                                else:
                                    other_sem = 2 if sem == "1" else 1
                                    candidate = f"{year}학년 {other_sem}학기"
                                    if semester_credit_map[candidate] + credit <= 21 and \
                                            sum(c for _, c, t in curriculum[candidate] if t == "GE") < 9:
                                        curriculum[candidate].append((name, credit, lec_type))
                                        assigned_names.add(name)
                                        used_names.add(name)
                                        semester_credit_map[candidate] += credit
                                        total_credits += credit
                                        placed = True
                                        print(f"[교양 추천] {name} -> {candidate}")

                            else:
                                for gs in [1, 2]:
                                    candidate = f"{year}학년 {gs}학기"
                                    if semester_credit_map[candidate] + credit <= 21 and \
                                            sum(c for _, c, t in curriculum[candidate] if t == "GE") < 9:
                                        curriculum[candidate].append((name, credit, lec_type))
                                        assigned_names.add(name)
                                        used_names.add(name)
                                        semester_credit_map[candidate] += credit
                                        total_credits += credit
                                        placed = True
                                        print(f"[교양 추천] {name} -> {candidate}")
                                        break

                            if not placed:
                                for gy in range(year + 1, 5):
                                    for gs in [1, 2]:
                                        candidate = f"{gy}학년 {gs}학기"
                                        if semester_credit_map[candidate] + credit <= 21 and \
                                                sum(1 for name, _, t in curriculum[candidate]
                                                    if t in ("GR", "GE") and name != "진로와미래(취업과창직)") < 3 and \
                                                sum(c for _, c, t in curriculum[candidate] if t == "GE") < 9:
                                            curriculum[candidate].append((name, credit, lec_type))
                                            assigned_names.add(name)
                                            used_names.add(name)
                                            semester_credit_map[candidate] += credit
                                            total_credits += credit
                                            print(f"[교양 추천] {name} -> {candidate}")
                                            placed = True
                                            break
                                    if placed:
                                        break

                        if placed:
                            break

                if added_general:
                    print(f"[교양 추천] {sem_key} -> {added_general}")

            for year in [4]:
                for semester in [1, 2]:
                    sem_key = f"{year}학년 {semester}학기"
                    curriculum.setdefault(sem_key, [])
                    semester_credits = semester_credit_map[sem_key]

                    current_general = sum(
                        credit for _, credit, lec_type in sum(curriculum.values(), [])
                        if lec_type in ["GR", "GE"]
                    )
                    if current_general >= general_required_credits:
                        continue

                    needed = 9 - sum(c for _, c, t in curriculum[sem_key] if t == "GE")
                    if needed <= 0:
                        continue

                    added_general = []
                    while needed > 0:
                        try:
                            next_name = next(general_iter)
                        except StopIteration:
                            break

                        lec_list = await self.lecture_crud.get_general_lectures_by_name(next_name)
                        if not lec_list:
                            continue

                        placed = False
                        for lec in lec_list:
                            name, credit, lec_type, grade, sem = (
                                lec.name, lec.credits, lec.type, lec.grade, lec.semester
                            )

                            if name in assigned_names or name in used_names:
                                continue

                            if sem in ("1", "2") and int(sem) != semester:
                                continue

                            if sum(1 for name, _, t in curriculum[sem_key]
                                   if t in ("GR", "GE") and name != "진로와미래(취업과창직)") >= 3:
                                continue

                            if semester_credit_map[sem_key] + credit <= 21:
                                curriculum[sem_key].append((name, credit, lec_type))
                                assigned_names.add(name)
                                used_names.add(name)
                                semester_credit_map[sem_key] += credit
                                total_credits += credit
                                added_general.append((name, credit))
                                leftover_general.discard(name)
                                needed -= credit
                                placed = True
                                break

                        if not placed:
                            print(f"[교양 추천 보류] {next_name} -> 4학년 {semester}학기 배정 실패, 추후 5학년 검토 예정")

                    if added_general:
                        print(f"[교양 추천] {sem_key} -> {added_general}")

            print("7. 교양 추천 배정 완료: ")
            log_curriculum_snapshot(curriculum)
            log_total_credits(curriculum)

            deferred_lectures = list(next_deferred)
            current_semester_index += 1

        general_semester_credit_map = defaultdict(int)

        for sem_key, lectures_in_sem in curriculum.items():
            for _, credit, lec_type in lectures_in_sem:
                if lec_type in ("GR", "GE"):
                    general_semester_credit_map[sem_key] += credit

        # 학기별 최소 학점 보완 및 교양 강의 배정
        for sem_key, lectures_in_sem in curriculum.items():
            match = re.match(r"(\d+)학년 (\d)학기", sem_key)
            if not match:
                continue

            year, semester = match.groups()
            year = int(year)
            semester = int(semester)

            if year < 2:
                continue

            semester_credits = sum(c for _, c, _ in lectures_in_sem)

            # 최소 18학점 채우기
            if year <= 3:
                while semester_credits < 18:
                    needed = 18 - semester_credits

                    major_pool = [
                        l for l in full_lectures
                        if l[0] not in assigned_names
                           and l[0] not in used_names
                           and l[2] in ("MR", "ME")
                           and semester_credit_map[sem_key] + l[1] <= 21
                           and int(l[3]) == year
                           and (
                                   l[4] in ("1", "2") and int(l[4]) == semester
                                   or l[4] not in ("1", "2")
                           )
                    ]

                    added_major = []
                    if major_pool:
                        added_major = await add_extra_lectures(
                            curriculum,
                            major_interest,
                            major_pool,
                            needed_credits=needed,
                            types=["MR", "ME"],
                            used_names=assigned_names,
                            student_grade=student_grade,
                            student_semester=student_semester
                        )

                    if added_major:
                        for name, credit in added_major:
                            assigned_names.add(name)
                            used_names.add(name)
                            semester_credit_map[sem_key] += credit
                            semester_credits += credit
                            total_credits += credit
                        print(f"[전공 보완] {sem_key} -> {semester_credits}학점")
                        continue

                    # 더 이상 추가할 과목이 없으면 종료
                    print(f"[보완 실패] {sem_key}: {semester_credits}학점까지만 채움")
                    break

            else:
                continue

        print("8. 학기별 최소 학점 보완 완료: ")
        log_curriculum_snapshot(curriculum)
        log_total_credits(curriculum)

        # 부족한 학점 보완
        all_lectures = sum(curriculum.values(), [])
        current_major = sum(credit for _, credit, lec_type in all_lectures if lec_type in ["MR", "ME"])
        current_general = sum(credit for _, credit, lec_type in all_lectures if lec_type in ["GR", "GE"])
        current_total = current_major + current_general

        needed_major = max(0, major_required_credits - current_major)
        needed_general = max(0, general_required_credits - current_general)
        needed_total = max(0, total_required_credits - current_total)

        if needed_major > 0:
            print("[전공 강의 추가 보완 중]")
            total_added_major = 0

            while total_added_major < needed_major:
                candidate_major = None

                for lec in full_lectures:
                    if (
                            lec[2] == "ME"
                            and lec[0] not in assigned_names
                            and lec[0] not in used_names
                            and lec[3] != '1'
                    ):
                        name, credit, lec_type, grade, sem, *_ = lec
                        # 원래 학기 우선
                        if sem in ("1", "2"):
                            target = f"{grade}학년 {sem}학기"
                            if semester_credit_map[target] + credit <= 21:
                                candidate_major = (lec, target)
                                break
                        # 개설 학기 불명확하면 현재 이후 학기부터 탐색
                        else:
                            for gy in range(int(grade), 10):
                                for gs in [1, 2]:
                                    target = f"{gy}학년 {gs}학기"
                                    if semester_credit_map[target] + credit <= 21:
                                        candidate_major = (lec, target)
                                        break
                                if candidate_major:
                                    break
                    if candidate_major:
                        break

                if not candidate_major:
                    print("더 이상 전공 선택 보완 불가")
                    break

                lec, sem_key = candidate_major
                name, credit, lec_type, *_ = lec
                curriculum.setdefault(sem_key, []).append((name, credit, lec_type))
                assigned_names.add(name)
                used_names.add(name)
                semester_credit_map[sem_key] += credit
                total_credits += credit
                total_added_major += credit
                print(f"[전공 보완] {name} -> {sem_key} ({credit}학점), 남은 학점: {needed_major - total_added_major}")

        if needed_general > 0 and total_credits < total_graduation_credits:
            print("[교양 강의 추가 보완 중]")
            total_added_general = 0

            while total_added_general < needed_general and total_credits < total_graduation_credits + 3:
                general_pool = [
                    l for l in full_lectures
                    if l[0] in leftover_general
                       and l[0] not in assigned_names
                       and l[0] not in used_names
                       and l[0] not in scheduled_names
                ]
                if not general_pool:
                    general_pool = [
                        l for l in full_lectures
                        if l[2] == "GE"
                           and l[0] not in assigned_names
                           and l[0] not in used_names
                           and l[3] != '1']


                added_general = await add_extra_lectures(
                    curriculum,
                    general_interest,
                    general_pool,
                    needed_general - total_added_general,
                    types=["GE"],
                    used_names=used_names,
                    student_grade=student_grade,
                    student_semester=student_semester
                )

                if not added_general:
                    for lec in general_pool:
                        name, credit, lec_type, grade, sem, *_ = lec
                        placed = False

                        for gy in range(2, 5):
                            for gs in [1, 2]:
                                sem_key = f"{gy}학년 {gs}학기"
                                if sum(1 for name, _, t in curriculum[sem_key]
                                       if t in ("GR", "GE") and name != "진로와미래(취업과창직)") >= 3:
                                    continue

                                if semester_credit_map[sem_key] + credit <= 21:
                                    curriculum.setdefault(sem_key, []).append((name, credit, lec_type))
                                    assigned_names.add(name)
                                    used_names.add(name)
                                    semester_credit_map[sem_key] += credit
                                    total_credits += credit
                                    print(f"[교양 보완] {name} -> {sem_key}")
                                    placed = True
                                    break
                            if placed:
                                break

                        if not placed:
                            for gy in range(5, 7):
                                for gs in [1, 2]:
                                    sem_key = f"{gy}학년 {gs}학기"

                                    if sum(1 for name, _, t in curriculum[sem_key]
                                           if t in ("GR", "GE") and name != "진로와미래(취업과창직)") >= 3:
                                        continue

                                    if semester_credit_map[sem_key] + credit <= 21:
                                        curriculum.setdefault(sem_key, []).append((name, credit, lec_type))
                                        assigned_names.add(name)
                                        used_names.add(name)
                                        semester_credit_map[sem_key] += credit
                                        total_credits += credit
                                        print(f"[교양 보완] {name} -> {sem_key}")
                                        placed = True
                                        break
                                if placed:
                                    break

                for name, credit in added_general:
                    if name in assigned_names or name in used_names:
                        continue
                    assigned_names.add(name)
                    used_names.add(name)
                    leftover_general.discard(name)
                    total_credits += credit

                added_credits = sum(credit for _, credit in added_general)
                total_added_general += added_credits
                print("[교양 추가 보완 강의]", added_general)

                if not added_general:
                    break

        if needed_total > 0:
            print("[전체 학점 추가 보완 중]")
            while total_credits < total_required_credits:
                all_pool = [
                    l for l in full_lectures
                    if l[2] in ["ME", "GE", "MR", "GR", "FE"]
                       and l[0] not in assigned_names
                       and l[0] not in used_names
                       and l[0] not in scheduled_names
                       and l[3] != '1'
                ]

                added_total = await add_extra_lectures(
                    curriculum,
                    major_interest + general_interest,
                    all_pool,
                    total_required_credits - total_credits,
                    types=["ME", "GE", "MR", "GR", "FE"],
                    used_names=used_names,
                    student_grade=student_grade,
                    student_semester=student_semester
                )

                for name, credit in added_total:
                    assigned_names.add(name)
                    used_names.add(name)

                all_lectures = sum(curriculum.values(), [])
                total_credits = sum(c for _, c, _ in all_lectures)

                print("[전체 학점 추가 보완 강의]", added_total)
                print("[남은 부족 학점]", total_required_credits - total_credits)

                if not added_total:
                    break

        # 최종 정렬
        sorted_curriculum = {
            k: curriculum[k] for k in sorted(curriculum.keys(), key=sort_key)
        }

        # 최종 강의 리스트 생성
        final_filtered_lecture_list = []
        lecture_name_to_code = {name: code for name, _, _, _, _, _, _, _, code, _ in lecture_list}

        for semester_key, lectures in sorted_curriculum.items():
            match = re.match(r"(\d+)학년 (\d)학기", semester_key)
            if not match:
                print(f"[경고] 학기 파싱 실패: '{semester_key}' -> 건너뜀")
                continue

            grade, semester = match.groups()
            for name, credit, lec_type in lectures:
                code = lecture_name_to_code.get(name, '')
                final_filtered_lecture_list.append((name, credit, lec_type, grade, semester, '', '', '', code, '', ''))

        print("final_filtered:", final_filtered_lecture_list)
        print("sorted:", sorted_curriculum)

        all_lectures = sum(sorted_curriculum.values(), [])
        total_credits = sum(credit for _, credit, _ in all_lectures)

        print("9. 부족 학점 보완 완료: ")
        log_curriculum_snapshot(curriculum)
        log_total_credits(curriculum)

        return sorted_curriculum, total_credits, final_filtered_lecture_list