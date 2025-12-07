"""Question and Bounty models."""

from enum import Enum
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class QuestionStatus(str, Enum):
    """Question lifecycle status."""
    OPEN = "open"
    ANSWERED = "answered"
    EXPIRED = "expired"
    FLAGGED = "flagged"


class QuestionCreate(BaseModel):
    """Payload to create a new question."""
    title: str
    body: str
    target_politician_id: str
    initial_stake: int = 0  # Points to stake with question


class QuestionUpdate(BaseModel):
    """Payload to update a question."""
    title: Optional[str] = None
    body: Optional[str] = None


class Question(BaseModel):
    """Full question model."""
    id: str
    title: str
    body: str
    citizen_id: str
    target_politician_id: str
    total_bounty: int = 0
    status: QuestionStatus = QuestionStatus.OPEN
    ai_directness_score: Optional[float] = None
    created_at: datetime
    deadline: datetime
    
    class Config:
        from_attributes = True


class QuestionWithDetails(Question):
    """Question with related data for display."""
    citizen_name: Optional[str] = None
    politician_name: Optional[str] = None
    staker_count: int = 0
    has_answer: bool = False
    vote_count: int = 0
    helpful_percentage: Optional[float] = None


class BountyContributor(BaseModel):
    """A contributor to a question's bounty."""
    citizen_id: str
    citizen_name: str
    amount: int
    staked_at: datetime


class QuestionBounty(BaseModel):
    """Bounty summary for a question."""
    question_id: str
    total_bounty: int
    contributors: List[BountyContributor]
    time_remaining_hours: float
