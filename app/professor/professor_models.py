from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.base import Base


class Professor(Base):
    __tablename__ = "professor"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    department = Column(String(100))

    lectures = relationship("Lectures", back_populates="professor")
    preferred_professors = relationship("PreferredProfessor", back_populates="professor")

class PreferredProfessor(Base):
    __tablename__ = "preferred_professors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("professor.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    professor = relationship("Professor", back_populates="preferred_professors")