import httpx
from fastapi import WebSocket, WebSocketDisconnect
import openai
import json
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from app.chat.chat_repository import ChatCrud
from app.curriculum.curriculum_repository import CurriculumCrud
from app.lecture.lecture_repository import LectureCrud
from app.lecture.lecture_service import LectureService
from app.professor.professor_repository import ProfessorCrud
from app.recommendation.service.gpt_service import GPTService
from app.recommendation.service.recommendation_service import RecommendationService
from app.curriculum.service.curriculum_edit_service import CurriculumEditService
from app.utils.completed_data import completed_data
from app.curriculum.service.curriculum_manager import CurriculumService

load_dotenv()

GPT_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.AsyncOpenAI(
    api_key=GPT_API_KEY,
    http_client=httpx.AsyncClient()
)

userId = 1
user_curri_id = 40


class WebSocketHandler:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chat_crud = ChatCrud(db)
        self.curriculum_crud = CurriculumCrud(db)
        self.lecture_crud = LectureCrud(db)
        self.lecture_service = LectureService(db)
        self.professor_crud = ProfessorCrud(db)
        self.gpt_service = GPTService(db)  # DB 세션 주입
        self.recommendation_service = RecommendationService(db)
        self.curriculum_edit_service = CurriculumEditService(db)
        self.curriculum_service = CurriculumService(db)

    async def handle_websocket(self, websocket: WebSocket):
        await websocket.accept()

        session_id = await self.chat_crud.create_chat_session(userId=userId, session_type="curriculum")
        websocket.scope["session_id"] = session_id

        websocket.scope["view_mode"] = "list"
        websocket.scope["selected_curri_id"] = None

        mode = "idle"
        major_lectures = []
        general_lectures = []
        major_interest = None
        general_interest = None
        completed_codes = set()
        completed_names = set()

        try:
            while True:
                try:
                    print(">>> 메시지 수신 대기 중")
                    user_input = await websocket.receive_text()
                    print(f"[입력 수신] {user_input}")

                    try:
                        await self.chat_crud.save_chat_log(session_id=session_id, chat_type="U", message=user_input)
                    except Exception as e:
                        print(f"[사용자 메시지 저장 실패] {e}")

                    if user_input.strip() == "__ping__":
                        continue

                    if mode == "idle":
                        if "pending_edit_input" in websocket.scope:
                            curri_names = await self.curriculum_crud.get_curriculum_names_by_user(userId)
                            curri_name = await self.gpt_service.extract_curriculum_name_for_deletion(user_input,
                                                                                                     curri_names)

                            if curri_name not in curri_names:
                                message = "입력하신 커리큘럼 이름을 찾을 수 없습니다. 다시 입력해주세요."
                                await websocket.send_text(json.dumps({"message": message}))
                                await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B",
                                                                   message=message)
                                continue

                            curri_id = await self.curriculum_crud.get_curriculum_id_by_name(userId, curri_name)
                            websocket.scope["selected_curri_id"] = curri_id

                            restored_input = websocket.scope["pending_edit_input"]
                            del websocket.scope["pending_edit_input"]
                            user_input = restored_input

                        if "waiting_for_curri_selection" in websocket.scope:
                            curri_id = await self.gpt_service.extract_curriculum_id(user_input, userId)
                            if curri_id:
                                websocket.scope["selected_curri_id"] = curri_id
                                pending_input = websocket.scope["waiting_for_curri_selection"]["pending_input"]
                                del websocket.scope["waiting_for_curri_selection"]
                                user_input = pending_input
                            else:
                                message = "입력한 커리큘럼 이름을 찾을 수 없습니다. 다시 입력해주세요."
                                await websocket.send_text(json.dumps({"message": message}))
                                await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B",
                                                                   message=message)
                                continue

                        if await self.gpt_service.is_curriculum_edit_request(user_input):
                            await self.curriculum_edit_service.handle_completed_curriculum_edit(websocket, user_input)
                            continue

                        if "pending_addition" in websocket.scope:
                            await self.curriculum_edit_service.handle_pending_addition_in_edit_mode(websocket,
                                                                                                    user_input, userId)
                            continue

                        if await self.gpt_service.is_curriculum_request(user_input):
                            message = "더욱 맞춤화된 커리큘럼을 생성하기 위해,아래에서 원하는 조건을 모두 선택해 주세요.\n\n관심 분야 외의 과목은 아래 조건으로 설계됩니다.\n\n조건: 졸업, 재수강, 선호 교수, 팀플 제외"
                            await websocket.send_text(json.dumps({
                                "message": message,
                                "type": "condition_selection_prompt"
                            }))
                            await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)
                            websocket.scope["mode"] = "waiting_condition_selection"
                            mode = "waiting_condition_selection"
                            continue

                        response = await client.chat.completions.create(
                            model="gpt-4-turbo",
                            messages=[{"role": "user", "content": user_input.strip()}],
                            max_tokens=300,
                            temperature=0.7
                        )

                        message = response.choices[0].message.content.strip()

                        await websocket.send_text(json.dumps({"message": message}))
                        await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)
                        continue

                    elif mode == "waiting_condition_selection":
                        selected_conditions = await self.gpt_service.parse_conditions_with_gpt(user_input)
                        if not selected_conditions:
                            message = (
                                "조건을 인식하지 못했습니다. 예시: '졸업, 팀플 제외, 재수강'\n"
                                "가능한 조건: 졸업, 팀플 제외, 선호 교수, 재수강"
                            )
                            await websocket.send_text(json.dumps({"message": message}))
                            await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)
                            continue

                        websocket.scope["conditions"] = selected_conditions
                        print(f"[선택된 조건]: {selected_conditions}")

                        if "retake" in selected_conditions:
                            retake_elligible_grades = {"C+", "C0", "D+", "D0", "F", "NP"}
                            retake_candidates = []
                            for semester, types in completed_data.items():
                                for lec_type, lectures in types.items():
                                    for code, name, credit, grade in lectures:
                                        if grade in retake_elligible_grades:
                                            retake_candidates.append({
                                                "code": code,
                                                "name": name,
                                                "credit": credit,
                                                "grade": grade
                                            })

                            message = "이전에 수강한 강의 중 재수강이 가능한 강의 목록입니다.\n재수강하고 싶은 과목을 입력해 주세요."
                            await websocket.send_text(json.dumps({
                                "message": message,
                                "retake_candidates": retake_candidates
                            }))
                            mode = "waiting_retake_selection"
                            continue

                        message = "전공 관련 관심 분야를 입력해주세요."
                        await websocket.send_text(json.dumps({
                            "message": message,
                            "type": "waiting_major_interest"
                        }))
                        await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)
                        mode = "waiting_major_interest"
                        websocket.scope["mode"] = "waiting_major_interest"
                        continue

                    elif mode == "waiting_major_interest":
                        major_lectures, major_interest, completed_codes = await self.recommendation_service.handle_major_interest_input(
                            client, websocket, user_input, completed_names, session_id
                        )

                        if not major_lectures:
                            continue

                        websocket.scope["major_interest"] = major_interest

                        print("[전공 추천 강의] ", major_lectures)
                        message = "[전공 추천 강의 리스트]\n" + "\n".join(f"- {lec}" for lec in major_lectures)
                        message += "\n\n추천 강의에 대해 추가하거나 삭제할 강의가 있나요?\n" \
                                   "(단, 삭제한 강의가 졸업 요건을 맞추기 위해 다시 포함될 수 있습니다.)"

                        await websocket.send_text(json.dumps({"message": message, "final_lectures": major_lectures}))
                        await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)

                        websocket.scope["mode"] = "modification_major"
                        mode = "modification_major"
                        continue

                    elif mode == "modification_major":
                        result = await self.recommendation_service.handle_recommendation_modification(
                            websocket, user_input, major_lectures,
                            completed_names, completed_codes, completed_data, major_interest, userId, mode
                        )
                        if result == "next_general":
                            websocket.scope["final_major_lectures"] = major_lectures
                            message = "교양 관련 관심 분야를 입력해주세요."
                            await websocket.send_text(json.dumps({"message": message}))
                            await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)
                            websocket.scope["mode"] = "waiting_general_interest"
                            mode = "waiting_general_interest"
                        continue

                    elif mode == "waiting_retake_selection":
                        try:
                            if isinstance(user_input, str):
                                if user_input.strip().startswith("["):
                                    user_names = json.loads(user_input)
                                else:
                                    user_names = [name.strip() for name in user_input.split(",") if name.strip()]
                            else:
                                user_names = user_input

                            lecture_list = await self.lecture_crud.get_lecture_list()
                            retake_codes = await self.gpt_service.names_to_codes_by_gpt(user_names, lecture_list,
                                                                                        completed_data)
                            websocket.scope["retake_codes"] = retake_codes

                            message = "전공 관련 관심 분야를 입력해주세요."
                            await websocket.send_text(json.dumps({
                                "message": message,
                                "type": "waiting_major_interest"
                            }))
                            await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)

                            mode = "waiting_major_interest"
                            websocket.scope["mode"] = "waiting_major_interest"
                            continue

                        except Exception as e:
                            print(f"[재수강 선택 처리 에러] {e}")
                            await websocket.send_text(json.dumps({
                                "message": "재수강 과목 선택 형식이 올바르지 않습니다. 다시 시도해 주세요."
                            }))
                            continue

                    elif mode == "waiting_general_interest":
                        general_lectures, general_interest, completed_codes = await self.recommendation_service.handle_general_interest_input(
                            client, websocket, user_input, completed_names, session_id
                        )

                        if not general_lectures:
                            continue

                        websocket.scope["general_interest"] = general_interest

                        print("[교양 추천 강의] ", general_lectures)
                        message = "[교양 추천 강의 리스트]\n" + "\n".join(f"- {lec}" for lec in general_lectures)
                        message += "\n\n추천 강의에 대해 추가하거나 삭제할 강의가 있나요?\n" \
                                   "(단, 삭제한 강의가 졸업 요건을 맞추기 위해 다시 포함될 수 있습니다.)"

                        await websocket.send_text(json.dumps({"message": message, "final_lectures": general_lectures}))
                        await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)

                        websocket.scope["mode"] = "modification_general"
                        mode = "modification_general"
                        continue

                    elif mode == "modification_general":
                        result = await self.recommendation_service.handle_recommendation_modification(
                            websocket, user_input, general_lectures,
                            completed_names, completed_codes, completed_data, general_interest, userId, mode
                        )
                        websocket.scope["final_general_lectures"] = general_lectures

                        if result == "done":
                            mode = "idle"
                            continue

                except Exception as inner:
                    print(f"[서버 루프 중 예외 발생] {inner}")
                    break

        except WebSocketDisconnect:
            print("웹소켓 연결 종료")
            await self.chat_crud.end_chat_session(session_id=websocket.scope["session_id"])