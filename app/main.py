"""
CivicStake Backend - FastAPI Application

Main entry point for the Civic Reputation Marketplace API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.routers import auth, questions, bounties, answers, leaderboard
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("🚀 CivicStake API starting up...")
    yield
    # Shutdown
    print("👋 CivicStake API shutting down...")


app = FastAPI(
    title="CivicStake API",
    description="""
    The Civic Reputation Marketplace - where citizens hold politicians accountable.
    
    ## Features
    - Citizens post questions and stake civic points as bounties
    - Politicians answer to earn reputation and release funds to charity
    - AI-powered answer analysis detects evasive responses
    - Bayesian ranking system rewards responsive politicians
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Production domains
        "https://netaoffice.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(bounties.router)
app.include_router(answers.router)
app.include_router(leaderboard.router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "CivicStake API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    settings = get_settings()
    
    return {
        "status": "healthy",
        "supabase_configured": bool(settings.supabase_url and settings.supabase_key),
        "ai_configured": bool(settings.gemini_api_key),
        "escrow_timeout_days": settings.escrow_timeout_days
    }
