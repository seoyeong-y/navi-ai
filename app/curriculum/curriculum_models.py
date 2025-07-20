from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database.base import Base
from datetime import datetime


class Curriculum(Base):
    __tablename__ = "curriculums"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    total_credits = Column(Integer, nullable=False)
    description = Column(Text)

    lectures = relationship("CurriLecture", back_populates="curriculum")


class CurriLecture(Base):
    __tablename__ = "curri_lectures"

    id = Column(Integer, primary_key=True, index=True)
    curri_id = Column(Integer, ForeignKey("curriculums.id"))
    lect_id = Column(Integer, ForeignKey("lecture_code.id"))
    name = Column(String(255), nullable=False)
    credits = Column(Integer, nullable=False)
    semester = Column(String(10))
    type = Column(String(10))
    grade = Column(String(10))

    curriculum = relationship("Curriculum", back_populates="lectures")