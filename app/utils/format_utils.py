import re

def parse_semester_key(key: str):
    try:
        year = int(key.split("학년")[0].strip())
        sem = int(key.split("학년")[1].strip().replace("학기", "").strip())
        return year, sem
    except (IndexError, ValueError):
        return 99, 99

def build_semester_mapping(all_semesters):
    sorted_semesters = sorted(all_semesters, key=parse_semester_key)

    mapping = {}
    current_grade = 1
    prev_year, prev_sem = None, None

    for sem in sorted_semesters:
        year, sem_num = sem.split("-")
        year = int(year)
        sem_num = int(sem_num.replace("학기", "").strip())

        if prev_year is None:
            current_grade = 1
        else:
            if year == prev_year:
                # 같은 연도면 학년 유지
                pass
            else:
                # 연도가 바뀐 경우
                if prev_sem == 2 and sem_num == 1:
                    current_grade += 1  # 2학기 → 다음해 1학기 → 학년 증가
                else:
                    # 휴학으로 비어있는 경우 (ex. 2023-1 → 2024-2)
                    pass  # 학년 그대로

        mapping[sem] = (str(current_grade), str(sem_num))
        prev_year, prev_sem = year, sem_num

    return mapping

def format_curriculum(curriculum: dict, completed_data: dict) -> str:
    output = []

    for semester in sorted(curriculum.keys(), key=parse_semester_key):
        is_completed_semester = semester in completed_data
        has_lectures = bool(curriculum[semester])
        if not is_completed_semester and not has_lectures:
            continue

        # 여기서 semester는 이미 "2학년 1학기" 같은 형태
        output.append(f"[{semester}]")

        for name, credit, lec_type in curriculum[semester]:
            output.append(f"- {name} ({credit}학점) - {lec_type}")
        output.append("")

    return "\n".join(output)

def format_lecture_info_block(final_lectures, lecture_data):
    lectures_str = "\n".join(f"- {lecture}" for lecture in final_lectures)

    lecture_info_str = "\n".join(
        f"{name} / {credit}학점 / {lec_type} / {grade}학년 / {semester}학기 / {prereq or '없음'} / {required_know or '없음'}"
        for name, credit, lec_type, grade, semester, prereq, required_know, team_project, code, major in lecture_data
    )

    return lectures_str, lecture_info_str