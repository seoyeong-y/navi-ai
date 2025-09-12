import re
import asyncio
from typing import Tuple, Dict, List, Set
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.completed_data import get_completed_data
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
        log_curriculum_snapshot(curriculum)
        log_total_credits(curriculum)

        # 종합설계 과목들을 미리 배정 (가장 우선순위)
        design_schedule = [
            (3, 2, design_planning),  # 3학년 2학기: 종합설계기획
            (4, 1, design1),  # 4학년 1학기: 종합설계1
            (4, 2, design2),  # 4학년 2학기: 종합설계2
        ]

        assigned_codes = set(completed_codes)
        assigned_names = set(completed_names)
        semester_credit_map = defaultdict(int)

        # 기존 커리큘럼의 학점 계산
        for sem_key, lectures_in_sem in curriculum.items():
            semester_credit_map[sem_key] = sum(c for _, c, _ in lectures_in_sem)

        # 종합설계 과목들 강제 배정
        for design_year, design_sem, design_name in design_schedule:
            # 이미 이수했거나 배정된 경우 스킵
            if design_name in assigned_names:
                print(f"[종합설계] {design_name}은 이미 이수/배정됨 → 스킵")
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

            # 종합설계 과목 우선 배정 (21학점 내에서)
            current_credits = semester_credit_map[sem_key]
            curriculum[sem_key].append((design_name, credit, lec_type))
            assigned_names.add(design_name)
            if design_lec:  # 실제 강의 정보가 있는 경우에만 코드 추가
                assigned_codes.add(code)
            semester_credit_map[sem_key] += credit
            total_credits += credit
            print(f"[종합설계 우선배정] {design_name} → {sem_key} ({credit}학점, 현재 학기: {semester_credit_map[sem_key]}학점)")

        print("2. 종합설계 과목 배정 완료: ")
        log_curriculum_snapshot(curriculum)
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
                        success_local = assign_with_prerequisites(prereq_lec, lec_year, lec_semester, lec_sem_key,
                                                                  parent_stack)
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

            # 교양 추천 강의 우선 배정
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

                        if 15 <= semester_credits + credit <= 21:  # 종합설계 배정 후 남은 학점으로
                            curriculum[sem_key].append((name, credit, lec_type))
                            assigned_names.add(name)
                            assigned_codes.add(code)
                            semester_credit_map[sem_key] += credit
                            total_credits += credit
                            assigned = True
                            break
                    if assigned:
                        break

            print("3. 교양 추천 강의 배정 완료: ")
            log_curriculum_snapshot(curriculum)
            log_total_credits(curriculum)

            # 재수강 강의 배정 (사용자가 선택한 과목들만, 현재 학기 이후에)
            if retake_mode and retake_codes:
                for retake_code in retake_codes:
                    # retake_codes에 있는 과목들을 lectures에서 찾기
                    retake_lec = next((l for l in lectures if l[8] == retake_code), None)
                    if not retake_lec:
                        # lectures에 없으면 full_lectures에서 찾기
                        retake_lec = next((l for l in full_lectures if l[8] == retake_code), None)

                    if not retake_lec:
                        print(f"[재수강 경고] 코드 {retake_code}에 해당하는 강의를 찾을 수 없음")
                        continue

                    name, credit, lec_type, grade, semester, _, _, _, code, _ = retake_lec

                    # 이미 배정된 경우 스킵
                    if name in assigned_names or code in assigned_codes:
                        continue

                    # 현재 학기 이후에만 배정
                    retake_assigned = False
                    for gy in range(student_grade, 10):
                        for gs in [1, 2]:
                            # 현재 학기보다 이후 학기에만 배정
                            if (gy < student_grade) or (gy == student_grade and gs <= student_semester):
                                continue

                            # 원래 강의의 개설 학기와 맞춰서 배정
                            if int(semester) != gs:
                                continue

                            sem_key = f"{gy}학년 {gs}학기"
                            curriculum.setdefault(sem_key, [])
                            semester_credits = semester_credit_map[sem_key]

                            # 종합설계 과목 배정 후 남은 학점으로 재수강 과목 배정
                            if semester_credits + credit <= 21:
                                curriculum[sem_key].append((name, credit, lec_type))
                                assigned_names.add(name)
                                assigned_codes.add(code)
                                semester_credit_map[sem_key] += credit
                                total_credits += credit
                                print(f"[재수강 배정] {name} → {sem_key} ({credit}학점)")
                                retake_assigned = True
                                break
                        if retake_assigned:
                            break

                    if not retake_assigned:
                        print(f"[재수강 실패] {name} 배정할 수 있는 학기를 찾지 못함")

                print("4. 재수강 강의 배정 완료: ")
                log_curriculum_snapshot(curriculum)
                log_total_credits(curriculum)

            # 메인 강의 배정 (종합설계 배정 후 남은 학점으로)
            for lec in current_lecture_pool:
                name, credit, lec_type, grade, lec_semester, prereq, _, team_project, code, _ = lec

                # 종합설계 과목은 이미 배정했으므로 스킵
                if name in design_courses or code in assigned_codes or name in assigned_names:
                    continue

                if int(grade) not in allowed_grades:
                    continue
                if int(lec_semester) != semester:
                    continue

                # 현재 학기에 배정 가능한지 확인 (종합설계 과목 배정 후 남은 학점)
                if semester_credit_map[semester_key] + credit > 21:
                    overflow_inserted = False

                    # 다른 학기에 배정 시도
                    for gy in range(student_grade, 10):
                        for gs in [1, 2]:
                            if (gy < student_grade) or (gy == student_grade and gs <= student_semester):
                                continue
                            overflow_key = f"{gy}학년 {gs}학기"
                            if int(lec_semester) != gs:
                                continue
                            # 해당 학기의 종합설계 과목 배정 후 남은 학점 확인
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

            print("5. GPT 추천 강의 배정 완료: ")
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
                print(f"[경고] 학기 파싱 실패: '{semester_key}' → 건너뜀")
                continue

            grade, semester = match.groups()
            for name, credit, lec_type in lectures:
                code = lecture_name_to_code.get(name, '')
                final_filtered_lecture_list.append((name, credit, lec_type, grade, semester, '', '', '', code, '', ''))

        print("final_filtered:", final_filtered_lecture_list)
        print("sorted:", sorted_curriculum)

        all_lectures = sum(sorted_curriculum.values(), [])
        total_credits = sum(credit for _, credit, _ in all_lectures)

        print("6. 부족 학점 보완 완료: ")
        log_curriculum_snapshot(curriculum)
        log_total_credits(curriculum)

        return sorted_curriculum, total_credits, final_filtered_lecture_list