"""Authentication router."""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from app.database import get_supabase, get_supabase_admin
from app.models.user import (
    UserCreate, UserLogin, UserProfile, UserPublic, UserRole
)
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[UserProfile]:
    """Extract and validate current user from auth header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    
    try:
        # Verify token with Supabase
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            return None
        
        # Get profile from database
        profile = supabase.table("profiles").select("*").eq(
            "id", user_response.user.id
        ).single().execute()
        
        if profile.data:
            return UserProfile(
                id=profile.data["id"],
                email=user_response.user.email,
                display_name=profile.data["display_name"],
                role=UserRole(profile.data["role"]),
                avatar_url=profile.data.get("avatar_url"),
                verified=profile.data.get("verified", False),
                mu=profile.data.get("mu", 25.0),
                sigma=profile.data.get("sigma", 8.333),
                civic_points=profile.data.get("civic_points", 100),
                created_at=profile.data["created_at"]
            )
    except Exception:
        return None
    
    return None


async def require_auth(user: Optional[UserProfile] = Depends(get_current_user)) -> UserProfile:
    """Require authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_citizen(user: UserProfile = Depends(require_auth)) -> UserProfile:
    """Require authenticated citizen."""
    if user.role != UserRole.CITIZEN:
        raise HTTPException(status_code=403, detail="Citizen role required")
    return user


async def require_politician(user: UserProfile = Depends(require_auth)) -> UserProfile:
    """Require authenticated politician."""
    if user.role != UserRole.POLITICIAN:
        raise HTTPException(status_code=403, detail="Politician role required")
    return user


@router.post("/register", response_model=UserPublic)
async def register(user_data: UserCreate):
    """Register a new user (citizen or politician)."""
    supabase = get_supabase()
    settings = get_settings()
    
    try:
        # Create auth user with metadata (role passed to trigger)
        auth_response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "data": {
                    "role": user_data.role.value,
                    "display_name": user_data.display_name
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Registration failed")
        
        user_id = auth_response.user.id
        
        # Update profile using admin client to bypass RLS
        # The trigger may have already created a basic profile, so use upsert
        admin_client = get_supabase_admin()
        profile_data = {
            "id": user_id,
            "display_name": user_data.display_name,
            "role": user_data.role.value,
            "verified": False,
            "mu": settings.default_mu,
            "sigma": settings.default_sigma,
            "civic_points": settings.initial_civic_points
        }
        
        admin_client.table("profiles").upsert(profile_data).execute()
        
        return UserPublic(
            id=user_id,
            display_name=user_data.display_name,
            role=user_data.role,
            verified=False,
            mu=settings.default_mu,
            sigma=settings.default_sigma
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
async def login(credentials: UserLogin):
    """Login and get access token."""
    supabase = get_supabase()
    
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        
        if not response.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Get user profile
        profile = supabase.table("profiles").select("*").eq(
            "id", response.user.id
        ).single().execute()
        
        return {
            "access_token": response.session.access_token,
            "token_type": "bearer",
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "display_name": profile.data["display_name"],
                "role": profile.data["role"]
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@router.get("/me", response_model=UserProfile)
async def get_me(user: UserProfile = Depends(require_auth)):
    """Get current user profile."""
    return user


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout current user."""
    if authorization and authorization.startswith("Bearer "):
        supabase = get_supabase()
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
    return {"message": "Logged out"}
