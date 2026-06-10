"""
Central configuration loaded from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


# ── LinkdAPI ──────────────────────────────────────────────────────────────────
LINKDAPI_API_KEY: str = os.getenv("LINKDAPI_API_KEY", "")
LINKDAPI_BASE_URL: str = "https://linkdapi.com/api/v1"

# ── Fetch Defaults ────────────────────────────────────────────────────────────
DEFAULT_POST_COUNT: int = 5          # posts to fetch per company
MAX_RETRIES: int = 3                  # retry attempts on failure
RETRY_DELAY: float = 1.0             # base delay in seconds (exponential backoff)
REQUEST_TIMEOUT: float = 30.0        # seconds

# ── Database ──────────────────────────────────────────────────────────────────
_db_path = Path(__file__).resolve().parent.parent / "linkedin_analytics.db"
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_db_path}")

# ── Mistral AI (Phase 4) ─────────────────────────────────────────────────────
MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-large-latest")

# ── Alert Thresholds (Phase 5) ───────────────────────────────────────────────
HIGH_ALERT_ENGAGEMENT_MULTIPLIER: float = 2.0
MEDIUM_ALERT_ENGAGEMENT_MULTIPLIER: float = 1.3

# ── Validation ────────────────────────────────────────────────────────────────
def validate_config() -> None:
    """Raise an error if critical config is missing."""
    if not LINKDAPI_API_KEY or LINKDAPI_API_KEY == "your_api_key_here":
        raise ValueError(
            "LINKDAPI_API_KEY is not set. "
            "Add your API key to the .env file in the project root."
        )
