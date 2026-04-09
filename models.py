import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, Enum
)
from sqlalchemy.orm import relationship
from database import Base


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class Difficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    submissions = relationship("Submission", back_populates="user")


class Problem(Base):
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    difficulty = Column(Enum(Difficulty), default=Difficulty.medium, nullable=False)
    time_limit_ms = Column(Integer, default=1000, nullable=False)
    memory_limit_mb = Column(Integer, default=256, nullable=False)
    is_visible = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    test_cases = relationship(
        "TestCase", back_populates="problem",
        cascade="all, delete-orphan", order_by="TestCase.order_index"
    )
    submissions = relationship("Submission", back_populates="problem")
    creator = relationship("User", foreign_keys=[created_by])


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    input = Column(Text, nullable=False, default="")
    expected_output = Column(Text, nullable=False)
    is_sample = Column(Boolean, default=False, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)

    problem = relationship("Problem", back_populates="test_cases")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)
    language = Column(String(10), nullable=False)
    code = Column(Text, nullable=False)
    verdict = Column(String(30), default="pending", nullable=False)
    runtime_ms = Column(Integer, nullable=True)
    memory_mb = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="submissions")
    problem = relationship("Problem", back_populates="submissions")
