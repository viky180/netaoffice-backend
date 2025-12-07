"""Leaderboard router for politician rankings."""

from fastapi import APIRouter, Query
from typing import List, Optional
from app.database import get_supabase
from app.models.user import PoliticianStats

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


@router.get("", response_model=List[PoliticianStats])
async def get_leaderboard(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get global politician leaderboard sorted by skill rating."""
    supabase = get_supabase()
    
    # Get all politicians with their stats
    politicians = supabase.table("profiles").select("*").eq(
        "role", "politician"
    ).order("mu", desc=True).range(offset, offset + limit - 1).execute()
    
    results = []
    rank = offset + 1
    
    for p in politicians.data:
        # Get questions answered count
        answers = supabase.table("answers").select("id", count="exact").eq(
            "politician_id", p["id"]
        ).execute()
        
        # Get total bounty earned (released escrows)
        answered_questions = supabase.table("answers").select(
            "question:questions(id)"
        ).eq("politician_id", p["id"]).execute()
        
        total_bounty = 0
        for a in answered_questions.data:
            if a.get("question"):
                escrow = supabase.table("escrow").select("amount").eq(
                    "question_id", a["question"]["id"]
                ).eq("status", "released").execute()
                total_bounty += sum(e["amount"] for e in escrow.data)
        
        # Calculate satisfaction rate from votes
        all_votes = []
        for a in answered_questions.data:
            if a.get("question"):
                answer = supabase.table("answers").select("id").eq(
                    "question_id", a["question"]["id"]
                ).execute()
                if answer.data:
                    votes = supabase.table("votes").select("is_helpful").eq(
                        "answer_id", answer.data[0]["id"]
                    ).execute()
                    all_votes.extend(votes.data)
        
        satisfaction = None
        if all_votes:
            helpful = sum(1 for v in all_votes if v["is_helpful"])
            satisfaction = (helpful / len(all_votes)) * 100
        
        results.append(PoliticianStats(
            id=p["id"],
            display_name=p["display_name"],
            role="politician",
            avatar_url=p.get("avatar_url"),
            verified=p.get("verified", False),
            mu=p.get("mu", 25.0),
            sigma=p.get("sigma", 8.333),
            questions_answered=answers.count or 0,
            total_bounty_earned=total_bounty,
            satisfaction_rate=satisfaction,
            rank=rank
        ))
        rank += 1
    
    return results


@router.get("/{politician_id}", response_model=PoliticianStats)
async def get_politician_stats(politician_id: str):
    """Get detailed stats for a specific politician."""
    supabase = get_supabase()
    
    # Get politician profile
    profile = supabase.table("profiles").select("*").eq(
        "id", politician_id
    ).eq("role", "politician").single().execute()
    
    if not profile.data:
        return {"error": "Politician not found"}
    
    p = profile.data
    
    # Get all questions directed at this politician
    all_questions = supabase.table("questions").select("id, status").eq(
        "target_politician_id", politician_id
    ).execute()
    
    questions_received = len(all_questions.data)
    
    # Calculate open bounty (bounty on open questions)
    open_bounty_total = 0
    for q in all_questions.data:
        if q["status"] == "open":
            escrow = supabase.table("escrow").select("amount").eq(
                "question_id", q["id"]
            ).eq("status", "held").execute()
            open_bounty_total += sum(e["amount"] for e in escrow.data)
    
    # Get answers with timing
    answers = supabase.table("answers").select(
        "*, question:questions(*)"
    ).eq("politician_id", politician_id).execute()
    
    total_bounty = 0
    total_charity = 0
    response_times = []
    all_votes = []
    
    for a in answers.data:
        if a.get("question"):
            # Get released bounty (earned by politician)
            escrow = supabase.table("escrow").select("amount, status").eq(
                "question_id", a["question"]["id"]
            ).execute()
            
            for e in escrow.data:
                if e["status"] == "released":
                    total_bounty += e["amount"]
                    total_charity += e["amount"]  # Same as released to charity
            
            # Calculate response time
            from datetime import datetime
            created = datetime.fromisoformat(a["question"]["created_at"].replace("Z", "+00:00"))
            answered = datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
            response_times.append((answered - created).total_seconds() / 3600)
            
            # Get votes
            votes = supabase.table("votes").select("is_helpful").eq(
                "answer_id", a["id"]
            ).execute()
            all_votes.extend(votes.data)
    
    avg_response = sum(response_times) / len(response_times) if response_times else None
    satisfaction = None
    if all_votes:
        helpful = sum(1 for v in all_votes if v["is_helpful"])
        satisfaction = (helpful / len(all_votes)) * 100
    
    # Calculate rank
    all_politicians = supabase.table("profiles").select("id, mu").eq(
        "role", "politician"
    ).order("mu", desc=True).execute()
    
    rank = 1
    for pol in all_politicians.data:
        if pol["id"] == politician_id:
            break
        rank += 1
    
    return PoliticianStats(
        id=p["id"],
        display_name=p["display_name"],
        role="politician",
        avatar_url=p.get("avatar_url"),
        verified=p.get("verified", False),
        mu=p.get("mu", 25.0),
        sigma=p.get("sigma", 8.333),
        questions_answered=len(answers.data),
        total_bounty_earned=total_bounty,
        avg_response_time_hours=avg_response,
        satisfaction_rate=satisfaction,
        rank=rank,
        open_bounty_total=open_bounty_total,
        total_charity_released=total_charity,
        questions_received=questions_received
    )


@router.get("/stats/dashboard")
async def get_dashboard_stats():
    """Get platform-wide statistics."""
    supabase = get_supabase()
    
    # Total questions
    questions = supabase.table("questions").select("id", count="exact").execute()
    
    # Open questions
    open_q = supabase.table("questions").select("id", count="exact").eq(
        "status", "open"
    ).execute()
    
    # Total politicians
    politicians = supabase.table("profiles").select("id", count="exact").eq(
        "role", "politician"
    ).execute()
    
    # Total citizens
    citizens = supabase.table("profiles").select("id", count="exact").eq(
        "role", "citizen"
    ).execute()
    
    # Total bounty in escrow
    escrow = supabase.table("escrow").select("amount").eq(
        "status", "held"
    ).execute()
    total_escrow = sum(e["amount"] for e in escrow.data)
    
    # Total released to charity
    released = supabase.table("escrow").select("amount").eq(
        "status", "released"
    ).execute()
    total_released = sum(e["amount"] for e in released.data)
    
    return {
        "total_questions": questions.count or 0,
        "open_questions": open_q.count or 0,
        "total_politicians": politicians.count or 0,
        "total_citizens": citizens.count or 0,
        "total_bounty_in_escrow": total_escrow,
        "total_released_to_charity": total_released
    }
