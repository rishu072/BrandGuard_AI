import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


APP_NAME = os.getenv("APP_NAME", "BrandGuard AI")
DEMO_MODE = env_bool("DEMO_MODE", True)
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "brandguard").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

# Demo secrets are generated per process when unset. Configure stable, random values
# before deploying so sessions survive restarts and OTP hashes remain verifiable.
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
OTP_PEPPER = os.getenv("OTP_PEPPER", "").strip()
if DEMO_MODE:
    JWT_SECRET = JWT_SECRET or secrets.token_urlsafe(48)
    OTP_PEPPER = OTP_PEPPER or secrets.token_urlsafe(48)
elif len(JWT_SECRET) < 32 or len(OTP_PEPPER) < 32:
    raise RuntimeError("Set JWT_SECRET and OTP_PEPPER to random values of at least 32 characters.")

JWT_ISSUER = os.getenv("JWT_ISSUER", "brandguard-ai")
SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "720"))
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "10"))
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_MAX_PER_HOUR = int(os.getenv("OTP_MAX_PER_HOUR", "5"))

DEMO_ADMIN_EMAIL = os.getenv("DEMO_ADMIN_EMAIL", "").strip().lower()
DEMO_ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "").strip()
SMTP_USE_SSL = env_bool("SMTP_USE_SSL", False)

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip().rstrip("/")
COOKIE_SECURE = env_bool("COOKIE_SECURE", not DEMO_MODE)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("COOKIE_SAMESITE must be lax, strict, or none.")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SECURE must be true when COOKIE_SAMESITE=none.")

DEFAULT_ORGANIZATION_ID = "org-demo"
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "brandguard_sources").strip()
QDRANT_EMBED_MODEL = os.getenv("QDRANT_EMBED_MODEL", "BAAI/bge-small-en-v1.5").strip()
