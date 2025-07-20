from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database.base import Base


class LectureCode(Base):
    __tablename__ = "lecture_code"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    lecture_description = Column(Text)
    lecture_objectives = Column(Text)

    recent_lectures = relationship("RecentLecture", back_populates="lecture_code")


class RecentLecture(Base):
    __tablename__ = "recent_lectures"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), ForeignKey("lecture_code.code"))
    name = Column(String(255), nullable=False)
    credits = Column(Integer, nullable=False)
    type = Column(String(10))
    grade = Column(String(10))
    semester = Column(String(10))
    major = Column(String(50))
    team_project = Column(String(10))

    lecture_code = relationship("LectureCode", back_populates="recent_lectures")


class LectureReplacement(Base):
    __tablename__ = "lecture_replacement"

    id = Column(Integer, primary_key=True, index=True)
    original_code = Column(String(50), nullable=False)
    replacement_code = Column(String(50), nullable=False)


class Lectures(Base):
    __tablename__ = "lectures"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    professor_id = Column(Integer, ForeignKey("professors.id"))
    credits = Column(Integer, nullable=False)
    type = Column(String(10))
    grade = Column(String(10))
    semester = Column(String(10))
    year = Column(String(10))

    professor = relationship("Professor", back_populates="lectures")