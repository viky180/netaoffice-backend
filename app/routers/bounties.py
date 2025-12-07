"""Bounties router for staking civic points."""

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime, timezone
from app.database import get_supabase
from app.models.user import UserProfile
from app.models.escrow import (
    StakeCreate, EscrowTransaction, EscrowStatus,
    WalletInfo, PointsPurchase
)
from app.models.question import QuestionBounty, BountyContributor
from app.routers.auth import require_auth, require_citizen

router = APIRouter(prefix="/bounties", tags=["Bounties"])


@router.post("/questions/{question_id}/stake", response_model=EscrowTransaction)
async def stake_points(
    question_id: str,
    data: StakeCreate,
    user: UserProfile = Depends(require_citizen)
):
    """Stake civic points on a question's bounty."""
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Stake amount must be positive")
    
    supabase = get_supabase()
    
    # Check question exists and is open
    question = supabase.table("questions").select("id, status").eq(
        "id", question_id
    ).single().execute()
    
    if not question.data:
        raise HTTPException(status_code=404, detail="Question not found")
    
    if question.data["status"] != "open":
        raise HTTPException(status_code=400, detail="Question is not open for staking")
    
    # Check citizen has enough points
    profile = supabase.table("profiles").select("civic_points").eq(
        "id", user.id
    ).single().execute()
    
    current_points = profile.data["civic_points"]
    if current_points < data.amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient points. Available: {current_points}"
        )
    
    now = datetime.now(timezone.utc)
    
    # Deduct points from wallet
    supabase.table("profiles").update({
        "civic_points": current_points - data.amount
    }).eq("id", user.id).execute()
    
    # Create escrow record
    escrow_data = {
        "citizen_id": user.id,
        "question_id": question_id,
        "amount": data.amount,
        "status": EscrowStatus.HELD.value,
        "created_at": now.isoformat()
    }
    
    result = supabase.table("escrow").insert(escrow_data).execute()
    
    if not result.data:
        # Rollback points
        supabase.table("profiles").update({
            "civic_points": current_points
        }).eq("id", user.id).execute()
        raise HTTPException(status_code=500, detail="Failed to create escrow")
    
    # Update question total bounty
    q = supabase.table("questions").select("total_bounty").eq(
        "id", question_id
    ).single().execute()
    
    supabase.table("questions").update({
        "total_bounty": q.data["total_bounty"] + data.amount
    }).eq("id", question_id).execute()
    
    return EscrowTransaction(**result.data[0])


@router.get("/questions/{question_id}", response_model=QuestionBounty)
async def get_bounty_details(question_id: str):
    """Get bounty details and contributors for a question."""
    supabase = get_supabase()
    
    # Get question
    question = supabase.table("questions").select(
        "id, total_bounty, deadline"
    ).eq("id", question_id).single().execute()
    
    if not question.data:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Get escrow records with citizen names
    escrows = supabase.table("escrow").select(
        "*, citizen:profiles!escrow_citizen_id_fkey(display_name)"
    ).eq("question_id", question_id).execute()
    
    contributors = []
    for e in escrows.data:
        contributors.append(BountyContributor(
            citizen_id=e["citizen_id"],
            citizen_name=e["citizen"]["display_name"] if e.get("citizen") else "Anonymous",
            amount=e["amount"],
            staked_at=e["created_at"]
        ))
    
    # Calculate time remaining
    deadline = datetime.fromisoformat(question.data["deadline"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    time_remaining = max(0, (deadline - now).total_seconds() / 3600)
    
    return QuestionBounty(
        question_id=question_id,
        total_bounty=question.data["total_bounty"],
        contributors=contributors,
        time_remaining_hours=time_remaining
    )


@router.get("/wallet", response_model=WalletInfo)
async def get_wallet(user: UserProfile = Depends(require_auth)):
    """Get current user's wallet info."""
    supabase = get_supabase()
    
    # Get current points
    profile = supabase.table("profiles").select("civic_points").eq(
        "id", user.id
    ).single().execute()
    
    # Get total staked (held escrows)
    staked = supabase.table("escrow").select("amount").eq(
        "citizen_id", user.id
    ).eq("status", EscrowStatus.HELD.value).execute()
    
    total_staked = sum(e["amount"] for e in staked.data)
    
    # For politicians, get total earned for charity
    total_earned = 0
    if user.role.value == "politician":
        earned = supabase.table("escrow").select("amount").eq(
            "status", EscrowStatus.RELEASED.value
        ).execute()
        # Filter by questions this politician answered
        # (This is simplified - in production you'd join properly)
        total_earned = sum(e["amount"] for e in earned.data)
    
    return WalletInfo(
        user_id=user.id,
        civic_points=profile.data["civic_points"],
        total_staked=total_staked,
        total_earned=total_earned
    )


@router.post("/purchase", response_model=WalletInfo)
async def purchase_points(
    data: PointsPurchase,
    user: UserProfile = Depends(require_auth)
):
    """Mock purchase of civic points (for MVP demo)."""
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    if data.amount > 1000:
        raise HTTPException(status_code=400, detail="Maximum 1000 points per purchase")
    
    supabase = get_supabase()
    
    # Get current points
    profile = supabase.table("profiles").select("civic_points").eq(
        "id", user.id
    ).single().execute()
    
    new_balance = profile.data["civic_points"] + data.amount
    
    # Update points
    supabase.table("profiles").update({
        "civic_points": new_balance
    }).eq("id", user.id).execute()
    
    return WalletInfo(
        user_id=user.id,
        civic_points=new_balance,
        total_staked=0,
        total_earned=0
    )
