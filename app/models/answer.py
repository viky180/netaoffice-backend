"""Answer and Vote models."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AnswerCreate(BaseModel):
    """Payload to submit an answer."""
    content: str
    video_url: Optional[str] = None


class AIAnalysis(BaseModel):
    """AI analysis of an answer."""
    directness_score: float  # 0-100
    summary: str
    flags: list[str] = []  # e.g., ["political_fluff", "off_topic"]


class Answer(BaseModel):
    """Full answer model."""
    id: str
    question_id: str
    politician_id: str
    content: str
    video_url: Optional[str] = None
    ai_analysis: Optional[AIAnalysis] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class AnswerWithVotes(Answer):
    """Answer with voting statistics."""
    total_votes: int = 0
    helpful_votes: int = 0
    evasive_votes: int = 0
    
    @property
    def helpful_percentage(self) -> Optional[float]:
        """Calculate percentage of helpful votes."""
        if self.total_votes == 0:
            return None
        return (self.helpful_votes / self.total_votes) * 100


class VoteCreate(BaseModel):
    """Payload to cast a vote on an answer."""
    is_helpful: bool


class Vote(BaseModel):
    """Vote record."""
    id: str
    answer_id: str
    citizen_id: str
    is_helpful: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class VoteSummary(BaseModel):
    """Voting summary for an answer."""
    answer_id: str
    total_votes: int
    helpful_votes: int
    evasive_votes: int
    helpful_percentage: Optional[float] = None
    user_vote: Optional[bool] = None  # Current user's vote if any
