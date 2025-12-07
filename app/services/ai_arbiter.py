"""AI Arbiter service for answer analysis using Gemini."""

import google.generativeai as genai
from app.config import get_settings
from app.models.answer import AIAnalysis


async def analyze_answer_directness(
    question_title: str,
    question_body: str,
    answer_content: str
) -> AIAnalysis:
    """
    Analyze how directly an answer addresses the question.
    
    Uses Gemini to detect "political fluff" and evasive responses.
    Returns a directness score from 0-100.
    """
    settings = get_settings()
    
    if not settings.gemini_api_key:
        # Return mock analysis if no API key
        return AIAnalysis(
            directness_score=75.0,
            summary="AI analysis unavailable - using default score",
            flags=[]
        )
    
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    prompt = f"""You are an AI assistant analyzing political accountability.

Analyze how directly the following answer addresses the citizen's question.

QUESTION TITLE: {question_title}

QUESTION BODY: {question_body}

POLITICIAN'S ANSWER: {answer_content}

Evaluate the answer and respond in this exact JSON format:
{{
    "directness_score": <0-100 number, where 100 is perfectly direct and 0 is completely evasive>,
    "summary": "<one sentence summary of your analysis>",
    "flags": [<list of any concerning patterns, e.g. "political_fluff", "off_topic", "vague_promises", "blame_shifting">]
}}

Scoring guidelines:
- 80-100: Answer directly addresses the specific issue with concrete details
- 60-79: Answer is somewhat relevant but lacks specifics
- 40-59: Answer is vague or only tangentially related
- 20-39: Answer is mostly political platitudes with minimal relevance
- 0-19: Answer completely ignores the question

Return ONLY the JSON, no other text."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Parse JSON from response
        import json
        # Handle potential markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        data = json.loads(text)
        
        return AIAnalysis(
            directness_score=float(data.get("directness_score", 50)),
            summary=data.get("summary", "Analysis completed"),
            flags=data.get("flags", [])
        )
        
    except Exception as e:
        # Fallback if AI analysis fails
        return AIAnalysis(
            directness_score=50.0,
            summary=f"Analysis error: {str(e)[:50]}",
            flags=["analysis_failed"]
        )


async def check_duplicate_question(
    title: str,
    body: str,
    politician_id: str
) -> dict:
    """
    Check if a similar question already exists for this politician.
    
    Returns similarity info if duplicate found.
    """
    settings = get_settings()
    
    if not settings.gemini_api_key:
        return {"is_duplicate": False}
    
    from app.database import get_supabase
    supabase = get_supabase()
    
    # Get existing open questions for this politician
    existing = supabase.table("questions").select("id, title, body").eq(
        "target_politician_id", politician_id
    ).eq("status", "open").limit(10).execute()
    
    if not existing.data:
        return {"is_duplicate": False}
    
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    existing_qs = "\n".join([
        f"ID: {q['id']}\nTitle: {q['title']}\nBody: {q['body'][:200]}"
        for q in existing.data
    ])
    
    prompt = f"""Compare this new question to existing ones and determine if it's a duplicate.

NEW QUESTION:
Title: {title}
Body: {body}

EXISTING QUESTIONS:
{existing_qs}

Respond with JSON:
{{
    "is_duplicate": true/false,
    "similar_question_id": "<ID of most similar question if duplicate>",
    "similarity_reason": "<brief explanation if duplicate>"
}}

Return ONLY the JSON."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        import json
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        return json.loads(text)
        
    except Exception:
        return {"is_duplicate": False}
