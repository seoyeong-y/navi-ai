from fastapi import WebSocket
import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.curriculum.curriculum_repository import CurriculumCrud
from app.lecture.lecture_repository import LectureCrud
from app.chat.chat_repository import ChatCrud
from app.recommendation.service.gpt_service import GPTService
from sqlalchemy import select
from app.lecture.lecture_models import RecentLecture
from sqlalchemy import delete, update
from app.curriculum.curriculum_models import CurriLecture


class CurriculumEditService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.curriculum_crud = CurriculumCrud(db)
        self.lecture_crud = LectureCrud(db)
        self.chat_crud = ChatCrud(db)
        self.gpt_service = GPTService(db)  # DB 세션 주입

    async def handle_completed_curriculum_edit(self, websocket: WebSocket, user_input: str):
        curri_id = websocket.scope.get("selected_curri_id")

        if not curri_id:
            websocket.scope["waiting_for_curri_selection"] = {
                "pending_input": user_input
            }
            message = "어떤 커리큘럼에 적용할까요? 커리큘럼명을 입력해주세요."
            await websocket.send_text(json.dumps({
                "message": message,
                "ask_curriculum_selection": True
            }))
            await self.chat_crud.save_chat_log(session_id=websocket.scope["session_id"], chat_type="B", message=message)
            return

        edit_result = await self.gpt_service.parse_curriculum_edit_command(user_input, curri_id)
        action = edit_result.get("action")

        if action == "remove":
            lecture_name = edit_result.get("lecture_name")
            success = await self.delete_lecture_from_curriculum(curri_id, lecture_name)
            message = f"강의 '{lecture_name}'을 삭제했습니다." if success else f"삭제 실패: '{lecture_name}'을 찾을 수 없습니다."
            await websocket.send_text(json.dumps({"message": message}))
            await self.chat_crud.save_chat_log(
                session_id=websocket.scope["session_id"],
                chat_type="B",
                message=message
            )
            return

        elif action == "move":
            lecture_name = edit_result.get("lecture_name")
            target_grade = edit_result.get("target_grade")
            target_semester = edit_result.get("target_semester")
            success = await self.move_lecture_to_semester(curri_id, lecture_name, target_grade, target_semester)
            message = f"'{lecture_name}'을 {target_grade}학년 {target_semester}학기로 이동했습니다." if success else f"이동 실패: '{lecture_name}'을 찾을 수 없습니다."
            await websocket.send_text(json.dumps({"message": message}))
            await self.chat_crud.save_chat_log(
                session_id=websocket.scope["session_id"],
                chat_type="B",
                message=message
            )
            return

        elif action == "add":
            lecture_name = edit_result.get("lecture_name")
            target_grade = edit_result.get("target_grade")
            target_semester = edit_result.get("target_semester")

            all_lectures = await self.fetch_all_lectures()
            similar_lecture = await self.gpt_service.find_similar_lecture_by_gpt(lecture_name, all_lectures)

            prerequisites = await self.gpt_service.get_prerequisites_and_required_knowledge_by_name(similar_lecture)

            prerequisites = [lec for lec in prerequisites if lec != similar_lecture]

            message = f"요청하신 강의와 선이수 과목 리스트입니다.\n\n"
            message += "\n".join(["- " + name for name in [similar_lecture] + prerequisites])
            message += "\n\n추가 시 모두 커리큘럼에 추가됩니다.\n추가할까요?"

            await websocket.send_text(json.dumps({
                "message": message,
                "confirm_addition": True,
                "suggested_name": similar_lecture,
                "prerequisites": prerequisites,
                "target_grade": target_grade,
                "target_semester": target_semester
            }))

            await self.chat_crud.save_chat_log(
                session_id=websocket.scope["session_id"],
                chat_type="B",
                message=message
            )

            websocket.scope["pending_addition"] = {
                "suggested_name": similar_lecture,
                "main_lecture": similar_lecture,
                "related_lectures": prerequisites,
                "target_grade": target_grade,
                "target_semester": target_semester
            }
            return

        else:
            await websocket.send_text(json.dumps({
                "message": "수정할 내용을 다시 입력해주세요. (강의 추가/삭제/이동 지원)"
            }))
            return

    async def handle_pending_addition_in_edit_mode(self, websocket: WebSocket, user_input: str, user_id: int):
        curri_id = websocket.scope.get("selected_curri_id")

        if not curri_id:
            message = "커리큘럼을 선택해주세요."
            await websocket.send_text(json.dumps({"message": message}))
            return False

        if "pending_addition" in websocket.scope:
            suggested_name = websocket.scope["pending_addition"]["suggested_name"]
            target_grade = websocket.scope["pending_addition"]["target_grade"]
            target_semester = websocket.scope["pending_addition"]["target_semester"]

            if await self.gpt_service.is_user_confirming_addition(user_input):
                lecture_info = await self.lecture_crud.get_lecture_by_name(suggested_name)
                if lecture_info:
                    lec_grade = lecture_info[3]
                    lec_semester = lecture_info[4]

                    final_grade = target_grade if target_grade else lec_grade
                    final_semester = target_semester if target_semester else lec_semester

                    success = await self.insert_lecture_to_curriculum(curri_id, lecture_info, target_grade,
                                                                      target_semester)
                    message = f"{suggested_name}을 {final_grade}학년 {final_semester}학기에 추가했습니다." if success else f"추가 실패: DB 처리 오류"
                else:
                    message = f"추가 실패: {suggested_name} 강의를 찾을 수 없습니다."
            else:
                message = f"추가에 실패하였습니다. 다른 강의를 원하시면 다시 말씀해주세요."

            await websocket.send_text(json.dumps({"message": message}))
            await self.chat_crud.save_chat_log(
                session_id=websocket.scope["session_id"],
                chat_type="B",
                message=message
            )
            del websocket.scope["pending_addition"]

        return True

    async def insert_lecture_to_curriculum(self, curri_id: int, lecture_info: tuple, grade: str, semester: str) -> bool:
        name, credits, lec_type, lec_grade, lec_semester, _, _, code, _ = lecture_info

        final_grade = grade if grade else lec_grade
        final_semester = semester if semester else lec_semester

        if not final_grade or not final_semester:
            print(f"[삽입 실패] 학년 또는 학기가 None입니다: grade={final_grade}, semester={final_semester}")
            return False

        code_id_map = await self.lecture_crud.get_lecture_code_id_map()
        if code not in code_id_map:
            print(f"[삽입 실패] '{code}'에 해당하는 lecture_code.id를 찾을 수 없습니다.")
            return False

        lect_id = code_id_map[code]

        # CurriLecture 모델을 사용하여 삽입
        curri_lecture = CurriLecture(
            curri_id=curri_id,
            lect_id=lect_id,
            name=name,
            credits=credits,
            semester=final_semester,
            type=lec_type,
            grade=final_grade
        )

        try:
            self.db.add(curri_lecture)
            await self.db.commit()
            return True
        except Exception as e:
            print(f"[DB Insert 오류] {e}")
            await self.db.rollback()
            return False

    async def delete_lecture_from_curriculum(self, curri_id: int, lecture_name: str) -> bool:
        stmt = delete(CurriLecture).where(
            CurriLecture.curri_id == curri_id,
            CurriLecture.name == lecture_name
        )

        try:
            result = await self.db.execute(stmt)
            await self.db.commit()
            return result.rowcount > 0
        except Exception as e:
            print(f"[DB Delete 오류] {e}")
            await self.db.rollback()
            return False

    async def move_lecture_to_semester(self, curri_id: int, lecture_name: str, grade: str, semester: str) -> bool:
        stmt = update(CurriLecture).where(
            CurriLecture.curri_id == curri_id,
            CurriLecture.name == lecture_name
        ).values(grade=grade, semester=semester)

        try:
            result = await self.db.execute(stmt)
            await self.db.commit()
            return result.rowcount > 0
        except Exception as e:
            print(f"[DB Update 오류] {e}")
            await self.db.rollback()
            return False

    async def fetch_all_lectures(self):
        stmt = select(RecentLecture.name).where(
            RecentLecture.type.in_(['ME', 'MR'])
        ).group_by(RecentLecture.name)

        try:
            result = await self.db.execute(stmt)
            return [row.name.strip() for row in result]
        except Exception as e:
            print(f"[강의 목록 조회 오류] {e}")
            return []