import json
import re
from typing import List, Tuple
from openai import AsyncOpenAI
from app.core.config import Settings

settings = Settings()

class GPTService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # 강의 개요 기반 추천 강의 필터링
    async def filter_recommended_lectures_by_description(
            self,
            recommended: List[str],
            lecture_infos: List[Tuple],
            user_input: str
    ) -> List[str]:
        if not recommended:
            return []

        lecture_info_dict = {
            name: (desc, obj)
            for name, desc, obj in lecture_infos
            if name in recommended
        }

        filter_prompt = f"""
        사용자의 관심 분야는 다음과 같습니다:
        - {user_input}

        아래는 추천된 강의 리스트입니다:
        {chr(10).join(f"- {name}" for name in recommended)}

        각 강의에 대한 설명은 다음과 같습니다:
        {chr(10).join(f"{name}: {desc or ''} {obj or ''}" for name, (desc, obj) in lecture_info_dict.items())}

        위 정보를 기반으로, 설명에 사용자의 관심 분야와 관련된 내용이 하나라도 포함되어 있다면, 해당 강의를 선별해주세요.
        강의명만 줄바꿈으로 출력하고, 다른 설명은 절대 포함하지 마세요.
        """

        response = await self.client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": filter_prompt}],
            max_tokens=200,
            temperature=0.5,
        )

        filtered_text = response.choices[0].message.content.strip()
        return [
            line.strip()
            for line in filtered_text.split("\n")
            if line.strip() in recommended
        ]


    # GPT 기반 유사 강의 검색
    async def find_similar_lecture_by_gpt(
            self,
            user_input: str,
            candidate_lectures: List[str]
    ) -> str:
        prompt = f"""
        아래는 강의명 후보 리스트입니다:
        {chr(10).join(f"- {name}" for name in candidate_lectures)}

        사용자가 입력한 강의 관련 요청: "{user_input}"

        위 입력에 가장 가까운 강의명을 하나만 골라서 출력하세요.
        다른 설명 없이 강의명 하나만 정확하게 출력하세요.
        """

        response = await self.client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.3
        )

        result = response.choices[0].message.content.strip()
        matched = next(
            (lec for lec in candidate_lectures
             if result.replace(" ", "").lower() in lec.replace(" ", "").lower()),
            None
        )
        return matched if matched else result


    # GPT로 추가/삭제 요청 분석
    async def parse_add_remove_lectures(
            self,
            user_input: str,
            current_lectures: List[str],
            available_lectures: List[str],
            previously_removed: List[str] = None
    ) -> Tuple[List[str], List[str]]:
        previously_removed = previously_removed or []

        prompt = f"""
        다른 설명, 분석 과정은 절대 출력하지 말고, JSON만 출력하세요.

        현재 추천된 강의 목록:
        {chr(10).join(f"- {lec}" for lec in current_lectures)}

        추가 가능한 전체 강의 목록:
        {chr(10).join(f"- {lec}" for lec in available_lectures)}

        사용자 입력: "{user_input}"

        [분석 기준]
        - 만약 입력한 강의명이 추천 리스트에 존재한다면 삭제 대상으로 간주하세요.
        - 입력한 강의명이 추천 리스트에 없고 전체 강의 목록에는 있다면 추가 대상으로 간주하세요.

        [출력 포맷]
        반드시 JSON 형식으로 출력하세요:
        {{
            "add": ["추가할 강의명1", "추가할 강의명2"],
            "remove": ["삭제할 강의명1", "삭제할 강의명2"]
        }}
        """

        response = await self.client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )

        text = response.choices[0].message.content.strip()
        match = re.search(r"\{(?:[^{}]|(?R))*}", text)

        if not match:
            print(f"JSON 패턴 매칭 실패: {text}")
            return [], []

        json_text = match.group()
        try:
            result = json.loads(json_text)
            return result.get("add", []), result.get("remove", [])
        except json.JSONDecodeError:
            print(f"JSON 디코딩 실패: {json_text}")
            return [], []


    # 삭제된 강의 제외 추천 판단
    async def is_requesting_alternative_recommendation(
            self,
            user_input: str,
            deleted_lectures: List[str]
    ) -> bool:
        prompt = f"""
        사용자의 입력: "{user_input}"

        다음은 사용자가 삭제한 강의 리스트입니다:
        {chr(10).join(f"- {name}" for name in deleted_lectures)}

        입력에 삭제된 강의명 중 하나라도 포함되어 있고,  
        그 강의를 빼고 다른 강의를 추천해달라는 의도로 보이면 "YES"라고만 출력하세요.

        그 외에는 "NO"라고만 출력하세요.
        반드시 YES 또는 NO만 출력하세요.
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3,
                temperature=0
            )
            result = response.choices[0].message.content.strip()
            return result.upper() == "YES"
        except Exception as e:
            print(f"[GPT 대체 추천 판단 예외 발생] {e}")
            return False


    # 삭제된 강의 제외 유사 강의 추천
    async def suggest_other_similar_lectures(
            self,
            user_input: str,
            deleted_lectures: List[str],
            interest: List[str],
            available_lectures: List[str]
    ) -> List[str]:
        prompt = f"""
        사용자는 관심 분야로 "{user_input}"을 선택했습니다.
        그러나 다음 강의들은 제외하고 싶어 합니다:
        {chr(10).join(f"- {name}" for name in deleted_lectures)}

        관심 분야 키워드:
        {chr(10).join(f"- {kw}" for kw in interest)}

        전체 강의 후보 목록은 다음과 같습니다:
        {chr(10).join(f"- {lec}" for lec in available_lectures)}

        위 정보들을 기반으로 제외된 강의 외에 관심 분야와 관련된 강의명을 3개 추천하세요.
        출력은 강의명만 줄바꿈으로, 다른 설명은 포함하지 마세요.
        """

        response = await self.client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "너는 대학생의 강의 선택을 돕는 AI 챗봇이야."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.5
        )

        return [
            line.strip()
            for line in response.choices[0].message.content.strip().split("\n")
            if line.strip()
        ]


    # 관심 분야 명확성 판단
    async def resolve_unclear_interest(self, user_input: str) -> Tuple[List[str], bool]:
        prompt = f"""
        다음 입력이 명확한 관심 분야인지 판단하세요.
        입력: "{user_input}"

        1. 이 입력이 명확한 관심 분야이면 "YES: <관심 분야1>, <관심 분야2>, ..." 형식으로 출력하세요.
        2. 애매하거나 불분명한 입력이면 "NO: 컴퓨터공학부 학생들이 가장 쉽게 접하는 분야"라고 출력하세요.

        [YES 예시]
        - "인공지능과 웹 개발 분야에 관심 있어" → YES: 인공지능, 웹 개발
        - "데이터 분석, 머신러닝" → YES: 데이터 분석, 머신러닝

        [NO 예시]
        - "그냥 다 추천해줘"
        - "모르겠어"
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0
            )
            result = response.choices[0].message.content.strip()

            if "YES:" in result:
                start = result.index("YES:") + 4
                interests_raw = result[start:].strip()
                interests = [i.strip().strip('"') for i in interests_raw.split(",") if i.strip()]
                return interests, False
            elif "NO:" in result:
                return ["컴퓨터공학부 학생들이 가장 쉽게 접하는 분야"], True
            else:
                return [user_input], False

        except Exception as e:
            print(f"[GPT 관심 분야 처리 오류] {e}")
            return [user_input], False


    # 추천 강의 목록 수정 종료 판단
    async def is_no_more_modification(self, user_input: str) -> bool:
        prompt = f"""
        현재는 사용자가 추천된 강의 목록을 수정(추가/삭제)하는 단계입니다.

        사용자의 입력: "{user_input}"

        - "종료" : 더 이상 추천 강의를 수정할 의도가 없고 커리큘럼 생성을 시작해도 된다는 경우
        - "계속" : 강의를 추가/삭제하거나 다른 추천을 요청하는 경우

        반드시 "종료" 또는 "계속" 중 하나만 출력하세요.
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0
            )
            result = response.choices[0].message.content.strip().replace('"', '').strip()
            return result == "종료"
        except Exception as e:
            print(f"[GPT 판단 오류] {e}")
            return False


    # 커리큘럼 설계 조건 판단
    async def parse_conditions_with_gpt(self, user_input: str) -> List[str]:
        condition_keys = ["graduation", "no_team_project", "preferred_professor", "retake"]

        prompt = f"""
        아래는 대학 커리큘럼 설계 챗봇에 입력한 조건입니다.

        [입력 예시]
        "졸업 꼭 하고 싶고, 팀플은 싫어요. 재수강 포함해줘."

        [출력 예시]
        ["graduation", "no_team_project", "retake"]

        아래 입력에 대해, 해당되는 조건 키만 리스트로 출력하세요. 
        가능한 조건: graduation(졸업), no_team_project(팀플 제외), preferred_professor(선호 교수), retake(재수강)
        반드시 리스트만 반환하세요.

        [입력]
        {user_input}
        """

        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=40,
            temperature=0,
        )
        result = response.choices[0].message.content.strip()

        try:
            parsed = eval(result)
            if isinstance(parsed, list):
                return [c for c in parsed if c in condition_keys]
            return []
        except Exception:
            return []


    # 커리큘럼 설계 요청 판단
    async def is_curriculum_request(self, user_input: str) -> bool:
        prompt = f"""
        사용자의 입력: "{user_input}"

        아래 조건을 만족할 때 "YES", 아니라면 "NO"라고만 답하세요:
        - 사용자가 커리큘럼을 설계하거나 생성해달라고 요청하는 경우

        절대 설명 없이 YES 또는 NO만 출력하세요.
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3,
                temperature=0
            )
            result = response.choices[0].message.content.strip().upper()
            return result == "YES"
        except Exception as e:
            print(f"[GPT 커리큘럼 요청 판단 오류] {e}")
            return False