from sqlalchemy.ext.asyncio import AsyncSession
from app.recommendation.service.gpt_service import GPTService
from app.curriculum.service.curriculum_utils import calculate_credits
from app.utils.completed_data import *
from app.core.constants import *
from app.lecture.lecture_repository import LectureCrud
from app.lecture.lecture_service import LectureService
from app.curriculum.curriculum_repository import CurriculumCrud
from app.chat.chat_repository import ChatCrud
import json, asyncio, re
from collections import defaultdict
from app.curriculum.service.curriculum_manager import CurriculumService
from app.curriculum.service.curriculum_final_builder import build_final_curriculum
from app.utils.condition_utils import encode_conditions

class RecommendationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.lecture_crud = LectureCrud(db)
        self.lecture_service = LectureService(db)
        self.curriculum_crud = CurriculumCrud(db)
        self.chat_crud = ChatCrud(db)
        self.gpt_service = GPTService(db)  # DB 세션 주입

    async def handle_major_interest_input(self, client, websocket, user_input, completed_names, session_id, completed_data):
        resolved, unclear = await self.gpt_service.resolve_unclear_interest(user_input)
        interest = resolved
        websocket.scope["major_interest"] = interest
        print(f"[전공 관심 분야 설정] {interest}")

        if unclear:
            message = "표현이 불분명하여 기본 추천을 진행합니다."
            await self.chat_crud.save_chat_log(
                session_id=websocket.scope["session_id"],
                chat_type="B",
                message=message
            )
            await websocket.send_text(json.dumps({"message": message}))

        message = "전공 추천 강의 리스트를 생성 중입니다. \n잠시만 기다려 주세요."
        await self.chat_crud.save_chat_log(
            session_id=websocket.scope["session_id"],
            chat_type="B",
            message=message
        )
        await websocket.send_text(json.dumps({"message": message}))

        (total_credits, major_credits, general_credits, field_practice_credits,
         major_required_credits_earned, original_codes) = calculate_credits(completed_data)

        completed_codes = await self.lecture_crud.get_all_completed_codes_with_replacement(original_codes)

        for semester in completed_data.values():
            for lectures in semester.values():
                for _, name, _, _, status in lectures:
                    completed_names.add(name)

        major_lectures = await self.lecture_service.fetch_major_lectures()
        major_lectures = [lec for lec in major_lectures if "(SDU)" not in lec and lec not in completed_names]
        major_lectures_str = "\n".join(major_lectures)

        prompt = f"""
        사용자가 입력한 관심 분야에 맞는 전공 선택(ME) 강의를 추천해주세요.
        강의 개요와 강의 목표를 참고하여 관련성이 높은 강의만 추천해야 합니다.
        추천된 강의는 가장 관련성이 높은 강의만 추천해야 하며, 우리 대학의 전공 선택 강의 목록만 사용해야 합니다.
        다음은 전공 선택 강의 목록입니다. (SDU 과목은 제외하고, 관련성 높은 강의만 뽑아주세요)

        {major_lectures_str}

        사용자 입력: "{user_input}"

        추천 강의 리스트:
        1. 가장 관련성이 높은 강의를 우선으로 추천해주세요.
        2. 관련성이 높다고 판단되는 강의는 제한 없이 모두 추천해주세요. 단, 너무 낮은 관련성의 강의는 제외해주세요.
        3. 강의 수는 사용자 입력에 가장 관련성이 높은 강의들로만 제한되어야 합니다.
        4. 추천 강의는 가장 관련성이 높은 순으로 정렬해주세요.
        5. 추천 강의 개요 및 목표도 고려하여 추천해주세요. 대신 출력은 강의명만 해주세요.

        강의 추천 결과:
        """

        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.7
        )

        gpt_response = response.choices[0].message.content.strip()

        recommended_lectures = [
            lec.strip().replace("'", "").split(". ")[-1]
            for lec in gpt_response.split("\n") if lec.strip()
        ]

        major_lecture_infos = await self.lecture_service.fetch_lecture_infos_for_recommendation()

        filtered_lectures = await self.gpt_service.filter_recommended_lectures_by_description(
            recommended_lectures, major_lecture_infos, interest
        )

        valid_major_lectures = set(await self.lecture_service.fetch_major_lectures())
        filtered_lectures = [lec for lec in filtered_lectures if lec in valid_major_lectures]

        print("[입력된 관심 분야]:", user_input)
        print("[GPT 1차 추천 강의]:", recommended_lectures)
        print("[GPT 필터링 결과]:", filtered_lectures)

        return filtered_lectures, interest, completed_codes

    async def handle_general_interest_input(self, client, websocket, user_input, completed_names, session_id, completed_data):
        resolved, unclear = await self.gpt_service.resolve_unclear_interest(user_input)
        interest = resolved
        websocket.scope["general_interest"] = interest
        print(f"[교양 관심 분야 설정] {interest}")

        if unclear:
            message = "표현이 불분명하여 기본 추천을 진행합니다."
            await self.chat_crud.save_chat_log(
                session_id=websocket.scope["session_id"],
                chat_type="B",
                message=message
            )
            await websocket.send_text(json.dumps({"message": message}))

        message = "교양 추천 강의 리스트를 생성 중입니다. \n잠시만 기다려 주세요."
        await self.chat_crud.save_chat_log(
            session_id=websocket.scope["session_id"],
            chat_type="B",
            message=message
        )
        await websocket.send_text(json.dumps({"message": message}))

        (total_credits, major_credits, general_credits, field_practice_credits,
         major_required_credits_earned, original_codes) = calculate_credits(completed_data)

        completed_codes = await self.lecture_crud.get_all_completed_codes_with_replacement(original_codes)

        for semester in completed_data.values():
            for lectures in semester.values():
                for _, name, _, _, status in lectures:
                    completed_names.add(name)

        general_lectures = await self.lecture_service.fetch_general_lectures()
        general_lectures = [lec for lec in general_lectures if "(SDU)" not in lec and lec not in completed_names]
        general_lectures_str = "\n".join(general_lectures)

        prompt = f"""
        사용자가 입력한 관심 분야에 맞는 교양 선택(GE) 강의를 추천해주세요.
        강의 개요와 강의 목표를 참고하여 관련성이 높은 강의만 추천해야 합니다.
        추천된 강의는 우리 대학의 교양 선택 강의 목록만 사용해야 합니다.

        다음은 교양 선택 강의 목록입니다. (SDU 과목은 제외하고, 관련성 높은 강의만 뽑아주세요)

        {general_lectures_str}

        사용자 입력: "{user_input}"

        추천 강의 리스트:
        1. 가장 관련성이 높은 강의를 우선으로 추천해주세요.
        2. 관련성이 높다고 판단되는 강의는 제한 없이 모두 추천해주세요. 단, 너무 낮은 관련성의 강의는 제외하고, 최대 10개만 추천해 주세요.
        3. 강의 수는 사용자 입력에 가장 관련성이 높은 강의들로만 제한되어야 합니다.
        4. 추천 강의는 가장 관련성이 높은 순으로 정렬해주세요.
        5. 추천 강의 개요 및 목표도 고려하여 추천해주세요. 대신 출력은 강의명만 해주세요.

        강의 추천 결과:
        """

        response = await client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.7
        )

        gpt_response = response.choices[0].message.content.strip()

        recommended_lectures = [
            lec.strip().replace("'", "").split(". ")[-1]
            for lec in gpt_response.split("\n") if lec.strip()
        ]

        def normalize(text):
            return re.sub(r'\s+', '', text.lower())

        valid_general_lectures = set(await self.lecture_service.fetch_general_lectures())
        normalized_valids = {normalize(name): name for name in valid_general_lectures}

        filtered_lectures = []
        for lec in recommended_lectures:
            norm = normalize(lec)
            if norm in normalized_valids:
                filtered_lectures.append(normalized_valids[norm])

        print("gpt 추천 결과:", recommended_lectures)
        print("강의 개요와 목표에 따른 필터링 결과:", filtered_lectures)

        return filtered_lectures, interest, completed_codes

    async def handle_recommendation_modification(self, websocket, user_input, final_lectures, completed_names, completed_codes, completed_data, interest, userId, mode):
        try:
            if await self.gpt_service.is_no_more_modification(user_input):
                if websocket.scope.get("mode") == "modification_major":
                    return "next_general"
                else:
                    websocket.scope["final_general_lectures"] = final_lectures

                    print("커리큘럼 생성 시작")
                    message = "추천 커리큘럼을 생성 중입니다. \n잠시만 기다려 주세요."
                    await self.chat_crud.save_chat_log(
                        session_id=websocket.scope["session_id"],
                        chat_type="B",
                        message=message
                    )
                    await websocket.send_text(json.dumps({"message": message}))

                    print("get_lecture_list() 호출 준비")
                    lecture_list = await self.lecture_crud.get_lecture_list()
                    print(f">>> 전체 강의 수: {len(lecture_list)}")

                    if lecture_list:
                        print(f">>> lecture_list 첫 번째 항목 길이: {len(lecture_list[0])}")
                        print(f">>> lecture_list 첫 번째 항목: {lecture_list[0]}")

                    student_grade = 3
                    student_semester = 1

                    completed_names = set()
                    for semester in completed_data.values():
                        for lectures in semester.values():
                            for _, name, _, _, status in lectures:
                                completed_names.add(name)

                    major_recommendations = websocket.scope.get("final_major_lectures", [])
                    general_recommendations = websocket.scope.get("final_general_lectures", [])

                    print("final-general: ", general_recommendations)

                    try:
                        curriculum, total_credits, filtered_lecture_list = await build_final_curriculum(
                            completed_data=completed_data,
                            completed_codes=completed_codes,
                            completed_names=completed_names,
                            lecture_list=lecture_list,
                            major_recommendations=major_recommendations,
                            general_recommendations=general_recommendations,
                            student_grade=student_grade,
                            student_semester=student_semester,
                            major_interest=websocket.scope.get("major_interest", []),
                            general_interest=websocket.scope.get("general_interest", []),
                            conditions=websocket.scope.get("conditions", []),
                            retake_codes=websocket.scope.get("retake_codes", []),
                            db=self.db
                        )
                    except Exception as e:
                        print(f"[build_final_curriculum 에러] {e}")
                        print(f"[에러 타입] {type(e)}")
                        import traceback
                        print(f"[전체 스택 트레이스] {traceback.format_exc()}")
                        raise e

                    print("커리큘럼 설계 완료")

                    curriculum_service = CurriculumService(self.db)
                    curriculum_name = await curriculum_service.generate_curriculum_name(userId=userId)

                    major_interest = websocket.scope.get("major_interest", [])
                    general_interest = websocket.scope.get("general_interest", [])

                    full_interest = []
                    if isinstance(major_interest, list):
                        full_interest += major_interest
                    if isinstance(general_interest, list):
                        full_interest += general_interest

                    exclusion_phrase = "컴퓨터공학부 학생들이 가장 쉽게 접하는 분야"

                    filtered_interest = [interest for interest in full_interest if exclusion_phrase not in interest]

                    description = ", ".join(sorted(set(map(str.strip, filtered_interest))))
                    conditions_string = encode_conditions(websocket.scope.get("conditions", []))

                    curri_id = await self.curriculum_crud.save_curriculum(
                        userId=userId,
                        name=curriculum_name,
                        total_credits=total_credits,
                        description=description,
                        conditions=conditions_string
                    )

                    completed_lecture_list = []
                    for semester, types in completed_data.items():
                        year, sem = semester.split()
                        semester_val = '1' if sem == "1학기" else '2'
                        for type_key, lec_list in types.items():
                            for code, name, credit, record_grade, status in lec_list:
                                lec_type = (
                                    'GR' if type_key in ['교필', 'GR'] else
                                    'GE' if type_key in ['교선', 'GE'] else
                                    'MR' if type_key in ['전필', 'MR'] else
                                    'ME' if type_key in ['전선', 'ME'] else
                                    'RE' if type_key in ['현장연구', 'RE'] else
                                    'FE'
                                )

                                grade = year.strip()[0]
                                completed_lecture_list.append((name, credit, lec_type, grade, semester_val, '', '', '', code, '', status))

                    lecture_name_to_code = {name: code for name, _, _, _, _, _, _, _, code, _ in lecture_list}

                    final_lecture_list = []
                    for semester_key, lectures in curriculum.items():
                        year, sem = semester_key.split("학년 ")
                        grade = year.strip()[0]
                        semester = sem.replace("학기", "")

                        for name, credit, lec_type in lectures:
                            code = lecture_name_to_code.get(name, '')

                            status = "planned"

                            if int(grade) == student_grade and int(semester) == student_semester:
                                status = "current"

                            final_lecture_list.append((name, credit, lec_type, grade, semester, '', '', '', code, '', status))

                    print("save-filter:", filtered_lecture_list)
                    print("save-final:", final_lecture_list)

                    def remove_duplicate_lectures(lectures):
                        seen = set()
                        filtered = []
                        for lec in lectures:
                            key = (lec[0], lec[3], lec[4])
                            if key not in seen:
                                seen.add(key)
                                filtered.append(lec)
                        return filtered

                    unique_lectures = remove_duplicate_lectures(completed_lecture_list + filtered_lecture_list)
                    await self.curriculum_crud.save_curri_lectures(curri_id, unique_lectures)

                    major_credits = sum(
                        credit
                        for semester_courses in curriculum.values()
                        for _, credit, lec_type in semester_courses
                        if lec_type in ("MR", "ME")
                    )
                    general_credits = sum(
                        credit
                        for semester_courses in curriculum.values()
                        for _, credit, lec_type in semester_courses
                        if lec_type in ("GR", "GE")
                    )
                    total = total_credits

                    summary_message = (
                        f"커리큘럼 설계가 완료되었습니다.\n\n"
                        f"- 총 학점: {total}학점\n"
                        f"- 전공 학점: {major_credits}학점\n"
                        f"- 교양 학점: {general_credits}학점\n\n"
                        f"커리큘럼 페이지에서 자세히 확인할 수 있습니다."
                    )

                    print(summary_message)
                    semester_totals = defaultdict(int)
                    for semester, lectures in curriculum.items():
                        semester_totals[semester] = sum(credit for _, credit, _ in lectures)

                    for semester in sorted(semester_totals.keys(),
                                           key=lambda k: (int(k.split("학년")[0]), int(k.split("학기")[0][-1]))):
                        print(f"- {semester}: {semester_totals[semester]}학점")

                    await self.chat_crud.save_chat_log(
                        session_id=websocket.scope["session_id"],
                        chat_type="B",
                        message=summary_message
                    )

                    await websocket.send_text(json.dumps({
                        "message": summary_message,
                        "status": "done"
                    }))
                    return "done"

            if mode == "modification_general":
                print("modification_general 진입")
                lecture_pool_full = await self.lecture_service.fetch_general_lectures()
                print(f"lecture_pool_raw: {lecture_pool_full}")
                lecture_pool = [lec[0] if isinstance(lec, (list, tuple)) else lec for lec in lecture_pool_full]
                print(f"lecture_pool parsed: {lecture_pool[:10]}")
            else:
                lecture_pool = await self.lecture_service.fetch_major_lectures()
                interest = websocket.scope.get("major_interest", [])

            try:
                deleted_lectures = list(set(lecture_pool) - set(final_lectures))

                if await self.gpt_service.is_requesting_alternative_recommendation(user_input, deleted_lectures):
                    print("requesting")
                    new_interest, unclear = await self.gpt_service.resolve_unclear_interest(user_input)

                    if isinstance(interest, str):
                        interest = [kw.strip() for kw in interest.split(",")]

                    if new_interest:
                        for kw in new_interest:
                            kw = kw.strip()
                            if kw and kw not in interest:
                                interest.append(kw)
                        print(f"[업데이트된 관심 분야] {interest}")

                        if mode == "modification_general":
                            websocket.scope["general_interest"] = interest
                        else:
                            websocket.scope["major_interest"] = interest

                    print("suggest 실행")

                    alternative_lectures = await self.gpt_service.suggest_other_similar_lectures(
                        user_input=user_input,
                        deleted_lectures=deleted_lectures,
                        interest=interest,
                        available_lectures=lecture_pool
                    )

                    filtered = []
                    for lec in alternative_lectures:
                        if lec not in final_lectures:
                            final_lectures.append(lec)
                            filtered.append(lec)

                    if filtered:
                        filtered_names = ", ".join(filtered)
                        message = f"{filtered_names} 강의가 추천되었습니다:\n\n"

                        print(final_lectures)
                        lecture_list_message = "[추천 강의 리스트]\n" + "\n".join(f"- {lec}" for lec in final_lectures)
                        ask_message = "\n\n추천 강의에 대해 추가하거나 삭제할 강의가 있나요?\n" \
                                  "(단, 삭제한 강의가 졸업 요건을 맞추기 위해 다시 포함될 수 있습니다.)"

                        full_message = message + lecture_list_message + ask_message

                        await websocket.send_text(json.dumps({
                            "message": full_message,
                            "final_lectures": final_lectures
                        }))

                        await asyncio.sleep(0.1)

                        await self.chat_crud.save_chat_log(
                            session_id=websocket.scope["session_id"],
                            chat_type="B",
                            message=full_message
                        )
                        return False

                    else:
                        print(final_lectures)
                        message = "삭제된 강의 대신 추천할 수 있는 강의를 찾지 못했습니다.\n\n"
                        lecture_list_message = "[추천 강의 리스트]\n" + "\n".join(f"- {lec}" for lec in final_lectures)
                        ask_message = "\n\n추천 강의에 대해 추가하거나 삭제할 강의가 있나요?\n" \
                                    "(단, 삭제한 강의가 졸업 요건을 맞추기 위해 다시 포함될 수 있습니다.)"

                        full_message = message + lecture_list_message + ask_message

                        await websocket.send_text(json.dumps({
                            "message": full_message,
                            "final_lectures": final_lectures
                        }))

                        await self.chat_crud.save_chat_log(
                            session_id=websocket.scope["session_id"],
                            chat_type="B",
                            message=message
                        )
                        return False
            except Exception as e:
                    print(f"[대체 추천 요청 판단 중 오류] {e}")
                    return False

            add_list, remove_list = await self.gpt_service.parse_add_remove_lectures(user_input, final_lectures, lecture_pool)

            new_interest, _ = await self.gpt_service.resolve_unclear_interest(user_input)

            if new_interest:
                if isinstance(interest, str):
                    interest = [kw.strip() for kw in interest.split(",")]
                for kw in new_interest:
                    kw = kw.strip()
                    if kw and kw not in interest:
                        interest.append(kw)
                print(f"[관심 분야 업데이트] {interest}")

                if mode == "modification_general":
                    websocket.scope["general_interest"] = interest
                else:
                    websocket.scope["major_interest"] = interest

            for lec in remove_list:
                matched = next((f for f in final_lectures if f.replace(" ", "").lower() == lec.replace(" ", "").lower()), None)
                if matched:
                    final_lectures.remove(matched)
                else:
                    print(f"[삭제 실패] remove 요청 '{lec}'는 final_lectures에서 찾을 수 없습니다.")

            for lec in add_list:
                similar = await self.gpt_service.find_similar_lecture_by_gpt(lec, lecture_pool)
                if similar and similar not in final_lectures:
                    final_lectures.append(similar)

            print("[GPT add/remove 결과]", {"add": add_list, "remove": remove_list})

            action_message = ""
            if remove_list:
                action_message += " '" + "', '".join(remove_list) + "' 강의가 삭제되었습니다."
            if add_list:
                if action_message:
                    action_message += " "
                action_message += " '" + "', '".join(add_list) + "' 강의가 추가되었습니다."

            print(final_lectures)
            lecture_list_message = "[추천 강의 리스트]\n" + "\n".join(f"- {lec}" for lec in final_lectures)
            ask_message = "\n\n추천 강의에 대해 추가하거나 삭제할 강의가 있나요?\n" \
                    "(단, 삭제한 강의가 졸업 요건을 맞추기 위해 다시 포함될 수 있습니다.)"

            if action_message:
                full_message = action_message.strip() + "\n\n" + lecture_list_message + ask_message
            else:
                full_message = lecture_list_message + ask_message

            try:
                await websocket.send_text(json.dumps({
                    "message": full_message,
                    "final_lectures": final_lectures
                }))
            except Exception as e:
                print(f"[websocket 전송 실패] {e}")

            try:
                await self.chat_crud.save_chat_log(
                    session_id=websocket.scope["session_id"],
                    chat_type="B",
                    message=full_message
                )
            except Exception as e:
                print(f"[save_chat_log 실패] {e}")

            print("[handle_recommendation_modification 끝] return False 실행됨")
            return False

        except Exception as e:
            print(f"[handle_recommendation_modification 예외] {e}")
            import traceback
            print(f"[전체 스택 트레이스] {traceback.format_exc()}")
            return False