"""Questions router."""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timedelta
from app.database import get_supabase
from app.models.user import UserProfile
from app.models.question import (
    QuestionCreate, Question, QuestionWithDetails, QuestionStatus
)
from app.models.escrow import EscrowStatus
from app.routers.auth import require_auth, require_citizen, get_current_user

router = APIRouter(prefix="/questions", tags=["Questions"])


@router.post("", response_model=Question)
async def create_question(
    data: QuestionCreate,
    user: UserProfile = Depends(require_citizen)
):
    """Create a new question targeting a politician."""
    supabase = get_supabase()
    
    # Verify target politician exists
    politician = supabase.table("profiles").select("id, role").eq(
        "id", data.target_politician_id
    ).eq("role", "politician").single().execute()
    
    if not politician.data:
        raise HTTPException(status_code=404, detail="Politician not found")
    
    # Check if citizen has enough points for initial stake
    if data.initial_stake > 0:
        if user.civic_points < data.initial_stake:
            raise HTTPException(status_code=400, detail="Insufficient civic points")
    
    # Create question
    now = datetime.utcnow()
    question_data = {
        "title": data.title,
        "body": data.body,
        "citizen_id": user.id,
        "target_politician_id": data.target_politician_id,
        "total_bounty": data.initial_stake,
        "status": QuestionStatus.OPEN.value,
        "created_at": now.isoformat(),
        "deadline": (now + timedelta(days=14)).isoformat()
    }
    
    result = supabase.table("questions").insert(question_data).execute()
    
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create question")
    
    question = result.data[0]
    
    # Handle initial stake
    if data.initial_stake > 0:
        # Deduct from citizen's wallet
        supabase.table("profiles").update({
            "civic_points": user.civic_points - data.initial_stake
        }).eq("id", user.id).execute()
        
        # Create escrow record
        supabase.table("escrow").insert({
            "citizen_id": user.id,
            "question_id": question["id"],
            "amount": data.initial_stake,
            "status": EscrowStatus.HELD.value,
            "created_at": now.isoformat()
        }).execute()
    
    return Question(**question)


@router.get("", response_model=List[QuestionWithDetails])
async def list_questions(
    status: Optional[QuestionStatus] = None,
    politician_id: Optional[str] = None,
    sort_by: str = Query("bounty", regex="^(bounty|recent|deadline)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: Optional[UserProfile] = Depends(get_current_user)
):
    """List questions with optional filters."""
    supabase = get_supabase()
    
    query = supabase.table("questions").select(
        "*, citizen:profiles!questions_citizen_id_fkey(display_name), "
        "politician:profiles!questions_target_politician_id_fkey(display_name)"
    )
    
    if status:
        query = query.eq("status", status.value)
    
    if politician_id:
        query = query.eq("target_politician_id", politician_id)
    
    # Sorting
    if sort_by == "bounty":
        query = query.order("total_bounty", desc=True)
    elif sort_by == "recent":
        query = query.order("created_at", desc=True)
    elif sort_by == "deadline":
        query = query.order("deadline", desc=False)
    
    query = query.range(offset, offset + limit - 1)
    result = query.execute()
    
    questions = []
    for q in result.data:
        # Get staker count
        stakers = supabase.table("escrow").select("citizen_id", count="exact").eq(
            "question_id", q["id"]
        ).execute()
        
        # Check if has answer
        answer = supabase.table("answers").select("id").eq(
            "question_id", q["id"]
        ).execute()
        
        questions.append(QuestionWithDetails(
            id=q["id"],
            title=q["title"],
            body=q["body"],
            citizen_id=q["citizen_id"],
            target_politician_id=q["target_politician_id"],
            total_bounty=q["total_bounty"],
            status=QuestionStatus(q["status"]),
            ai_directness_score=q.get("ai_directness_score"),
            created_at=q["created_at"],
            deadline=q["deadline"],
            citizen_name=q["citizen"]["display_name"] if q.get("citizen") else None,
            politician_name=q["politician"]["display_name"] if q.get("politician") else None,
            staker_count=stakers.count or 0,
            has_answer=len(answer.data) > 0
        ))
    
    return questions


@router.get("/{question_id}", response_model=QuestionWithDetails)
async def get_question(
    question_id: str,
    user: Optional[UserProfile] = Depends(get_current_user)
):
    """Get question details by ID."""
    supabase = get_supabase()
    
    result = supabase.table("questions").select(
        "*, citizen:profiles!questions_citizen_id_fkey(display_name), "
        "politician:profiles!questions_target_politician_id_fkey(display_name)"
    ).eq("id", question_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Question not found")
    
    q = result.data
    
    # Get staker count
    stakers = supabase.table("escrow").select("citizen_id", count="exact").eq(
        "question_id", q["id"]
    ).execute()
    
    # Get answer and votes if exists
    answer = supabase.table("answers").select("id").eq(
        "question_id", q["id"]
    ).execute()
    
    vote_count = 0
    helpful_pct = None
    
    if answer.data:
        votes = supabase.table("votes").select("is_helpful").eq(
            "answer_id", answer.data[0]["id"]
        ).execute()
        
        vote_count = len(votes.data)
        if vote_count > 0:
            helpful = sum(1 for v in votes.data if v["is_helpful"])
            helpful_pct = (helpful / vote_count) * 100
    
    return QuestionWithDetails(
        id=q["id"],
        title=q["title"],
        body=q["body"],
        citizen_id=q["citizen_id"],
        target_politician_id=q["target_politician_id"],
        total_bounty=q["total_bounty"],
        status=QuestionStatus(q["status"]),
        ai_directness_score=q.get("ai_directness_score"),
        created_at=q["created_at"],
        deadline=q["deadline"],
        citizen_name=q["citizen"]["display_name"] if q.get("citizen") else None,
        politician_name=q["politician"]["display_name"] if q.get("politician") else None,
        staker_count=stakers.count or 0,
        has_answer=len(answer.data) > 0,
        vote_count=vote_count,
        helpful_percentage=helpful_pct
    )
