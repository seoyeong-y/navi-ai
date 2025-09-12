from sqlalchemy.ext.asyncio import AsyncSession
from app.chat.chat_models import ChatSession, ChatLog
from datetime import datetime
from typing import Optional
from sqlalchemy import select, desc


class ChatCrud:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 전체 히스토리 조회
    async def get_chat_history_by_user(self, userId: int, limit: int = 1000):
        result = await self.db.execute(
            select(ChatLog)
            .join(ChatSession, ChatLog.session_id == ChatSession.id)
            .where(ChatSession.userId == userId)
            .order_by(ChatLog.timestamp.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_chat_history_by_session(self, sessionId: int, limit: int = 1000):
        result = await self.db.execute(
            select(ChatLog)
            .where(ChatLog.session_id == sessionId)
            .order_by(ChatLog.timestamp.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_latest_session_by_user(self, userId: int) -> Optional[ChatSession]:
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.userId == userId)
            .order_by(desc(ChatSession.start_time))
            .limit(1)
        )
        return result.scalars().first()

    # 채팅 세션 생성
    async def create_chat_session(self, userId: int, session_type: str) -> int:
        session = ChatSession(
            userId=userId,
            session_type=session_type,
            start_time=datetime.now()
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session.id

    # 채팅 세션 종료
    async def end_chat_session(self, session_id: int):
        session = await self.db.get(ChatSession, session_id)
        if session:
            session.end_time = datetime.now()
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