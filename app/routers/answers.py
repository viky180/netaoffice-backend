"""Answers router with voting and AI analysis."""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from app.database import get_supabase
from app.models.user import UserProfile
from app.models.answer import (
    AnswerCreate, Answer, AnswerWithVotes, VoteCreate, Vote, VoteSummary
)
from app.models.question import QuestionStatus
from app.routers.auth import require_auth, require_politician, require_citizen, get_current_user
from app.services.ai_arbiter import analyze_answer_directness
from app.services.ranking import update_rating_on_answer
from app.services.escrow import check_and_release_escrow

router = APIRouter(prefix="/answers", tags=["Answers"])


@router.post("/questions/{question_id}", response_model=AnswerWithVotes)
async def submit_answer(
    question_id: str,
    data: AnswerCreate,
    user: UserProfile = Depends(require_politician)
):
    """Submit an answer to a question (politician only)."""
    supabase = get_supabase()
    
    # Verify question exists, is open, and targets this politician
    question = supabase.table("questions").select("*").eq(
        "id", question_id
    ).single().execute()
    
    if not question.data:
        raise HTTPException(status_code=404, detail="Question not found")
    
    if question.data["target_politician_id"] != user.id:
        raise HTTPException(status_code=403, detail="This question is not addressed to you")
    
    if question.data["status"] != "open":
        raise HTTPException(status_code=400, detail="Question is not open for answers")
    
    # Check if already answered
    existing = supabase.table("answers").select("id").eq(
        "question_id", question_id
    ).execute()
    
    if existing.data:
        raise HTTPException(status_code=400, detail="Question already answered")
    
    now = datetime.now(timezone.utc)
    
    # Run AI analysis
    ai_analysis = None
    try:
        ai_result = await analyze_answer_directness(
            question_title=question.data["title"],
            question_body=question.data["body"],
            answer_content=data.content
        )
        ai_analysis = ai_result
    except Exception:
        pass  # AI analysis is optional, continue without it
    
    # Create answer
    answer_data = {
        "question_id": question_id,
        "politician_id": user.id,
        "content": data.content,
        "video_url": data.video_url,
        "ai_analysis": ai_analysis.model_dump() if ai_analysis else None,
        "created_at": now.isoformat()
    }
    
    result = supabase.table("answers").insert(answer_data).execute()
    
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to submit answer")
    
    # Update question status
    supabase.table("questions").update({
        "status": QuestionStatus.ANSWERED.value,
        "ai_directness_score": ai_analysis.directness_score if ai_analysis else None
    }).eq("id", question_id).execute()
    
    # Calculate response time and update rating
    created_at = datetime.fromisoformat(question.data["created_at"].replace("Z", "+00:00"))
    response_time_hours = (now - created_at).total_seconds() / 3600
    
    await update_rating_on_answer(
        politician_id=user.id,
        bounty_value=question.data["total_bounty"],
        response_time_hours=response_time_hours
    )
    
    answer = result.data[0]
    return AnswerWithVotes(
        id=answer["id"],
        question_id=answer["question_id"],
        politician_id=answer["politician_id"],
        content=answer["content"],
        video_url=answer.get("video_url"),
        ai_analysis=ai_analysis,
        created_at=answer["created_at"],
        total_votes=0,
        helpful_votes=0,
        evasive_votes=0
    )


@router.get("/questions/{question_id}", response_model=AnswerWithVotes)
async def get_question_answer(
    question_id: str,
    user: UserProfile = Depends(get_current_user)
):
    """Get the answer for a question."""
    supabase = get_supabase()
    
    result = supabase.table("answers").select("*").eq(
        "question_id", question_id
    ).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="No answer found")
    
    answer = result.data
    
    # Get vote counts
    votes = supabase.table("votes").select("is_helpful").eq(
        "answer_id", answer["id"]
    ).execute()
    
    helpful = sum(1 for v in votes.data if v["is_helpful"])
    evasive = len(votes.data) - helpful
    
    return AnswerWithVotes(
        id=answer["id"],
        question_id=answer["question_id"],
        politician_id=answer["politician_id"],
        content=answer["content"],
        video_url=answer.get("video_url"),
        ai_analysis=answer.get("ai_analysis"),
        created_at=answer["created_at"],
        total_votes=len(votes.data),
        helpful_votes=helpful,
        evasive_votes=evasive
    )


@router.post("/{answer_id}/vote", response_model=Vote)
async def vote_on_answer(
    answer_id: str,
    data: VoteCreate,
    user: UserProfile = Depends(require_citizen)
):
    """Vote on an answer (stakers only)."""
    supabase = get_supabase()
    
    # Get answer and question
    answer = supabase.table("answers").select("*, question:questions(*)").eq(
        "id", answer_id
    ).single().execute()
    
    if not answer.data:
        raise HTTPException(status_code=404, detail="Answer not found")
    
    question_id = answer.data["question_id"]
    
    # Check if user has staked on this question
    stake = supabase.table("escrow").select("id").eq(
        "citizen_id", user.id
    ).eq("question_id", question_id).execute()
    
    if not stake.data:
        raise HTTPException(
            status_code=403,
            detail="Only stakers can vote on answers"
        )
    
    # Check if already voted
    existing_vote = supabase.table("votes").select("id").eq(
        "answer_id", answer_id
    ).eq("citizen_id", user.id).execute()
    
    if existing_vote.data:
        # Update existing vote
        supabase.table("votes").update({
            "is_helpful": data.is_helpful
        }).eq("id", existing_vote.data[0]["id"]).execute()
        
        result = supabase.table("votes").select("*").eq(
            "id", existing_vote.data[0]["id"]
        ).single().execute()
    else:
        # Create new vote
        now = datetime.now(timezone.utc)
        vote_data = {
            "answer_id": answer_id,
            "citizen_id": user.id,
            "is_helpful": data.is_helpful,
            "created_at": now.isoformat()
        }
        result = supabase.table("votes").insert(vote_data).execute()
    
    # Check if escrow should be released
    await check_and_release_escrow(question_id)
    
    return Vote(**result.data[0])


@router.get("/{answer_id}/votes", response_model=VoteSummary)
async def get_vote_summary(
    answer_id: str,
    user: UserProfile = Depends(get_current_user)
):
    """Get voting summary for an answer."""
    supabase = get_supabase()
    
    votes = supabase.table("votes").select("*").eq(
        "answer_id", answer_id
    ).execute()
    
    helpful = sum(1 for v in votes.data if v["is_helpful"])
    total = len(votes.data)
    evasive = total - helpful
    
    helpful_pct = (helpful / total * 100) if total > 0 else None
    
    # Check if current user has voted
    user_vote = None
    if user:
        for v in votes.data:
            if v["citizen_id"] == user.id:
                user_vote = v["is_helpful"]
                break
    
    return VoteSummary(
        answer_id=answer_id,
        total_votes=total,
        helpful_votes=helpful,
        evasive_votes=evasive,
        helpful_percentage=helpful_pct,
        user_vote=user_vote
    )
