from sqlalchemy import Column, Integer, SmallInteger, DateTime, func
from app.database.base import Base

class GraduationRequirement(Base):
    __tablename__ = "graduation_requirement"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_year_start = Column(SmallInteger, nullable=False)
    entry_year_end = Column(SmallInteger)
    total_credits = Column(SmallInteger, nullable=False)
    liberal_arts = Column(SmallInteger, nullable=False)
    major = Column(SmallInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())