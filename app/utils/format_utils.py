import re

def parse_semester_key(key: str):
    try:
        year = int(key.split("학년")[0].strip())
        sem = int(key.split("학년")[1].strip().replace("학기", "").strip())
        return year, sem
    except (IndexError, ValueError):
        return 99, 99

def format_curriculum(curriculum: dict, completed_data: dict) -> str:
    output = []

    for semester in sorted(curriculum.keys(), key=parse_semester_key):
        is_completed_semester = semester in completed_data
        has_lectures = bool(curriculum[semester])
        if not is_completed_semester and not has_lectures:
            continue

        output.append(f"[{semester}]")
        for name, credit, lec_type in curriculum[semester]:
            output.append(f"- {name} ({credit}학점) - {lec_type}")
        output.append("")

    return "\n".join(output)

def format_lecture_info_block(final_lectures, lecture_data):
    lectures_str = "\n".join(f"- {lecture}" for lecture in final_lectures)

    lecture_info_str = "\n".join(
        f"{name} / {credit}학점 / {lec_type} / {grade}학년 / {semester}학기 / {prereq or '없음'} / {required_know or '없음'}"
        for name, credit, lec_type, grade, semester, prereq, required_know, code, major, _ in lecture_data
    )

    return lectures_str, lecture_info_str