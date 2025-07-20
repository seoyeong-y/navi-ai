from sqlalchemy.ext.asyncio import AsyncSession
from app.chat.chat_models import ChatSession, ChatLog
from datetime import datetime
from typing import Optional

class ChatCrud:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 채팅 세션 생성
    async def create_chat_session(self, user_id: int, session_type: str) -> int:
        session = ChatSession(
            user_id=user_id,
            session_type=session_type,
            started_at=datetime.now()
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session.id

    # 채팅 세션 종료
    async def end_chat_session(self, session_id: int):
        session = await self.db.get(ChatSession, session_id)
        if session:
            session.ended_at = datetime.now()
            await self.db.commit()

    # 채팅 로그 저장
    async def save_chat_log(self, session_id: int, chat_type: str, message: str):
        log = ChatLog(
            session_id=session_id,
            chat_type=chat_type,
            message=message,
            timestamp=datetime.now()
        )
        self.db.add(log)
        await self.db.commit()

    # ID로 채팅 세션 조회
    async def get_chat_session_by_id(self, session_id: int) -> Optional[ChatSession]:
        return await self.db.get(ChatSession, session_id)