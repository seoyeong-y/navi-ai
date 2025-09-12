from sqlalchemy import Column, Integer, String, DateTime, func, SmallInteger, Text
from sqlalchemy.dialects.mysql import INTEGER, TINYINT
from app.database.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255))
    provider = Column(String(20), default="local")
    major = Column(String(255))
    phone = Column(String(255))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    last_login_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

class UserProfile(Base):
    __tablename__ = "user_profiles"

    userId = Column(INTEGER(unsigned=True), primary_key=True)
    name = Column(String(255), nullable=False)
    student_id = Column(String(255))
    major = Column(String(255))
    phone = Column(String(255))
    grade = Column(SmallInteger, default=1)
    semester = Column(SmallInteger, default=1)
    onboarding_completed = Column(TINYINT(1), default=0)
    interests = Column(Text)
    completed_credits = Column(SmallInteger, default=0)
    career = Column(String(255))
    industry = Column(String(255))
    remaining_semesters = Column(SmallInteger, default=0)
    max_credits_per_term = Column(SmallInteger, default=18)
    updated_at = Column(DateTime)
    enrollment_year = Column(SmallInteger)
    graduation_year = Column(SmallInteger)