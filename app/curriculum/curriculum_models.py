from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean, func, Enum, Integer
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import relationship
from app.database.base import Base

class Curriculum(Base):
    __tablename__ = "curriculums"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    userId = Column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime, onupdate=func.now())
    total_credits = Column(INTEGER(unsigned=True), nullable=False, default=0)
    description = Column(Text)
    is_default = Column(Boolean, nullable=False, default=False)
    conditions = Column(String(50), nullable=False)

    lectures = relationship("CurriLecture", back_populates="curriculum", cascade="all, delete-orphan")


class CurriLecture(Base):
    __tablename__ = "curri_lectures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    curri_id = Column(Integer, ForeignKey("curriculums.id"), nullable=False)
    lect_id = Column(Integer, ForeignKey("lecture_code.id"), nullable=True)
    name = Column(String(50), nullable=False)
    credits = Column(Integer, nullable=False)
    semester = Column(Enum("1", "2", "S", "W"), nullable=False)
    type = Column(Enum("GR", "GE", "MR", "ME", "RE", "FE"), nullable=False)
    grade = Column(Integer, nullable=False)
    status = Column(Enum("completed", "current", "planned", "off-track"), nullable=True, default="planned")
    is_retaken = Column(Boolean, nullable=True, default=False)

    curriculum = relationship("Curriculum", back_populates="lectures")
    lecture_code = relationship("LectureCode", back_populates="curri_lectures")


class Records(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, ForeignKey("users.id"), nullable=False)
    courseCode = Column(String(255))
    courseName = Column(String(255), nullable=False)
    credits = Column(Integer, nullable=False)
    grade = Column(String(255))
    semester = Column(String(20))
    type = Column(Enum("GR", "GE", "MR", "ME", "RE", "FE"), nullable=False)
    createdAt = Column(DateTime, nullable=False, server_default=func.now())
    updatedAt = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    instructor = Column(String(80))
    room = Column(String(60))
    timeSlots = Column(Text)
    sourceScheduleId = Column(Integer, ForeignKey("schedule.id"))
    conversionDate = Column(DateTime)