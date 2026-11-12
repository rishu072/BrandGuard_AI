from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
import threading
from typing import Any, Callable
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from jwt import InvalidTokenError

from .config import (
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    DEFAULT_ORGANIZATION_ID,
    DEMO_ADMIN_EMAIL,
    DEMO_ADMIN_PASSWORD,
    DEMO_MODE,
    JWT_ISSUER,
    JWT_SECRET,
    MONGODB_DATABASE,
    MONGODB_URI,
    OTP_MAX_ATTEMPTS,
    OTP_MAX_PER_HOUR,
    OTP_PEPPER,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_MINUTES,
    SESSION_TTL_MINUTES,
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_SSL,
    SMTP_USERNAME,
)

logger = logging.getLogger(__name__)
password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_PASSWORD_HASH = password_hasher.hash("NotARealAccountPassword1!")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_is_strong(password: str) -> bool:
    return (
        len(password) >= 10
        and any(char.islower() for char in password)
        and any(char.isupper() for char in password)
        and any(char.isdigit() for char in password)
    )


def _clean(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    result = deepcopy(record)
    result.pop("_id", None)
    return result


class AuthStore:
    """Small auth repository with isolated in-memory demo mode and Mongo persistence."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._users: dict[str, dict[str, Any]] = {}
        self._emails: dict[str, str] = {}
        self._organizations: dict[str, dict[str, Any]] = {}
        self._challenges: dict[tuple[str, str], dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._sent: dict[str, list[datetime]] = defaultdict(list)
        self._mailbox: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._db = None

        if not DEMO_MODE:
            if not MONGODB_URI:
                raise RuntimeError("MONGODB_URI is required when DEMO_MODE=false.")
            try:
                from pymongo import MongoClient

                client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=4000, tz_aware=True)
                client.admin.command("ping")
                self._db = client[MONGODB_DATABASE]
                self._db.users.create_index("email", unique=True)
                self._db.organizations.create_index("id", unique=True)
                self._db.challenges.create_index([("email", 1), ("purpose", 1)], unique=True)
                self._db.challenges.create_index("expires_at", expireAfterSeconds=0)
                self._db.sessions.create_index("jti", unique=True)
                self._db.sessions.create_index("expires_at", expireAfterSeconds=0)
                self._db.otp_requests.create_index([("email", 1), ("created_at", -1)])
                self._db.otp_requests.create_index("expires_at", expireAfterSeconds=0)
            except Exception as exc:
                raise RuntimeError("MongoDB could not be reached; production auth will not fall back to memory.") from exc

        self._seed_demo_admin()

    @property
    def mode(self) -> str:
        return "demo-memory" if self._db is None else "mongodb"

    def _seed_demo_admin(self) -> None:
        if not DEMO_MODE:
            return
        if not DEMO_ADMIN_EMAIL or not DEMO_ADMIN_PASSWORD:
            logger.warning("Demo admin is not seeded. Set DEMO_ADMIN_EMAIL and DEMO_ADMIN_PASSWORD in .env.")
            return
        if len(DEMO_ADMIN_PASSWORD) < 10:
            logger.warning("Demo admin password is shorter than the recommended 10 characters; replace it in .env.")
        if self.user_by_email(DEMO_ADMIN_EMAIL):
            return
        self.create_organization(
            "Aster & Oak",
            organization_id=DEFAULT_ORGANIZATION_ID,
            industry="Science-led skin care",
            tagline="Care that feels like you.",
        )
        self.create_user(
            {
                "id": str(uuid4()),
                "email": normalize_email(DEMO_ADMIN_EMAIL),
                "name": "Demo Administrator",
                "password_hash": hash_password(DEMO_ADMIN_PASSWORD),
                "role": "admin",
                "organization_id": DEFAULT_ORGANIZATION_ID,
                "email_verified": True,
                "active": True,
                "created_at": utcnow(),
            }
        )
        logger.warning("Demo administrator credentials are enabled. Change them before any deployment.")

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        email = normalize_email(email)
        with self.lock:
            if self._db is not None:
                return _clean(self._db.users.find_one({"email": email}))
            user_id = self._emails.get(email)
            return deepcopy(self._users.get(user_id)) if user_id else None

    def user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self.lock:
            if self._db is not None:
                return _clean(self._db.users.find_one({"id": user_id}))
            return deepcopy(self._users.get(user_id))

    def create_user(self, user: dict[str, Any]) -> None:
        user = deepcopy(user)
        user["email"] = normalize_email(user["email"])
        with self.lock:
            if self.user_by_email(user["email"]):
                raise ValueError("An account with this email already exists.")
            if self._db is not None:
                self._db.users.insert_one(user)
            else:
                self._users[user["id"]] = user
                self._emails[user["email"]] = user["id"]

    def update_user(self, user_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        with self.lock:
            current = self.user_by_id(user_id)
            if current is None:
                return None
            if self._db is not None:
                self._db.users.update_one({"id": user_id}, {"$set": values})
                return self.user_by_id(user_id)
            if "email" in values:
                self._emails.pop(current["email"], None)
                values["email"] = normalize_email(values["email"])
                self._emails[values["email"]] = user_id
            current.update(deepcopy(values))
            self._users[user_id] = current
            return deepcopy(current)

    def list_users(self, organization_id: str) -> list[dict[str, Any]]:
        with self.lock:
            if self._db is not None:
                return [_clean(item) for item in self._db.users.find({"organization_id": organization_id}).sort("created_at", -1)]
            return [deepcopy(user) for user in self._users.values() if user.get("organization_id") == organization_id]

    def create_organization(
        self,
        name: str,
        *,
        organization_id: str | None = None,
        industry: str = "",
        tagline: str = "",
    ) -> dict[str, Any]:
        org = {
            "id": organization_id or str(uuid4()),
            "name": name.strip(),
            "industry": industry.strip(),
            "tagline": tagline.strip(),
            "created_at": utcnow(),
            "active": True,
        }
        with self.lock:
            if self._db is not None:
                self._db.organizations.replace_one({"id": org["id"]}, org, upsert=True)
            else:
                self._organizations[org["id"]] = deepcopy(org)
        return deepcopy(org)

    def organization(self, organization_id: str) -> dict[str, Any] | None:
        with self.lock:
            if self._db is not None:
                return _clean(self._db.organizations.find_one({"id": organization_id}))
            return deepcopy(self._organizations.get(organization_id))

    def update_organization(self, organization_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        with self.lock:
            current = self.organization(organization_id)
            if current is None:
                return None
            if self._db is not None:
                self._db.organizations.update_one({"id": organization_id}, {"$set": values})
                return self.organization(organization_id)
            current.update(deepcopy(values))
            self._organizations[organization_id] = current
            return deepcopy(current)

    def put_challenge(self, challenge: dict[str, Any]) -> None:
        key = (challenge["email"], challenge["purpose"])
        with self.lock:
            if self._db is not None:
                self._db.challenges.replace_one(
                    {"email": challenge["email"], "purpose": challenge["purpose"]},
                    challenge,
                    upsert=True,
                )
            else:
                self._challenges[key] = deepcopy(challenge)

    def get_challenge(self, email: str, purpose: str) -> dict[str, Any] | None:
        with self.lock:
            if self._db is not None:
                return _clean(self._db.challenges.find_one({"email": email, "purpose": purpose}))
            return deepcopy(self._challenges.get((email, purpose)))

    def verify_challenge(self, email: str, purpose: str, supplied_hash: str) -> tuple[bool, str]:
        now = utcnow()
        with self.lock:
            challenge = self.get_challenge(email, purpose)
            if challenge is None:
                return False, "missing"
            if challenge.get("expires_at") <= now:
                self.delete_challenge(email, purpose)
                return False, "expired"
            if challenge.get("attempts", 0) >= OTP_MAX_ATTEMPTS:
                self.delete_challenge(email, purpose)
                return False, "locked"
            if not hmac.compare_digest(challenge.get("code_hash", ""), supplied_hash):
                if self._db is not None:
                    self._db.challenges.update_one(
                        {"email": email, "purpose": purpose, "attempts": {"$lt": OTP_MAX_ATTEMPTS}},
                        {"$inc": {"attempts": 1}},
                    )
                else:
                    self._challenges[(email, purpose)]["attempts"] += 1
                return False, "invalid"
            if self._db is not None:
                result = self._db.challenges.delete_one(
                    {
                        "email": email,
                        "purpose": purpose,
                        "code_hash": challenge["code_hash"],
                        "expires_at": {"$gt": now},
                        "attempts": {"$lt": OTP_MAX_ATTEMPTS},
                    }
                )
                return (result.deleted_count == 1, "ok" if result.deleted_count == 1 else "used")
            del self._challenges[(email, purpose)]
            return True, "ok"

    def delete_challenge(self, email: str, purpose: str) -> None:
        with self.lock:
            if self._db is not None:
                self._db.challenges.delete_one({"email": email, "purpose": purpose})
            else:
                self._challenges.pop((email, purpose), None)

    def otp_send_allowed(self, email: str) -> tuple[bool, int]:
        now = utcnow()
        since = now - timedelta(hours=1)
        with self.lock:
            if self._db is not None:
                last = self._db.otp_requests.find_one({"email": email}, sort=[("created_at", -1)])
                count = self._db.otp_requests.count_documents({"email": email, "created_at": {"$gte": since}})
                recent = [last["created_at"]] if last else []
            else:
                self._sent[email] = [stamp for stamp in self._sent[email] if stamp >= since]
                recent = self._sent[email]
                count = len(recent)
            if recent:
                elapsed = (now - recent[-1]).total_seconds()
                if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                    return False, max(1, OTP_RESEND_COOLDOWN_SECONDS - int(elapsed))
            if count >= OTP_MAX_PER_HOUR:
                return False, max(1, int((recent[0] + timedelta(hours=1) - now).total_seconds())) if recent else 3600
            return True, 0

    def record_otp_send(self, email: str) -> None:
        now = utcnow()
        with self.lock:
            if self._db is not None:
                self._db.otp_requests.insert_one({"email": email, "created_at": now, "expires_at": now + timedelta(days=1)})
            else:
                self._sent[email].append(now)

    def put_session(self, session: dict[str, Any]) -> None:
        with self.lock:
            if self._db is not None:
                self._db.sessions.insert_one(session)
            else:
                self._sessions[session["jti"]] = deepcopy(session)

    def session_active(self, jti: str, user_id: str) -> bool:
        now = utcnow()
        with self.lock:
            if self._db is not None:
                return self._db.sessions.count_documents(
                    {"jti": jti, "user_id": user_id, "revoked": False, "expires_at": {"$gt": now}}, limit=1
                ) == 1
            session = self._sessions.get(jti)
            return bool(session and session["user_id"] == user_id and not session["revoked"] and session["expires_at"] > now)

    def revoke_session(self, jti: str) -> None:
        with self.lock:
            if self._db is not None:
                self._db.sessions.update_one({"jti": jti}, {"$set": {"revoked": True}})
            elif jti in self._sessions:
                self._sessions[jti]["revoked"] = True

    def store_demo_mail(self, email: str, code: str, purpose: str, expires_at: datetime) -> None:
        with self.lock:
            self._mailbox[email].append({"code": code, "purpose": purpose, "expires_at": expires_at})
            self._mailbox[email] = self._mailbox[email][-10:]

    def demo_mailbox(self, email: str) -> list[dict[str, Any]]:
        with self.lock:
            now = utcnow()
            return [deepcopy(item) for item in self._mailbox.get(email, []) if item["expires_at"] > now]


auth_store = AuthStore()


def otp_hash(email: str, purpose: str, code: str) -> str:
    material = f"{email}:{purpose}:{code}".encode("utf-8")
    return hmac.new(OTP_PEPPER.encode("utf-8"), material, hashlib.sha256).hexdigest()


def send_otp_email(email: str, name: str, code: str, purpose: str) -> datetime:
    expires_at = utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
    purpose_label = "verify your email" if purpose == "verify_email" else "finish signing in"
    if not SMTP_HOST:
        if not DEMO_MODE:
            raise RuntimeError("SMTP is required outside demo mode.")
        auth_store.store_demo_mail(email, code, purpose, expires_at)
        return expires_at

    message = EmailMessage()
    message["Subject"] = f"Your BrandGuard AI verification code"
    message["From"] = SMTP_FROM_EMAIL or SMTP_USERNAME
    message["To"] = email
    message.set_content(
        f"Hello {name},\n\nUse this one-time code to {purpose_label}: {code}\n\n"
        f"It expires in {OTP_TTL_MINUTES} minutes and can be used once. "
        "If you did not request it, you can ignore this email.\n\nBrandGuard AI"
    )
    context = ssl.create_default_context()
    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15) as client:
            if SMTP_USERNAME:
                client.login(SMTP_USERNAME, SMTP_PASSWORD)
            client.send_message(message)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as client:
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
            if SMTP_USERNAME:
                client.login(SMTP_USERNAME, SMTP_PASSWORD)
            client.send_message(message)
    return expires_at


def issue_session(user: dict[str, Any], response: Response) -> dict[str, Any]:
    now = utcnow()
    expires_at = now + timedelta(minutes=SESSION_TTL_MINUTES)
    jti = str(uuid4())
    token = jwt.encode(
        {
            "sub": user["id"],
            "org": user["organization_id"],
            "jti": jti,
            "iss": JWT_ISSUER,
            "iat": now,
            "exp": expires_at,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    auth_store.put_session({"jti": jti, "user_id": user["id"], "expires_at": expires_at, "revoked": False})
    response.set_cookie(
        "brandguard_session",
        token,
        max_age=SESSION_TTL_MINUTES * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    return {"user": public_user(user), "expires_at": expires_at.isoformat()}


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "organization_id": user["organization_id"],
        "email_verified": bool(user.get("email_verified")),
        "active": bool(user.get("active", True)),
    }


def _request_token(request: Request) -> str | None:
    token = request.cookies.get("brandguard_session")
    if token:
        return token
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def get_current_user(request: Request) -> dict[str, Any]:
    token = _request_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
        user_id = claims.get("sub")
        jti = claims.get("jti")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.") from exc
    if not user_id or not jti or not auth_store.session_active(jti, user_id):
        raise HTTPException(status_code=401, detail="Your session is no longer active. Sign in again.")
    user = auth_store.user_by_id(user_id)
    if not user or not user.get("active") or not user.get("email_verified"):
        raise HTTPException(status_code=401, detail="This account is unavailable.")
    return {**user, "session_id": jti}


def require_roles(*roles: str) -> Callable[..., dict[str, Any]]:
    def dependency(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Your account does not have permission for this action.")
        return user

    return dependency


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.buckets: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)

    def check(self, scope: str, key: str, limit: int, seconds: int) -> None:
        now = utcnow()
        cutoff = now - timedelta(seconds=seconds)
        bucket_key = (scope, key or "unknown")
        with self.lock:
            bucket = self.buckets[bucket_key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry = max(1, int((bucket[0] + timedelta(seconds=seconds) - now).total_seconds()))
                raise HTTPException(status_code=429, detail=f"Too many requests. Try again in {retry} seconds.", headers={"Retry-After": str(retry)})
            bucket.append(now)


auth_limiter = SlidingWindowLimiter()


def set_session_cookie(response: Response, user: dict[str, Any]) -> dict[str, Any]:
    return issue_session(user, response)


def logout_current_session(response: Response, user: dict[str, Any]) -> None:
    auth_store.revoke_session(user["session_id"])
    response.delete_cookie("brandguard_session", path="/", httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE)


def allowed_frontend_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin.rstrip("/") == FRONTEND_ORIGIN
