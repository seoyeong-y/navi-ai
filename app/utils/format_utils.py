import re

def parse_semester_key(key: str):
    try:
        year = int(key.split("학년")[0].strip())
        sem = int(key.split("학년")[1].strip().replace("학기", "").strip())
        return year, sem
    except (IndexError, ValueError):
        return 99, 99


def build_semester_mapping(all_semesters: set, enrollment_year: int):
    mapping = {}
    sorted_semesters = sorted(all_semesters)

    counter = 0
    for sem in sorted_semesters:
        year_str, term_str = sem.split("-")
        if term_str == "1학기":
            sem_num = 1
        elif term_str == "2학기":
            sem_num = 2
        elif term_str == "여름학기":
            sem_num = "S"
        elif term_str == "겨울학기":
            sem_num = "W"
        else:
            sem_num = "?"

        if sem_num in (1, 2):
            counter += 1
            grade = (counter + 1) // 2
        else:
            grade = (counter + 1) // 2

        mapping[sem] = (grade, sem_num)

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

def normalize_semester(val: str) -> int:
    if str(val) == "1":
        return 1
    elif str(val) == "2":
        return 2
    elif str(val) in ("S", "W"):
        return 0
    else:
        raise ValueError(f"[학기 값 에러] 지원하지 않는 학기 값: {val}")
