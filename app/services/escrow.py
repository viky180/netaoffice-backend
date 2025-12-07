"""Escrow service for managing staked points."""

from datetime import datetime, timezone, timedelta
from app.database import get_supabase
from app.models.escrow import EscrowStatus
from app.config import get_settings


async def check_and_release_escrow(question_id: str) -> bool:
    """
    Check if escrow should be released based on votes or AI score.
    
    Release conditions:
    1. >50% positive votes from stakers, OR
    2. AI directness score >= 70
    
    Returns: True if escrow was released
    """
    supabase = get_supabase()
    
    # Get answer and AI score
    answer = supabase.table("answers").select(
        "id, ai_analysis"
    ).eq("question_id", question_id).single().execute()
    
    if not answer.data:
        return False
    
    # Check AI score
    ai_analysis = answer.data.get("ai_analysis")
    ai_passes = False
    if ai_analysis and isinstance(ai_analysis, dict):
        directness = ai_analysis.get("directness_score", 0)
        ai_passes = directness >= 70
    
    # Check vote percentage
    votes = supabase.table("votes").select("is_helpful").eq(
        "answer_id", answer.data["id"]
    ).execute()
    
    votes_pass = False
    if votes.data and len(votes.data) >= 1:
        helpful = sum(1 for v in votes.data if v["is_helpful"])
        votes_pass = (helpful / len(votes.data)) > 0.5
    
    # Release if either condition met
    if ai_passes or votes_pass:
        return await release_escrow(question_id)
    
    return False


async def release_escrow(question_id: str, charity_id: str = None) -> bool:
    """
    Release all held escrow for a question to charity.
    
    Returns: True if successful
    """
    supabase = get_supabase()
    now = datetime.now(timezone.utc)
    
    # Get all held escrow for this question
    escrows = supabase.table("escrow").select("*").eq(
        "question_id", question_id
    ).eq("status", EscrowStatus.HELD.value).execute()
    
    if not escrows.data:
        return False
    
    # Update all to released
    for escrow in escrows.data:
        supabase.table("escrow").update({
            "status": EscrowStatus.RELEASED.value,
            "charity_id": charity_id or "default_charity",
            "released_at": now.isoformat()
        }).eq("id", escrow["id"]).execute()
    
    return True


async def refund_expired_escrows() -> int:
    """
    Background task to refund escrows for expired questions.
    
    Should be run periodically (e.g., daily cron).
    Returns: Number of refunded escrows
    """
    supabase = get_supabase()
    settings = get_settings()
    now = datetime.now(timezone.utc)
    
    # Find expired questions that haven't been answered
    expired = supabase.table("questions").select("id").eq(
        "status", "open"
    ).lt("deadline", now.isoformat()).execute()
    
    refund_count = 0
    
    for q in expired.data:
        # Check if no answer exists
        answer = supabase.table("answers").select("id").eq(
            "question_id", q["id"]
        ).execute()
        
        if answer.data:
            continue  # Has answer, don't refund
        
        # Get held escrows
        escrows = supabase.table("escrow").select("*").eq(
            "question_id", q["id"]
        ).eq("status", EscrowStatus.HELD.value).execute()
        
        for escrow in escrows.data:
            # Refund to citizen
            profile = supabase.table("profiles").select("civic_points").eq(
                "id", escrow["citizen_id"]
            ).single().execute()
            
            new_balance = profile.data["civic_points"] + escrow["amount"]
            
            supabase.table("profiles").update({
                "civic_points": new_balance
            }).eq("id", escrow["citizen_id"]).execute()
            
            # Update escrow status
            supabase.table("escrow").update({
                "status": EscrowStatus.REFUNDED.value,
                "released_at": now.isoformat()
            }).eq("id", escrow["id"]).execute()
            
            refund_count += 1
        
        # Update question status
        supabase.table("questions").update({
            "status": "expired"
        }).eq("id", q["id"]).execute()
    
    return refund_count


async def get_escrow_stats(user_id: str) -> dict:
    """Get escrow statistics for a user."""
    supabase = get_supabase()
    
    # Get all user escrows
    escrows = supabase.table("escrow").select("*").eq(
        "citizen_id", user_id
    ).execute()
    
    held = sum(e["amount"] for e in escrows.data if e["status"] == "held")
    released = sum(e["amount"] for e in escrows.data if e["status"] == "released")
    refunded = sum(e["amount"] for e in escrows.data if e["status"] == "refunded")
    
    return {
        "total_staked": held + released + refunded,
        "currently_held": held,
        "released_to_charity": released,
        "refunded": refunded,
        "escrow_count": len(escrows.data)
    }
