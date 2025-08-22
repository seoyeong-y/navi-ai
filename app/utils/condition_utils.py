from typing import List
from app.core.constants import CONDITION_CODES, CONDITION_NAMES

# 선택된 조건들을 코드로 변환
def encode_conditions(selected_conditions: List[str]) -> str:
    if not selected_conditions:
        return ""

    condition_codes = [
        CONDITION_CODES[cond]
        for cond in selected_conditions
        if cond in CONDITION_CODES
    ]
    return ",".join(sorted(condition_codes))


# 저장된 조건 코드를 읽기 쉬운 텍스트로 변환
def decode_conditions(conditions_string: str) -> List[str]:
    if not conditions_string:
        return []

    codes = [code.strip() for code in conditions_string.split(',') if code.strip()]
    return [
        CONDITION_NAMES[code]
        for code in codes
        if code in CONDITION_NAMES
    ]


# 조건 요약 문자열 생성
def get_condition_summary(conditions_string: str) -> str:
    decoded = decode_conditions(conditions_string)
    return ", ".join(decoded) if decoded else "조건 없음"