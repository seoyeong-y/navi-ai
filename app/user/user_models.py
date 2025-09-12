from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.dialects.mysql import INTEGER
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