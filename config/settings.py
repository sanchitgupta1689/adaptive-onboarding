from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Gemini
    google_api_key: str

    # LangSmith
    langsmith_api_key: str
    langsmith_project: str = "adaptive-onboarding"
    langchain_tracing_v2: str = "true"

    # Gemini model names
    # Pro  → complex reasoning (Planner, Risk agents)
    # Flash → fast classification (Empathy agent)
    gemini_pro_model: str = "gemini-2.5-pro"
    gemini_flash_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "models/text-embedding-004"

    # Agent temperature settings
    # Lower = more deterministic decisions, less creative variance
    planner_temperature: float = 0.3
    empathy_temperature: float = 0.1   # near-deterministic, it's a classifier
    risk_temperature: float = 0.1

    # Churn risk threshold above which Risk Agent hard-overrides Planner
    churn_hard_override_threshold: float = 0.75

    # Minimum bandit sample count before we trust it over Pattern Store
    bandit_min_samples: int = 50

    # App
    app_env: str = "development"
    app_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# lru_cache ensures Settings is instantiated only once for the entire app lifetime.
# Every module that calls get_settings() gets the same object — no repeated disk reads.
@lru_cache()
def get_settings() -> Settings:
    return Settings()
