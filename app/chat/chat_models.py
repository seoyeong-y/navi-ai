from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database.base import Base
from datetime import datetime


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    session_type = Column(String(50), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.now)
    ended_at = Column(DateTime)


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=False)
    chat_type = Column(String(10), nullable=False)  # 'U' or 'B'
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.now)