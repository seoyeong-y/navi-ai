import re
import asyncio
from typing import Tuple, Dict, List, Set
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.completed_data import completed_data
from app.core.constants import *
from app.lecture.lecture_repository import LectureCrud
from app.professor.professor_repository import ProfessorCrud
from app.utils.format_utils import format_curriculum
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
    ) -> dict:

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
            print(f"→ 누적 학점: 총 {total}, 전공 {major}, 교양 {general}")

        def sort_key(semester_str):
            match = re.match(r"(\d+)학년 (\d)학기", semester_str)
            if match:
                return int(match.group(1)), int(match.group(2))
            return 999, 999

        curriculum = {}
        total_credits = 0
        current_semester_index = 1
        max_semester_limit = 18
        if graduation_mode:
            max_semester_limit = 8

        design_planning = "종합설계기획"
        design1 = "종합설계1"
        design2 = "종합설계2"
        design_courses = [design_planning, design1, design2]
        design_assigned = set()
        design_lectures = {name: lec for lec in lectures if lec[0] in design_courses for name in [lec[0]]}

        for semester_key, lec_by_type in completed_data.items():
            curriculum[semester_key] = []
            for lec_type, lec_list in lec_by_type.items():
                for _, name, credit, _ in lec_list:
                    curriculum[semester_key].append((name, credit, lec_type))
                    total_credits += credit

        print("1. 이수 과목 반영 완료: ")
        log_curriculum_snapshot(curriculum)
        log_total_credits(curriculum)

        lecture_priority = {}
        for lec in lectures:
            name, _, lec_type, _, _, _, _, _, code, _ = lec
            if name in required_major_names:
                lecture_priority[name] = 0
            elif name in final_recommendations:
                lecture_priority[name] = 1
            else:
                lecture_priority[name] = 2

        assigned_codes = set(completed_codes)
        assigned_names = set(completed_names)

        missing_design_courses = [name for name in design_courses if name not in assigned_names]

        deferred_lectures = []

        def assign_with_prerequisites(lec, lec_year, lec_semester, lec_sem_key, parent_stack=None):
            nonlocal semester_credits, total_credits
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
                for req_name in required_list:
                    if req_name in assigned_names:
                        continue
                    prereq_lec = next((l for l in lectures if l[0] == req_name), None)
                    if prereq_lec:
                        if int(prereq_lec[4]) > lec_semester:
                            print(f"[선수 과목 불일치] {name_local}의 선수 {req_name}은 {lec_semester}학기 이후임 → 스킵")
                            return False
                        parent_stack.add(name_local)

                        print(f"[선수 과목 확인] {name_local} → 선수 과목 {req_name} 배정 시도")
                        success_local = assign_with_prerequisites(prereq_lec, lec_year, lec_semester, lec_sem_key, parent_stack)
                        parent_stack.remove(name_local)
                        if not success_local:
                            print(f"[선수 과목 배정 성공] {req_name}")
                        else:
                            print(f"[선수 과목 배정 실패] {req_name} → {name_local} 스킵")
                            return False
                    else:
                        print(f"[선수 과목 배정 실패] {req_name} → {name_local} 스킵")
                        return False

            curriculum[lec_sem_key].append((name_local, credit_local, type_local))
            assigned_names.add(name_local)
            assigned_codes.add(code_local)
            semester_credit_map[lec_sem_key] += credit_local
            semester_credits += credit_local
            total_credits += credit_local
            return True

        semester_credit_map = defaultdict(int)

        while (
                (graduation_mode and current_semester_index <= 8 and total_credits < total_required_credits) or
                (not graduation_mode and (len(curriculum) < 8 or current_semester_index <= 18))
        ):

            year = (current_semester_index + 1) // 2
            semester = 1 if current_semester_index % 2 else 2
            semester_key = f"{year}학년 {semester}학기"

            reserved_design_semesters = [
                (3, 2, design_planning),
                (4, 1, design1),
                (4, 2, design2),
            ]

            for gy, gs, design_name in reserved_design_semesters:
                if design_name in assigned_names:
                    continue
                lec = design_lectures.get(design_name)
                if not lec:
                    continue
                name, credit, lec_type, _, _, _, _, _, code, _ = lec
                sem_key = f"{gy}학년 {gs}학기"
                curriculum.setdefault(sem_key, [])
                if semester_credit_map[sem_key] + credit <= 21:
                    curriculum[sem_key].append((name, credit, lec_type))
                    assigned_names.add(name)
                    assigned_codes.add(code)
                    design_assigned.add(name)
                    semester_credit_map[sem_key] += credit
                    total_credits += credit
                    print(f"[종합설계 강제 배정] {name} → {sem_key}")

            if (year < student_grade) or (year == student_grade and semester < student_semester):
                current_semester_index += 1
                continue

            allowed_grades = [g for g in range(1, year + 1)]
            curriculum.setdefault(semester_key, [])
            semester_credits = semester_credit_map[semester_key]

            current_lecture_pool = sorted(lectures, key=lambda x: lecture_priority.get(x[0], 2)) + deferred_lectures
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

            for sem_key in curriculum:
                semester_credit_map[sem_key] = sum(c for _, c, _ in curriculum[sem_key])

            priority_semester_keys = [f"{y}학년 {s}학기" for y in range(1, 4) for s in range(1, 3)]
            fallback_semester_keys = [f"{y}학년 {s}학기" for y in range(4, 7) for s in range(1, 3)]

            for gen_name in general_recommendations:
                if gen_name in assigned_names:
                    continue

                if total_credits >= total_graduation_credits:
                    print(f"[총 학점 초과로 교양 {gen_name} 배정을 중단]")
                    continue

                gen_lec = next((l for l in lectures if l[0] == gen_name), None)
                if not gen_lec:
                    continue

                name, credit, lec_type, _, _, _, _, _, code, _ = gen_lec

                assigned = False

                if total_credits + credit > total_graduation_credits + 5:
                    print(f"[140학점 초과 방지를 위해 교양 {name} 배정 생략]")
                    continue

                for sem_keys in [priority_semester_keys, fallback_semester_keys]:
                    for sem_key in sem_keys:
                        curriculum.setdefault(sem_key, [])
                        semester_credits = sum(c for _, c, _ in curriculum[sem_key])
                        sem_year, sem_term = map(int, re.findall(r"\d+", sem_key))

                        if total_credits >= total_graduation_credits or sem_year >= 5:
                            continue

                        if (sem_year < student_grade) or (sem_year == student_grade and sem_term <= student_semester):
                            continue

                        if 18 <= semester_credits + credit <= 21:
                            curriculum[sem_key].append((name, credit, lec_type))
                            assigned_names.add(name)
                            assigned_codes.add(code)
                            semester_credit_map[sem_key] += credit
                            total_credits += credit
                            assigned = True
                            break
                    if assigned:
                        break

            print("2. 종합설계 과목 배정 완료: ")
            log_curriculum_snapshot(curriculum)
            log_total_credits(curriculum)

            if retake_mode:
                for code in retake_codes:
                    lec = next((l for l in lectures if l[7] == code), None)
                    if not lec:
                        continue
                    name, credit, lec_type, grade, semester, _, _, _, _, _ = lec

                    if name in assigned_names or code in assigned_codes:
                        continue

                    for gy in range(student_grade, 10):
                        for gs in [1, 2]:
                            sem_key = f"{gy}학년 {gs}학기"
                            curriculum.setdefault(sem_key, [])
                            semester_credits = sum(c for _, c, _ in curriculum[sem_key])
                            if semester_credits + credit <= 21:
                                curriculum[sem_key].append((name, credit, lec_type))
                                assigned_names.add(name)
                                assigned_codes.add(code)
                                print(f"[재수강 강의 배정]: {name} → {sem_key}")
                                break
                        else:
                            continue
                        break

                print("재수강 강의 배정 완료: ")
                log_curriculum_snapshot(curriculum)
                log_total_credits(curriculum)

            for lec in current_lecture_pool:
                name, credit, lec_type, grade, lec_semester, prereq, _, team_project, code, _ = lec
                if name in design_courses or code in assigned_codes or name in assigned_names or name in design_assigned:
                    continue
                if int(grade) not in allowed_grades:
                    continue
                if int(lec_semester) != semester:
                    continue

                if semester_credit_map[semester_key] + credit > 21:
                    overflow_inserted = False

                    for gy in range(student_grade, 10):
                        for gs in [1, 2]:
                            if (gy < student_grade) or (gy == student_grade and gs <= student_semester):
                                continue
                            overflow_key = f"{gy}학년 {gs}학기"
                            if int(lec_semester) != gs:
                                continue
                            if semester_credit_map[overflow_key] + credit <= 21:
                                curriculum.setdefault(overflow_key, []).append((name, credit, lec_type))
                                assigned_names.add(name)
                                assigned_codes.add(code)
                                semester_credit_map[overflow_key] += credit
                                total_credits += credit
                                overflow_inserted = True
                                break
                        if overflow_inserted:
                            break

                    if not overflow_inserted:
                        next_deferred.add(lec)

                    continue

                if (year < student_grade) or (year == student_grade and semester < student_semester):
                    continue

                success = assign_with_prerequisites(lec, year, semester, semester_key)
                if not success:
                    next_deferred.add(lec)

            deferred_lectures = list(next_deferred)
            current_semester_index += 1

            print("3. GPT 추천 강의 배정 완료: ")
            log_curriculum_snapshot(curriculum)
            log_total_credits(curriculum)

        all_lectures = sum(curriculum.values(), [])
        current_major = sum(credit for _, credit, lec_type in all_lectures if lec_type in ["MR", "ME"])
        current_general = sum(credit for _, credit, lec_type in all_lectures if lec_type in ["GR", "GE"])
        current_total = current_major + current_general

        needed_major = max(0, major_required_credits - current_major)
        needed_general = max(0, general_required_credits - current_general)
        needed_total = max(0, total_required_credits - current_total)

        used_names = set(name for name, _, _ in all_lectures)

        if needed_major > 0:
            print("[전공 강의 추가 보완 중]")
            total_added_major = 0

            while total_added_major < needed_major:
                major_pool = [l for l in full_lectures if l[2] == "ME" and l[0] not in used_names and l[3] != '1']
                added_major = await add_extra_lectures(
                    curriculum,
                    major_interest,
                    major_pool,
                    needed_major - total_added_major,
                    types=["ME"],
                    used_names=used_names,
                    student_grade=student_grade,
                    student_semester=student_semester
                )
                for name, _ in added_major:
                    used_names.add(name)
                print("[전공 추가 보완 강의]", added_major)

                added_credits = sum(credit for _, credit in added_major)
                total_added_major += added_credits
                print("[남은 전공 학점]", needed_major - total_added_major)

                if not added_major:
                    print("더 이상 추가할 강의가 없어 루프를 중단합니다.")
                    break

        if needed_general > 0 and total_credits < total_graduation_credits:
            print("[교양 강의 추가 보완 중]")
            total_added_general = 0

            while total_added_general < needed_general and total_credits < total_graduation_credits + 3:
                general_pool = [l for l in full_lectures if l[2] == "GE" and l[0] not in used_names and l[3] != '1']
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

                for name, _ in added_general:
                    used_names.add(name)
                print("[교양 추가 보완 강의]", added_general)

                added_credits = sum(credit for _, credit in added_general)
                total_added_general += added_credits
                print("[남은 교양 학점]", needed_general - total_added_general)

                if not added_general:
                    print("더 이상 추가할 강의가 없어 루프를 중단합니다.")
                    break

        if needed_total > 0:
            print("[전체 학점 추가 보완 중]")
            total_added = 0

            while total_added < needed_total:
                all_pool = [
                    l for l in full_lectures
                    if l[2] in ["ME", "GE", "MR", "GR", "FE"]
                       and l[0] not in used_names
                       and l[3] != '1'
                ]

                added_total = await add_extra_lectures(
                    curriculum,
                    major_interest + general_interest,
                    all_pool,
                    needed_total - total_added,
                    types=["ME", "GE", "MR", "GR", "FE"],
                    used_names=used_names,
                    student_grade=student_grade,
                    student_semester=student_semester
                )

                for name, _ in added_total:
                    used_names.add(name)
                print("[전체 학점 추가 보완 강의]", added_total)

                added_credits = sum(credit for _, credit in added_total)
                total_added += added_credits
                print("[남은 부족 학점]", needed_total - total_added)

                if not added_total:
                    print("더 이상 추가할 강의가 없어 루프를 중단합니다.")
                    break

        sorted_curriculum = {
            k: curriculum[k] for k in sorted(curriculum.keys(), key=sort_key)
        }

        final_filtered_lecture_list = []
        lecture_name_to_code = {name: code for name, _, _, _, _, _, _, _, code, _ in lecture_list}

        for semester_key, lectures in sorted_curriculum.items():
            match = re.match(r"(\d+)학년 (\d)학기", semester_key)
            if not match:
                print(f"[경고] 학기 파싱 실패: '{semester_key}' → 건너뜀")
                continue

            grade, semester = match.groups()
            for name, credit, lec_type in lectures:
                code = lecture_name_to_code.get(name, '')
                final_filtered_lecture_list.append((name, credit, lec_type, grade, semester, '', '', '', code, ''))

        print("final_filtered:", final_filtered_lecture_list)
        print("sorted:", sorted_curriculum)

        all_lectures = sum(sorted_curriculum.values(), [])
        total_credits = sum(credit for _, credit, _ in all_lectures)

        print("4. 부족 학점 보완 완료: ")
        log_curriculum_snapshot(curriculum)
        log_total_credits(curriculum)

        return sorted_curriculum, total_credits, final_filtered_lecture_list