"""Escrow transaction models."""

from enum import Enum
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class EscrowStatus(str, Enum):
    """Escrow transaction status."""
    HELD = "held"
    RELEASED = "released"
    REFUNDED = "refunded"


class StakeCreate(BaseModel):
    """Payload to stake points on a question."""
    amount: int


class EscrowTransaction(BaseModel):
    """Escrow transaction record."""
    id: str
    citizen_id: str
    question_id: str
    amount: int
    status: EscrowStatus = EscrowStatus.HELD
    charity_id: Optional[str] = None
    released_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class WalletInfo(BaseModel):
    """User's wallet information."""
    user_id: str
    civic_points: int
    total_staked: int
    total_earned: int  # For politicians: charity earnings


class PointsPurchase(BaseModel):
    """Mock purchase of civic points."""
    amount: int


class Charity(BaseModel):
    """Registered charity (mock for MVP)."""
    id: str
    name: str
    description: str
    logo_url: Optional[str] = None
