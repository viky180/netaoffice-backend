"""User models for Citizens and Politicians."""

from enum import Enum
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserRole(str, Enum):
    """User role enumeration."""
    CITIZEN = "citizen"
    POLITICIAN = "politician"


class UserBase(BaseModel):
    """Base user fields."""
    email: EmailStr
    display_name: str
    role: UserRole


class UserCreate(UserBase):
    """User registration payload."""
    password: str


class UserLogin(BaseModel):
    """User login payload."""
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    """Full user profile from database."""
    id: str
    email: str
    display_name: str
    role: UserRole
    avatar_url: Optional[str] = None
    verified: bool = False
    mu: float = 25.0  # TrueSkill skill rating
    sigma: float = 8.333  # TrueSkill uncertainty
    civic_points: int = 100
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserPublic(BaseModel):
    """Public user info (no sensitive data)."""
    id: str
    display_name: str
    role: UserRole
    avatar_url: Optional[str] = None
    verified: bool = False
    mu: float = 25.0
    sigma: float = 8.333
    
    @property
    def conservative_rating(self) -> float:
        """TrueSkill conservative rating (μ - 3σ)."""
        return self.mu - 3 * self.sigma


class PoliticianStats(UserPublic):
    """Extended politician stats for leaderboard and profile."""
    questions_answered: int = 0
    total_bounty_earned: int = 0
    avg_response_time_hours: Optional[float] = None
    satisfaction_rate: Optional[float] = None
    rank: int = 0
    # Profile-specific stats
    open_bounty_total: int = 0  # Bounty on open questions
    total_charity_released: int = 0  # Points released to charities
    questions_received: int = 0  # Total questions directed at this politician
