"""Configuration settings for CivicStake backend."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    
    # AI
    gemini_api_key: str = ""
    
    # Business Logic
    escrow_timeout_days: int = 14
    initial_civic_points: int = 100
    
    # TrueSkill defaults
    default_mu: float = 25.0
    default_sigma: float = 8.333
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
