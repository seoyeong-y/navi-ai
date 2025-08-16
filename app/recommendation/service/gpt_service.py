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

    # 재수강 강의 코드 변환
    async def names_to_codes_by_gpt(self, user_names, lecture_list, completed_data):
        GRADE_POINT = {
            'A+': 4.5, 'A0': 4.0,
            'B+': 3.5, 'B0': 3.0,
            'C+': 2.5, 'C0': 2.0,
            'D+': 1.5, 'D0': 1.0,
            'F': 0
        }

        candidate_names = set()
        for sem in completed_data.values():
            for lecture_type, lectures in sem.items():
                for code, name, credit, grade in lectures:
                    g = GRADE_POINT.get(str(grade).strip(), 10)
                    if g <= 2.5 or grade == 'NP':
                        candidate_names.add(name)
        candidate_names = list(candidate_names)

        lecture_name_to_code = {lec[0]: lec[8] for lec in lecture_list}

        codes = []
        for input_name in user_names:
            resolved_name = await self.find_similar_lecture_by_gpt(input_name, candidate_names)
            if not resolved_name:
                print(f"[경고] 유사 강의명 찾기 실패: {input_name}")
                continue
            code = lecture_name_to_code.get(resolved_name)
            if code:
                codes.append(code)
            else:
                print(f"[경고] name→code 변환 실패: {resolved_name}")
        return codes

    # 추가 확인 판단
    async def is_user_confirming_addition(self, user_input: str) -> bool:
        prompt = f"""
        사용자의 입력: "{user_input}"

        위 입력이 이전에 제안한 강의 추가에 대한 '확인' 또는 '동의'를 의미하면 "YES", 아니라면 "NO"라고만 답하세요.
        예: "응", "네", "맞아", "추가해줘", "그거야", "좋아" → YES
        예: "아니", "다른 거", "그건 아냐", "다시 알려줘" → NO
        절대 다른 설명 없이 YES 또는 NO만 출력하세요.
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3,
                temperature=0
            )
            return response.choices[0].message.content.strip().upper() == "YES"
        except Exception as e:
            print(f"[GPT 확인 응답 판단 오류] {e}")
            return False

    # 커리큘럼 편집 요청 판단
    async def is_curriculum_edit_request(self, user_input: str) -> bool:
        prompt = f"""
        사용자의 입력: "{user_input}"

        이 입력이 본인의 커리큘럼에서 강의를 추가하거나 삭제하거나, 특정 학기로 이동시키려는 요청이면 "YES", 아니라면 "NO"라고만 답하세요.

        다음은 YES인 예시입니다:
        - "자바 수업 빼줘"
        - "논리회로 3학년 1학기로 옮겨줘"
        - "딥러닝 수업 추가해줘"
        - "커리큘럼에 웹프레임워크 넣고 싶어"

        다음은 NO인 예시입니다:
        - "커리큘럼 삭제해줘"
        - "커리큘럼 21 지워"
        - "커리큘럼 목록 보여줘"
        - "졸업 요건 알려줘"

        절대 다른 설명 없이 YES 또는 NO만 출력하세요.
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3,
                temperature=0
            )
            return response.choices[0].message.content.strip().upper() == "YES"
        except Exception as e:
            print(f"[GPT 수정 판단 오류] {e}")
            return False

    # 커리큘럼 편집 명령 파싱
    async def parse_curriculum_edit_command(self, user_input: str, curri_id: int) -> dict:
        prompt = f"""
        사용자는 본인의 커리큘럼을 수정하려고 합니다.

        사용자 입력: "{user_input}"

        이 입력이 강의를 삭제하려는 요청이면:
        {{
            "action": "remove",
            "lecture_name": "강의명"
        }}

        강의를 다른 학기로 옮기려는 요청이면:
        {{
            "action": "move",
            "lecture_name": "강의명",
            "target_grade": "3",
            "target_semester": "2"
        }}

        강의를 추가하려는 요청이면:
        {{
            "action": "add",
            "lecture_name": "강의명",
            "target_grade": "3",
            "target_semester": "2"
        }}

        반드시 위 JSON 형식 중 하나로만 출력하고, 절대로 설명은 포함하지 마세요.
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0
            )
            return json.loads(response.choices[0].message.content.strip())
        except Exception as e:
            print(f"[parse_curriculum_edit_command 오류] {e}")
            return {}

    # 단순 메시지 전송용 GPT 함수
    async def chat_with_gpt_simple(self, message: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": message}]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"오류 발생: {e}"

    # 커리큘럼 삭제 요청 판단
    async def is_curriculum_delete_request(self, user_input: str, curri_names: List[str]) -> bool:
        curri_list_str = ", ".join(curri_names)
        prompt = f"""
        아래는 사용자가 보유한 커리큘럼 목록입니다:
        [{curri_list_str}]

        사용자의 입력: "{user_input}"

        이 입력이 위 목록 중 하나의 커리큘럼을 삭제하려는 의도인지 판단하세요.

        아래 조건을 모두 만족하면 "YES", 아니면 "NO"라고만 답하세요:
        - "삭제", "지워", "없애"와 같은 표현이 포함되어야 함
        - 위 목록 중 하나의 커리큘럼 이름이 명시되거나 암시되어야 함

        단, 강의 삭제, 이동, 추가에 대한 요청이면 "NO"로 답하세요.

        예:
        - "커리큘럼 21 삭제해줘" → YES
        - "머신러닝 수업 삭제해줘" → NO

        답변은 반드시 YES 또는 NO만 포함해야 합니다.
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3,
                temperature=0
            )
            return response.choices[0].message.content.strip().upper() == "YES"
        except Exception as e:
            print(f"[GPT 커리큘럼 삭제 판단 오류] {e}")
            return False

    # 삭제 확인 판단
    async def is_user_confirming_deletion(self, user_input: str) -> bool:
        prompt = f"""
        사용자의 입력: "{user_input}"

        이 입력이 '정말로 삭제하고 싶다'는 의미라면 "YES", 아니라면 "NO"라고만 대답하세요.
        예: "네", "응", "삭제해줘", "맞아", "그래", "지워", "ㅇㅇ", "삭제 원해" → YES
        예: "아니", "잘못 말했어", "아직", "보류", "그만", "취소", "지우지 마" → NO
        절대 다른 설명 없이 YES 또는 NO만 출력하세요.
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3,
                temperature=0
            )
            return response.choices[0].message.content.strip().upper() == "YES"
        except Exception as e:
            print(f"[GPT 삭제 확인 판단 오류] {e}")
            return False

    # 삭제 커리큘럼 이름 추출
    async def extract_curriculum_name_for_deletion(self, user_input: str, curri_names: List[str]) -> str:
        name_map = {
            curri_name.replace(" ", "").lower(): curri_name
            for curri_name in curri_names
        }

        prompt = f"""
        다음은 사용자가 가진 커리큘럼 목록입니다:
        {chr(10).join(f"- {name}" for name in curri_names)}

        사용자의 삭제 요청 입력: "{user_input}"

        이 입력에서 삭제하려는 커리큘럼의 이름을 정확히 추출해서 출력하세요.
        커리큘럼 이름 외에는 절대로 아무 설명도 하지 마세요.
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0
            )
            extracted = response.choices[0].message.content.strip()
            key = extracted.replace(" ", "").lower()
            return name_map.get(key, "")
        except Exception as e:
            print(f"[GPT 커리큘럼 삭제 이름 추출 실패] {e}")
            return ""

    # 커리큘럼 선택 요청 판단
    async def is_curriculum_selection_request(self, user_input: str) -> bool:
        prompt = f"""
        사용자의 입력: "{user_input}"

        이 입력이 '커리큘럼을 선택하려는 요청'인지 판단해주세요.
        예를 들어, "3번 커리큘럼 선택", "커리큘럼 2번 보여줘", "커리큘럼 1 골라줘" 같은 문장은 YES입니다.
        단순히 "커리큘럼 만들어줘", "강의 추가해줘"처럼 설계나 수정 요청이면 NO입니다.

        결과는 반드시 "YES" 또는 "NO"로만 출력해주세요.
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
            print(f"[GPT 커리큘럼 선택 판단 오류] {e}")
            return False

    # 커리큘럼 ID 추출
    async def extract_curriculum_id(self, user_input: str, user_id: int) -> int:
        from app.curriculum.curriculum_repository import CurriculumCrud
        from app.database.connection import get_db

        # 임시 DB 세션 생성 (실제 사용 시 적절한 방식으로 주입)
        async for db in get_db():
            curriculum_crud = CurriculumCrud(db)

            # 사용자가 가진 커리큘럼 이름과 ID 매핑
            from sqlalchemy import select
            from app.curriculum.curriculum_models import Curriculum

            stmt = select(Curriculum.id, Curriculum.name).where(Curriculum.user_id == user_id)
            result = await db.execute(stmt)

            for curri_id, name in result:
                if name.replace(" ", "") in user_input.replace(" ", ""):
                    return curri_id
            break

        return None

    # 선이수/필요 지식 과목 조회
    async def get_prerequisites_and_required_knowledge_by_name(self, lecture_name: str) -> List[str]:
        from app.database.connection import get_db
        from sqlalchemy import text

        query = """
                SELECT (SELECT GROUP_CONCAT(DISTINCT pre.name)
                        FROM prerequisite p
                                 JOIN lecture_code pre ON pre.id = p.pre_lecture_code
                        WHERE p.lecture_code = (SELECT lc.id \
                                                FROM lecture_code lc \
                                                WHERE lc.code = r.code \
                                                LIMIT 1))  AS prerequisites, \
                       (SELECT GROUP_CONCAT(DISTINCT req.name)
                        FROM required_knowledge rk
                                 JOIN lecture_code req ON req.id = rk.required_lecture_code
                        WHERE rk.lecture_code = (SELECT lc.id \
                                                 FROM lecture_code lc \
                                                 WHERE lc.code = r.code \
                                                 LIMIT 1)) AS required_knowledge
                FROM recent_lectures r
                WHERE r.name = :lecture_name
                LIMIT 1 \
                """

        async for db in get_db():
            result = await db.execute(text(query), {"lecture_name": lecture_name})
            row = result.fetchone()
            break

        if not row:
            return []

        prerequisites = row[0].split(",") if row[0] else []
        required_knowledge = row[1].split(",") if row[1] else []

        related = list(set(prerequisites + required_knowledge))
        return related