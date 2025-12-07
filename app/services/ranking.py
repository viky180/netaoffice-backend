"""Ranking service using Bayesian TrueSkill-style rating."""

import math
from openskill.models import PlackettLuce
from app.database import get_supabase
from app.config import get_settings


# Initialize the rating model
model = PlackettLuce()


async def update_rating_on_answer(
    politician_id: str,
    bounty_value: int,
    response_time_hours: float,
    satisfaction_score: float = None
) -> tuple[float, float]:
    """
    Update politician's skill rating after answering a question.
    
    The rating gain is proportional to:
    - Bounty value (logarithmic scale)
    - Response speed (faster = better)
    - Citizen satisfaction score (if votes received)
    
    Returns: (new_mu, new_sigma)
    """
    supabase = get_supabase()
    settings = get_settings()
    
    # Get current rating
    profile = supabase.table("profiles").select("mu, sigma").eq(
        "id", politician_id
    ).single().execute()
    
    current_mu = profile.data.get("mu", settings.default_mu)
    current_sigma = profile.data.get("sigma", settings.default_sigma)
    
    # Calculate performance score
    # Bounty weight: log scale so $1000 isn't 100x better than $10
    bounty_weight = 1 + math.log10(max(bounty_value, 1) + 1) / 3
    
    # Speed weight: faster responses get bonus (decay over time)
    # Max bonus at 1 hour, neutral at 24 hours, penalty after 72 hours
    if response_time_hours <= 1:
        speed_weight = 1.3
    elif response_time_hours <= 24:
        speed_weight = 1.0 + 0.3 * (1 - response_time_hours / 24)
    elif response_time_hours <= 72:
        speed_weight = 1.0 - 0.2 * ((response_time_hours - 24) / 48)
    else:
        speed_weight = 0.8
    
    # Satisfaction weight (if available)
    satisfaction_weight = 1.0
    if satisfaction_score is not None:
        # 80%+ satisfaction gives bonus, below 50% gives penalty
        if satisfaction_score >= 80:
            satisfaction_weight = 1.2
        elif satisfaction_score >= 60:
            satisfaction_weight = 1.0
        elif satisfaction_score >= 40:
            satisfaction_weight = 0.9
        else:
            satisfaction_weight = 0.7
    
    # Combined performance multiplier
    performance = bounty_weight * speed_weight * satisfaction_weight
    
    # Create rating objects for openskill
    from openskill.models import PlackettLuceRating
    
    politician_rating = PlackettLuceRating(mu=current_mu, sigma=current_sigma)
    
    # Simulate a "match" where performance determines outcome
    # Higher performance = more skill gain
    # We create a virtual opponent at default skill level
    opponent_mu = settings.default_mu
    
    # Adjust gain based on performance
    # If performance > 1, politician "won" decisively
    # If performance < 1, politician barely "won"
    
    if performance >= 1.0:
        # Good performance: rating goes up
        # Use openskill to calculate new rating as if won
        [[new_rating], _] = model.rate(
            [[politician_rating], 
             [PlackettLuceRating(mu=opponent_mu, sigma=8.333)]],
            ranks=[1, 2]  # Politician ranked first (won)
        )
        
        # Scale the gain by performance
        mu_gain = (new_rating.mu - current_mu) * min(performance, 2.0)
        new_mu = current_mu + mu_gain
        new_sigma = new_rating.sigma
    else:
        # Poor performance: minimal gain
        new_mu = current_mu + 0.1
        new_sigma = max(current_sigma - 0.1, 1.0)
    
    # Ensure bounds
    new_mu = max(0, min(new_mu, 50))
    new_sigma = max(1.0, min(new_sigma, 10.0))
    
    # Update database
    supabase.table("profiles").update({
        "mu": new_mu,
        "sigma": new_sigma
    }).eq("id", politician_id).execute()
    
    return (new_mu, new_sigma)


async def penalize_ignored_question(
    politician_id: str,
    bounty_value: int,
    days_ignored: int
) -> tuple[float, float]:
    """
    Penalize a politician for ignoring a high-bounty question.
    
    Penalty scales with bounty value and time ignored.
    Returns: (new_mu, new_sigma)
    """
    supabase = get_supabase()
    settings = get_settings()
    
    # Get current rating
    profile = supabase.table("profiles").select("mu, sigma").eq(
        "id", politician_id
    ).single().execute()
    
    current_mu = profile.data.get("mu", settings.default_mu)
    current_sigma = profile.data.get("sigma", settings.default_sigma)
    
    # Calculate penalty
    # Higher bounty = bigger penalty
    bounty_factor = math.log10(max(bounty_value, 10)) / 2
    
    # More days ignored = bigger penalty
    time_factor = min(days_ignored / 7, 2.0)  # Cap at 2x for 2+ weeks
    
    # Base penalty
    mu_penalty = 0.5 * bounty_factor * time_factor
    
    # Increase uncertainty (less confident in their skill)
    sigma_increase = 0.2 * time_factor
    
    new_mu = max(0, current_mu - mu_penalty)
    new_sigma = min(10.0, current_sigma + sigma_increase)
    
    # Update database
    supabase.table("profiles").update({
        "mu": new_mu,
        "sigma": new_sigma
    }).eq("id", politician_id).execute()
    
    return (new_mu, new_sigma)


def calculate_conservative_rating(mu: float, sigma: float) -> float:
    """
    Calculate conservative skill estimate (μ - 3σ).
    
    This is used for leaderboard ranking to favor
    consistent performers over lucky ones.
    """
    return mu - 3 * sigma


async def update_rating_after_votes(
    politician_id: str,
    question_id: str
) -> tuple[float, float]:
    """
    Update rating based on final vote results after voting period.
    """
    supabase = get_supabase()
    
    # Get the answer
    answer = supabase.table("answers").select("id").eq(
        "question_id", question_id
    ).single().execute()
    
    if not answer.data:
        return (0, 0)
    
    # Get vote breakdown
    votes = supabase.table("votes").select("is_helpful").eq(
        "answer_id", answer.data["id"]
    ).execute()
    
    if not votes.data:
        return (0, 0)
    
    helpful = sum(1 for v in votes.data if v["is_helpful"])
    total = len(votes.data)
    satisfaction = (helpful / total) * 100
    
    # Get question bounty
    question = supabase.table("questions").select("total_bounty").eq(
        "id", question_id
    ).single().execute()
    
    # Re-calculate with satisfaction
    return await update_rating_on_answer(
        politician_id=politician_id,
        bounty_value=question.data["total_bounty"],
        response_time_hours=24,  # Neutral time since already applied
        satisfaction_score=satisfaction
    )
