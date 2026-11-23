"""Runtime configuration. Secrets must be injected in production."""
import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent


def _load_dotenv() -> None:
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _secret_key() -> str:
    env = os.getenv("SECRET_KEY")
    if env:
        if len(env) < 32:
            raise RuntimeError("SECRET_KEY must contain at least 32 characters.")
        return env
    if os.getenv("APP_ENV", "development").lower() in {"production", "prod"}:
        raise RuntimeError("SECRET_KEY is required when APP_ENV=production.")
    key_file = BACKEND_DIR / ".secret_key"
    if key_file.exists():
        key = key_file.read_text().strip()
        if len(key) >= 32:
            return key
    key = secrets.token_urlsafe(48)
    try:
        key_file.write_text(key)
        key_file.chmod(0o600)
    except OSError:
        pass
    return key


class Settings:
    def __init__(self) -> None:
        _load_dotenv()
        self.app_env = os.getenv("APP_ENV", "development").lower()
        self.database_url = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///./flowforge.db"))
        self.secret_key = _secret_key()
        self.session_hours = int(os.getenv("SESSION_HOURS", "12"))
        self.cookie_secure = os.getenv("COOKIE_SECURE", "1" if self.app_env in {"production", "prod"} else "0") == "1"
        if self.app_env in {"production", "prod"} and not self.cookie_secure:
            raise RuntimeError("COOKIE_SECURE=1 is required in production.")
        self.bcrypt_rounds = int(os.getenv("BCRYPT_ROUNDS", "12"))
        self.step_delay = float(os.getenv("FF_STEP_DELAY", "0.9"))
        self.retry_backoff = float(os.getenv("FF_RETRY_BACKOFF", "0.8"))
        self.sync_runner = os.getenv("FF_SYNC_RUNNER", "0") == "1"
        # Assumptions behind the savings estimate (shown next to every figure in the UI; override per deployment).
        self.roi = {
            "currency": os.getenv("ROI_CURRENCY", "INR"),
            "manual_minutes_per_request": float(os.getenv("ROI_MANUAL_MINUTES", "45")),
            "hourly_cost": float(os.getenv("ROI_HOURLY_COST", "600")),
            "human_review_minutes": float(os.getenv("ROI_HUMAN_REVIEW_MINUTES", "8")),
            "llm_call_cost": float(os.getenv("ROI_LLM_CALL_COST", "1.5")),
            "tool_call_cost": float(os.getenv("ROI_TOOL_CALL_COST", "0.2")),
        }
        self.seed_demo = os.getenv("FF_SEED", "0") == "1"
        # Scripted demo scenarios (with injected faults) are on in development and off in production unless asked for.
        self.demo_mode = os.getenv("FF_DEMO_MODE", "0" if self.app_env in {"production", "prod"} else "1") == "1"
        if self.app_env in {"production", "prod"} and self.seed_demo:
            raise RuntimeError("FF_SEED=1 is forbidden in production; provision an administrator with create_admin.py.")
        self.demo_password = os.getenv("DEMO_PASSWORD")
        if self.seed_demo and not self.demo_password:
            raise RuntimeError("DEMO_PASSWORD must be set explicitly when FF_SEED=1.")
        self.llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.llm_timeout = float(os.getenv("LLM_TIMEOUT", "12"))
        self.port = int(os.getenv("FLOWFORGE_API_PORT", "8000"))
        self.api_metric_retention_days = max(7, int(os.getenv("API_METRIC_RETENTION_DAYS", "90")))


settings = Settings()
