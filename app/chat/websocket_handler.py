import httpx
from fastapi import WebSocket, WebSocketDisconnect
import openai
import json
import os
from dotenv import load_dotenv
from jose import jwt, JWTError
from openai.types.chat import ChatCompletionUserMessageParam
from sqlalchemy.ext.asyncio import AsyncSession
from app.chat.chat_repository import ChatCrud
from app.curriculum.curriculum_repository import CurriculumCrud
from app.lecture.lecture_repository import LectureCrud
from app.lecture.lecture_service import LectureService
from app.professor.professor_repository import ProfessorCrud
from app.recommendation.service.gpt_service import GPTService
from app.recommendation.service.recommendation_service import RecommendationService
from app.curriculum.service.curriculum_edit_service import CurriculumEditService
from app.utils.completed_data import get_completed_data
from app.curriculum.service.curriculum_manager import CurriculumService
from app.curriculum.service.retake_service import RetakeService

load_dotenv()

GPT_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.AsyncOpenAI(
    api_key=GPT_API_KEY,
    http_client=httpx.AsyncClient()
)

SECRET_KEY = os.getenv("JWT_SECRET", "your_jwt_secret")
ALGORITHM = "HS256"

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
        self.retake_service = RetakeService(db)

    async def handle_websocket(self, websocket: WebSocket):
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001)
            return

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            userId = int(payload.get("userId"))
        except JWTError:
            await websocket.close(code=4002)
            return

        await websocket.accept()

        existing_session = await self.chat_crud.get_latest_session_by_user(userId)
        if existing_session and existing_session.end_time is None:
            session_id = existing_session.id
        else:
            session_id = await self.chat_crud.create_chat_session(
                userId=userId, session_type="curriculum"
            )

        websocket.scope["session_id"] = session_id
        websocket.scope["view_mode"] = "list"
        websocket.scope["selected_curri_id"] = None

        await websocket.send_text(json.dumps({
            "type": "session",
            "sessionId": session_id
        }))

        mode = "idle"
        major_lectures = []
        general_lectures = []
        major_interest = None
        general_interest = None
        completed_codes = set()
        completed_names = set()
        completed_data = await get_completed_data(self.db, userId)
        retake_service = RetakeService(self.db)

        try:
            while True:
                try:
                    print(">>> 메시지 수신 대기 중")
                    user_input = await websocket.receive_text()
                    if not user_input.strip():
                        continue
                    print(f"[입력 수신] {user_input}")

                    try:
                        await self.chat_crud.save_chat_log(session_id=session_id, chat_type="U", message=user_input)
                    except Exception as e:
                        print(f"[사용자 메시지 저장 실패] {e}")

                    if user_input.strip() in ["__ping__", "init"]:
                        print(f"[DEBUG] Init/Ping received for userId={userId}, 응답 전송 안 함")
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
                            messages=[
                                ChatCompletionUserMessageParam(
                                    role="user",
                                    content=user_input.strip()
                                )
                            ],
                            max_tokens=300,
                            temperature=0.7
                        )

                        message = response.choices[0].message.content.strip()

                        await websocket.send_text(json.dumps({"message": message}))
                        await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B", message=message)
                        continue

                    elif mode == "waiting_condition_selection":
                        print(f"[DEBUG] 조건 파싱 시작, 입력: {user_input}")
                        selected_conditions = await self.gpt_service.parse_conditions_with_gpt(user_input)
                        print(f"[DEBUG] 파싱 결과: {selected_conditions}")
                        print(f"[DEBUG] 타입: {type(selected_conditions)}")

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
                            print(f"[DEBUG] 재수강 조건 감지, userId={userId}")
                            retake_candidates = await retake_service.get_retake_eligible_courses(userId)
                            websocket.scope["retake_candidates"] = retake_candidates
                            print(f"[DEBUG] 재수강 목록: {retake_candidates}")

                            if retake_candidates:
                                message = "이전에 수강한 강의 중 재수강이 가능한 강의 목록입니다.\n재수강하고 싶은 과목을 입력해 주세요."
                                await websocket.send_text(json.dumps({
                                    "message": message,
                                    "retake_candidates": retake_candidates
                                }))
                                await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B",
                                                                   message=message)
                                mode = "waiting_retake_selection"
                            else:
                                message = "현재 재수강 가능한 과목이 없습니다. 다음 단계로 넘어가겠습니다.\n전공 관련 관심 분야를 입력해주세요."
                                await websocket.send_text(json.dumps({"message": message}))
                                await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B",
                                                                   message=message)
                                mode = "waiting_major_interest"
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
                            client, websocket, user_input, completed_names, session_id, completed_data, userId
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
                            print(f"[DEBUG] waiting_retake_selection user_input raw: {user_input} ({type(user_input)})")
                            try:
                                if not user_input or user_input.strip() in ["", "[]"]:
                                    user_inputs = []

                                else:
                                    user_inputs = json.loads(user_input)
                                    if isinstance(user_inputs, str):
                                        user_inputs = [user_inputs]

                            except json.JSONDecodeError:
                                user_inputs = [name.strip() for name in user_input.split(",") if name.strip()]

                            print(f"[DEBUG] 파싱 결과 user_inputs = {user_inputs} ({type(user_inputs)})")

                            if not user_inputs:
                                websocket.scope["retake_codes"] = []
                                message = "전공 관련 관심 분야를 입력해주세요."
                                await websocket.send_text(json.dumps({
                                    "message": message,
                                    "type": "waiting_major_interest"
                                }))

                                await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B",
                                                                   message=message)
                                mode = "waiting_major_interest"
                                websocket.scope["mode"] = "waiting_major_interest"
                                continue

                            try:
                                retake_candidates = websocket.scope.get("retake_candidates")
                                code_to_name = {c["code"]: c["name"] for c in (retake_candidates or [])}

                                retake_codes = []
                                invalid_codes = []

                                for item in user_inputs:
                                    if item in code_to_name:
                                        resolved = await self.retake_service.resolve_final_code(item)

                                        if resolved:
                                            retake_codes.append(resolved)

                                        else:
                                            invalid_codes.append(item)

                                    else:
                                        lecture_list = await self.lecture_crud.get_lecture_list()
                                        mapped = await self.gpt_service.names_to_codes_by_gpt(
                                            [item], lecture_list, completed_data
                                        )

                                        for code in mapped:
                                            resolved = await self.retake_service.resolve_final_code(code)
                                            if resolved:
                                                retake_codes.append(resolved)
                                            else:
                                                invalid_codes.append(code)

                                if invalid_codes:
                                    msg = f"다음 과목은 폐지되어 재수강이 불가합니다: {', '.join(invalid_codes)}"
                                    await websocket.send_text(json.dumps({"message": msg}))
                                    await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B",
                                                                       message=msg)
                                if retake_codes:
                                    websocket.scope["retake_codes"] = list(set(retake_codes))
                                    message = "전공 관련 관심 분야를 입력해주세요."

                                else:
                                    message = "선택한 과목들은 모두 재수강이 불가합니다. 다음 단계로 넘어갑니다.\n전공 관련 관심 분야를 입력해주세요."

                                await websocket.send_text(json.dumps({
                                    "message": message,
                                    "type": "waiting_major_interest"
                                }))

                                await self.chat_crud.save_chat_log(session_id=session_id, chat_type="B",
                                                                   message=message)
                                mode = "waiting_major_interest"
                                websocket.scope["mode"] = "waiting_major_interest"
                                continue

                            except Exception as e:
                                print(f"[재수강 후처리 에러] user_inputs={user_inputs}, error={e}")
                                await websocket.send_text(json.dumps({
                                    "message": f"재수강 처리 중 오류가 발생했습니다: {str(e)}"
                                }))
                                continue

                        except Exception as e:
                            print(f"[재수강 선택 처리 에러] raw={user_input}, error={e}")
                            await websocket.send_text(json.dumps({
                                "message": "재수강 과목 입력을 이해하지 못했습니다. 예: ACS20010, 자료구조"
                            }))
                            continue

                    elif mode == "waiting_general_interest":
                        general_lectures, general_interest, completed_codes = await self.recommendation_service.handle_general_interest_input(
                            client, websocket, user_input, completed_names, session_id, completed_data, userId
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