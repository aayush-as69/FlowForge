"""Runtime configuration. All secrets come from environment variables, never from source."""
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
        return env
    key_file = BACKEND_DIR / ".secret_key"  # git-ignored, generated per deployment
    if key_file.exists():
        return key_file.read_text().strip()
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
        self.database_url = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///./flowforge.db"))
        self.secret_key = _secret_key()
        self.session_hours = int(os.getenv("SESSION_HOURS", "12"))
        self.cookie_secure = os.getenv("COOKIE_SECURE", "0") == "1"
        self.bcrypt_rounds = int(os.getenv("BCRYPT_ROUNDS", "12"))
        self.step_delay = float(os.getenv("FF_STEP_DELAY", "0.9"))
        self.retry_backoff = float(os.getenv("FF_RETRY_BACKOFF", "0.8"))
        self.sync_runner = os.getenv("FF_SYNC_RUNNER", "0") == "1"
        self.seed_demo = os.getenv("FF_SEED", "1") == "1"
        self.demo_password = os.getenv("DEMO_PASSWORD", "flowforge-demo")
        self.llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.llm_timeout = float(os.getenv("LLM_TIMEOUT", "12"))
        self.port = int(os.getenv("FLOWFORGE_API_PORT", "8000"))


settings = Settings()
