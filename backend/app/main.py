from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from .audit import retrieve_sources, run_deterministic_checks, run_gemini_analysis
from .auth import (
    DUMMY_PASSWORD_HASH,
    auth_limiter,
    auth_store,
    get_current_user,
    hash_password,
    issue_session,
    logout_current_session,
    normalize_email,
    otp_hash,
    password_is_strong,
    public_user,
    require_roles,
    send_otp_email,
    utcnow,
    verify_password,
)
from .config import (
    APP_NAME,
    COOKIE_SECURE,
    COOKIE_SAMESITE,
    DEMO_MODE,
    FRONTEND_ORIGIN,
    GEMINI_API_KEY,
    OTP_MAX_ATTEMPTS,
    OTP_TTL_MINUTES,
    QDRANT_URL,
    SMTP_FROM_EMAIL,
    SMTP_HOST,
)
from .repository import now_iso, repository

logger = logging.getLogger(__name__)
if not DEMO_MODE and (not SMTP_HOST or not SMTP_FROM_EMAIL):
    raise RuntimeError("Set SMTP_HOST and SMTP_FROM_EMAIL when DEMO_MODE=false.")
app = FastAPI(
    title=APP_NAME,
    version="2.0.0",
    description="Evidence-backed brand governance with verified accounts and human publication gates.",
)
allowed_origins = list(dict.fromkeys([FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def enforce_browser_origin(request: Request, call_next):
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in allowed_origins:
            return Response(status_code=403, content="Request origin is not allowed.")
    return await call_next(request)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=2, max_length=80)
    organization_name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class OTPRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    purpose: Literal["verify_email", "login"]


class ResendRequest(BaseModel):
    email: EmailStr
    purpose: Literal["verify_email", "login"]


class DraftCreate(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    channel: str = Field(min_length=2, max_length=50)
    text: str = Field(min_length=12, max_length=20000)


class AuditRequest(BaseModel):
    include_ai: bool = False


class FindingUpdate(BaseModel):
    decision: Literal["accepted", "rejected", "edited"]
    suggestion: str | None = Field(default=None, max_length=4000)


class ReviewRequest(BaseModel):
    action: Literal["approved", "changes_requested"]
    comment: str = Field(default="", max_length=1200)


class SourceCreate(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    type: str = Field(default="Guideline", max_length=40)
    content: str = Field(min_length=12, max_length=8000)


class FactCreate(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    value: str = Field(min_length=1, max_length=240)
    match_key: str = Field(min_length=2, max_length=40)
    source_excerpt: str = Field(min_length=12, max_length=1200)


class TerminologyCreate(BaseModel):
    preferred: str = Field(min_length=2, max_length=120)
    avoid: list[str] = Field(min_length=1, max_length=10)
    reason: str = Field(min_length=8, max_length=600)
    severity: Literal["low", "medium", "high"] = "medium"


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    industry: str = Field(default="", max_length=120)
    tagline: str = Field(default="", max_length=200)


class UserUpdate(BaseModel):
    role: Literal["member", "reviewer", "admin"] | None = None
    active: bool | None = None


class AdminUserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=80)
    role: Literal["member", "reviewer", "admin"] = "member"
    temporary_password: str = Field(min_length=10, max_length=128)


class RuleProposalCreate(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    proposed_text: str = Field(min_length=12, max_length=4000)
    rationale: str = Field(min_length=8, max_length=1200)
    draft_id: str | None = None
    finding_id: str | None = None


class ProposalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=1200)


def _workspace(user: dict) -> dict:
    organization = auth_store.organization(user["organization_id"])
    if not organization or not organization.get("active", True):
        raise HTTPException(status_code=403, detail="This organization is unavailable.")
    return repository.load(user["organization_id"], organization)


def _save(state: dict, user: dict) -> None:
    repository.save(state, user["organization_id"])


def _draft(state: dict, draft_id: str) -> dict:
    draft = next((item for item in state["drafts"] if item["id"] == draft_id), None)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found in this organization.")
    return draft


def _event(state: dict, draft: dict | None, actor: str, action: str, detail: str) -> None:
    state.setdefault("events", []).insert(
        0,
        {
            "id": str(uuid4()),
            "draft_id": (draft or {}).get("id", ""),
            "draft_title": (draft or {}).get("title", "Organization"),
            "actor": actor,
            "action": action,
            "detail": detail,
            "created_at": now_iso(),
        },
    )
    state["events"] = state["events"][:250]


def _send_code(user: dict, purpose: str) -> None:
    allowed, retry_after = auth_store.otp_send_allowed(user["email"])
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"A code was sent recently. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
    auth_store.put_challenge(
        {
            "email": user["email"],
            "purpose": purpose,
            "code_hash": otp_hash(user["email"], purpose, code),
            "attempts": 0,
            "created_at": utcnow(),
            "expires_at": expires_at,
        }
    )
    try:
        send_otp_email(user["email"], user["name"], code, purpose)
        auth_store.record_otp_send(user["email"])
    except Exception as exc:
        auth_store.delete_challenge(user["email"], purpose)
        logger.exception("OTP delivery failed for %s", user["email"])
        raise HTTPException(status_code=503, detail="Email delivery is unavailable. Check SMTP settings and try again.") from exc


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": APP_NAME,
        "demo_mode": DEMO_MODE,
        "storage_mode": repository.mode,
        "gemini_configured": bool(GEMINI_API_KEY),
        "qdrant_configured": bool(QDRANT_URL),
        "smtp_configured": bool(SMTP_HOST),
        "timestamp": now_iso(),
    }


@app.post("/api/auth/register", status_code=202)
def register(payload: RegisterRequest, request: Request) -> dict:
    auth_limiter.check("register_ip", request.client.host if request.client else "unknown", 8, 3600)
    email = normalize_email(str(payload.email))
    auth_limiter.check("register_email", email, 5, 3600)
    if any(not (char.isalnum() or char in "@._+-") for char in email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    password = payload.password
    if not password_is_strong(password):
        raise HTTPException(status_code=422, detail="Use at least one lowercase letter, uppercase letter, and number in the password.")
    if auth_store.user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    organization = auth_store.create_organization(payload.organization_name)
    user = {
        "id": str(uuid4()),
        "email": email,
        "name": payload.name.strip(),
        "password_hash": hash_password(password),
        "role": "admin",
        "organization_id": organization["id"],
        "email_verified": False,
        "active": True,
        "created_at": utcnow(),
    }
    try:
        auth_store.create_user(user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _send_code(user, "verify_email")
    return {"message": "Check your email for a one-time verification code.", "email": email, "expires_in_seconds": OTP_TTL_MINUTES * 60}


@app.post("/api/auth/login", status_code=202)
def login(payload: LoginRequest, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    email = normalize_email(str(payload.email))
    auth_limiter.check("login_ip", ip, 20, 900)
    auth_limiter.check("login_email", email, 10, 900)
    user = auth_store.user_by_email(email)
    valid = verify_password(user["password_hash"] if user else DUMMY_PASSWORD_HASH, payload.password)
    if not user or not valid or not user.get("active", False):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    if not user.get("email_verified"):
        _send_code(user, "verify_email")
        return {"requires_verification": True, "purpose": "verify_email", "email": email, "message": "Verify your email before signing in."}
    _send_code(user, "login")
    return {"requires_otp": True, "purpose": "login", "email": email, "message": "Enter the one-time code sent to your email."}


@app.post("/api/auth/verify")
def verify_otp(payload: OTPRequest, response: Response, request: Request) -> dict:
    email = normalize_email(str(payload.email))
    auth_limiter.check("verify_ip", request.client.host if request.client else "unknown", 30, 900)
    auth_limiter.check("verify_email", email, 12, 900)
    user = auth_store.user_by_email(email)
    if not user:
        raise HTTPException(status_code=400, detail="The code is invalid or has expired.")
    if payload.purpose == "verify_email" and user.get("email_verified"):
        raise HTTPException(status_code=400, detail="This email is already verified. Sign in to request a login code.")
    ok, reason = auth_store.verify_challenge(email, payload.purpose, otp_hash(email, payload.purpose, payload.code))
    if not ok:
        if reason == "locked":
            raise HTTPException(status_code=429, detail="Too many incorrect codes. Request a new code.")
        raise HTTPException(status_code=400, detail="The code is invalid or has expired.")
    if payload.purpose == "verify_email":
        user = auth_store.update_user(user["id"], {"email_verified": True, "verified_at": utcnow()}) or user
    if not user.get("active"):
        raise HTTPException(status_code=403, detail="This account is disabled. Contact your organization administrator.")
    return issue_session(user, response)


@app.post("/api/auth/resend", status_code=202)
def resend_otp(payload: ResendRequest, request: Request) -> dict:
    auth_limiter.check("resend_ip", request.client.host if request.client else "unknown", 10, 3600)
    email = normalize_email(str(payload.email))
    auth_limiter.check("resend_email", email, 5, 3600)
    user = auth_store.user_by_email(email)
    if user and user.get("active"):
        if payload.purpose == "verify_email" and not user.get("email_verified"):
            _send_code(user, "verify_email")
        elif payload.purpose == "login" and user.get("email_verified"):
            _send_code(user, "login")
    return {"message": "If the account is eligible, a new code has been sent.", "expires_in_seconds": OTP_TTL_MINUTES * 60}


@app.get("/api/auth/me")
def current_account(user: dict = Depends(get_current_user)) -> dict:
    return {"user": public_user(user), "organization": auth_store.organization(user["organization_id"])}


@app.post("/api/auth/logout")
def logout(response: Response, user: dict = Depends(get_current_user)) -> dict:
    logout_current_session(response, user)
    return {"message": "You have been signed out."}


@app.get("/api/dev/mailbox")
def demo_mailbox(email: EmailStr, request: Request) -> dict:
    if not DEMO_MODE or not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=404, detail="Not found.")
    return {"messages": auth_store.demo_mailbox(normalize_email(str(email)))}


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(get_current_user)) -> dict:
    state = _workspace(user)
    drafts = state["drafts"]
    open_findings = [finding for draft in drafts for finding in draft.get("findings", []) if finding.get("decision") == "open"]
    waiting = sum(1 for draft in drafts if draft["status"] in {"needs_review", "in_review"})
    reviewed = [draft for draft in drafts if draft["status"] in {"approved", "changes_requested", "published"}]
    approved = sum(1 for draft in reviewed if draft["status"] in {"approved", "published"})
    return {
        "organization": state["brand"]["organization"],
        "metrics": {
            "brand_score": state["brand"]["organization"].get("brand_score", 0),
            "awaiting_review": waiting,
            "open_findings": len(open_findings),
            "critical_findings": sum(1 for finding in open_findings if finding["severity"] == "critical"),
            "approval_rate": round(approved / len(reviewed) * 100) if reviewed else 0,
            "avg_review_hours": 0,
        },
        "drafts": drafts[:8],
        "events": state["events"][:8],
    }


@app.get("/api/brand-library")
def brand_library(user: dict = Depends(get_current_user)) -> dict:
    return _workspace(user)["brand"]


@app.post("/api/brand-library/sources")
def add_source(payload: SourceCreate, user: dict = Depends(require_roles("admin"))) -> dict:
    state = _workspace(user)
    source = {
        "id": str(uuid4()),
        "title": payload.title.strip(),
        "type": payload.type,
        "summary": payload.content[:120] + ("…" if len(payload.content) > 120 else ""),
        "content": payload.content.strip(),
        "updated": datetime.now(timezone.utc).strftime("%b %d, %Y"),
        "status": "Approved",
        "approved_by": user["id"],
    }
    state["brand"]["sources"].insert(0, source)
    _event(state, None, user["name"], "Approved brand guidance added", source["title"])
    _save(state, user)
    return source


@app.post("/api/brand-library/facts")
def add_fact(payload: FactCreate, user: dict = Depends(require_roles("admin"))) -> dict:
    state = _workspace(user)
    fact = {
        "id": str(uuid4()),
        "title": payload.title.strip(),
        "value": payload.value.strip(),
        "match_key": payload.match_key.strip().lower(),
        "source_excerpt": payload.source_excerpt.strip(),
        "status": "approved",
        "updated": datetime.now(timezone.utc).strftime("%b %d, %Y"),
        "approved_by": user["id"],
    }
    state["brand"]["facts"].insert(0, fact)
    _event(state, None, user["name"], "Approved fact added", fact["title"])
    _save(state, user)
    return fact


@app.post("/api/brand-library/terminology")
def add_terminology(payload: TerminologyCreate, user: dict = Depends(require_roles("admin"))) -> dict:
    state = _workspace(user)
    term = {
        "id": str(uuid4()),
        "preferred": payload.preferred.strip(),
        "avoid": [value.strip() for value in payload.avoid if value.strip()],
        "reason": payload.reason.strip(),
        "severity": payload.severity,
        "source_id": "admin-approved",
        "source_title": "Administrator-approved terminology",
        "source_excerpt": payload.reason.strip(),
    }
    state["brand"]["terminology"].insert(0, term)
    _event(state, None, user["name"], "Approved terminology added", term["preferred"])
    _save(state, user)
    return term


@app.get("/api/drafts")
def list_drafts(user: dict = Depends(get_current_user)) -> list[dict]:
    return _workspace(user)["drafts"]


@app.post("/api/drafts")
def create_draft(payload: DraftCreate, user: dict = Depends(get_current_user)) -> dict:
    state = _workspace(user)
    draft = {
        "id": str(uuid4()),
        "organization_id": user["organization_id"],
        "title": payload.title.strip(),
        "channel": payload.channel,
        "text": payload.text.strip(),
        "status": "draft",
        "author": user["name"],
        "author_id": user["id"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "revision": 1,
        "findings": [],
        "sources_used": [],
        "analysis_mode": "",
        "provider_note": "",
        "review_comment": "",
    }
    state["drafts"].insert(0, draft)
    _event(state, draft, user["name"], "Draft created", draft["channel"])
    _save(state, user)
    return draft


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str, user: dict = Depends(get_current_user)) -> dict:
    return _draft(_workspace(user), draft_id)


@app.post("/api/drafts/{draft_id}/audit")
def audit_draft(draft_id: str, request: AuditRequest, user: dict = Depends(get_current_user)) -> dict:
    state = _workspace(user)
    draft = _draft(state, draft_id)
    sources = retrieve_sources(draft["text"], state["brand"], organization_id=user["organization_id"])
    findings = run_deterministic_checks(draft["text"], state["brand"])
    provider_note = "Deterministic rules and approved-source retrieval completed."
    analysis_mode = "rules + source retrieval"
    if QDRANT_URL:
        analysis_mode += " (Qdrant when available)"
    if request.include_ai:
        if GEMINI_API_KEY:
            try:
                ai_findings = run_gemini_analysis(draft["text"], sources)
                findings.extend(ai_findings)
                analysis_mode += " + Gemini"
                provider_note = "Gemini findings are evidence-checked suggestions for human review."
            except RuntimeError:
                analysis_mode += " · Gemini unavailable"
                provider_note = "Gemini could not complete this check. Deterministic findings remain available."
        else:
            analysis_mode += " · Gemini not configured"
            provider_note = "No external AI provider was called. Deterministic checks and approved evidence are available."
    previous = {
        (item.get("category"), item.get("title"), item.get("excerpt", "").lower()): item.get("decision", "open")
        for item in draft.get("findings", [])
    }
    for finding in findings:
        finding["decision"] = previous.get((finding.get("category"), finding.get("title"), finding.get("excerpt", "").lower()), "open")
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    deduped = {}
    for finding in findings:
        deduped[(finding["category"], finding["title"], finding["excerpt"].lower())] = finding
    findings = sorted(deduped.values(), key=lambda item: (severity_order.get(item.get("severity"), 4), -item.get("confidence", 0)))
    draft["findings"] = findings
    draft["sources_used"] = sources
    draft["analysis_mode"] = analysis_mode
    draft["provider_note"] = provider_note
    draft["status"] = "needs_review" if findings else "ready_for_review"
    draft["updated_at"] = now_iso()
    _event(state, draft, user["name"], "Compliance check completed", f"{len(findings)} findings · {analysis_mode}")
    _save(state, user)
    return draft


@app.patch("/api/drafts/{draft_id}/findings/{finding_id}")
def update_finding(draft_id: str, finding_id: str, payload: FindingUpdate, user: dict = Depends(get_current_user)) -> dict:
    state = _workspace(user)
    draft = _draft(state, draft_id)
    finding = next((item for item in draft["findings"] if item["id"] == finding_id), None)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    changed_text = False
    if payload.decision == "edited":
        if not payload.suggestion:
            raise HTTPException(status_code=422, detail="Enter a correction before applying an edit.")
        finding["suggestion"] = payload.suggestion.strip()
        finding["decision"] = "accepted"
        if finding.get("excerpt"):
            draft["text"] = draft["text"].replace(finding["excerpt"], payload.suggestion.strip(), 1)
            changed_text = True
    elif payload.decision == "accepted":
        if finding.get("excerpt") and finding.get("suggestion"):
            draft["text"] = draft["text"].replace(finding["excerpt"], finding["suggestion"], 1)
            changed_text = True
        finding["decision"] = "accepted"
    else:
        finding["decision"] = payload.decision
    if changed_text:
        draft["revision"] += 1
        draft["status"] = "draft"
    draft["updated_at"] = now_iso()
    _event(state, draft, user["name"], "Suggestion " + ("applied" if finding["decision"] == "accepted" else "dismissed"), finding["title"])
    _save(state, user)
    return {"draft": draft, "finding": finding}


@app.post("/api/drafts/{draft_id}/submit-review")
def submit_for_review(draft_id: str, user: dict = Depends(get_current_user)) -> dict:
    state = _workspace(user)
    draft = _draft(state, draft_id)
    if not draft.get("findings") and not draft.get("analysis_mode"):
        raise HTTPException(status_code=409, detail="Run a brand check before submitting this draft for review.")
    if draft["status"] == "published":
        raise HTTPException(status_code=409, detail="This draft has already been published.")
    draft["status"] = "in_review"
    draft["updated_at"] = now_iso()
    _event(state, draft, user["name"], "Submitted for review", "A human approval decision is required before publication.")
    _save(state, user)
    return draft


@app.post("/api/drafts/{draft_id}/review")
def review_draft(draft_id: str, payload: ReviewRequest, user: dict = Depends(require_roles("admin", "reviewer"))) -> dict:
    state = _workspace(user)
    draft = _draft(state, draft_id)
    if payload.action == "approved":
        blockers = [item for item in draft.get("findings", []) if item.get("decision") == "open" and item.get("severity") in {"critical", "high"}]
        if blockers:
            raise HTTPException(status_code=409, detail="Resolve or dismiss critical and high findings before approving this draft.")
    draft["status"] = "approved" if payload.action == "approved" else "changes_requested"
    draft["review_comment"] = payload.comment
    draft["reviewed_by"] = user["id"]
    draft["reviewed_at"] = now_iso()
    draft["updated_at"] = now_iso()
    action = "Approved" if payload.action == "approved" else "Changes requested"
    _event(state, draft, user["name"], action, payload.comment or "Review decision recorded.")
    _save(state, user)
    return draft


@app.post("/api/drafts/{draft_id}/publish")
def publish_draft(draft_id: str, user: dict = Depends(require_roles("admin", "reviewer"))) -> dict:
    state = _workspace(user)
    draft = _draft(state, draft_id)
    if draft.get("status") != "approved":
        raise HTTPException(status_code=409, detail="A reviewer must approve this draft before publication.")
    open_findings = [item for item in draft.get("findings", []) if item.get("decision") == "open"]
    if open_findings:
        raise HTTPException(status_code=409, detail="Resolve every finding before publishing this draft.")
    draft["status"] = "published"
    draft["published_at"] = now_iso()
    draft["published_by"] = user["id"]
    draft["updated_at"] = now_iso()
    _event(state, draft, user["name"], "Published", "All findings were resolved and human approval was recorded.")
    _save(state, user)
    return draft


@app.get("/api/review-queue")
def review_queue(user: dict = Depends(require_roles("admin", "reviewer"))) -> list[dict]:
    state = _workspace(user)
    return [draft for draft in state["drafts"] if draft["status"] in {"needs_review", "in_review", "changes_requested"}]


@app.get("/api/audit-log")
def audit_log(user: dict = Depends(get_current_user)) -> list[dict]:
    return _workspace(user)["events"]


@app.get("/api/analytics")
def analytics(user: dict = Depends(get_current_user)) -> dict:
    state = _workspace(user)
    drafts = state["drafts"]
    counts: dict[str, int] = {}
    for draft in drafts:
        for finding in draft.get("findings", []):
            counts[finding["category"]] = counts.get(finding["category"], 0) + 1
    today = datetime.now(timezone.utc).date()
    labels = [(today - timedelta(days=offset)) for offset in range(6, -1, -1)]
    bars = []
    for day in labels:
        count = sum(1 for draft in drafts if str(draft.get("created_at", ""))[:10] == day.isoformat())
        bars.append({"day": day.strftime("%a"), "value": count})
    reviewed = [draft for draft in drafts if draft["status"] in {"approved", "changes_requested", "published"}]
    approved = sum(1 for draft in reviewed if draft["status"] in {"approved", "published"})
    return {
        "total_drafts": len(drafts),
        "approved": approved,
        "approval_rate": round(approved / len(reviewed) * 100) if reviewed else 0,
        "avg_review_hours": 0,
        "category_counts": counts,
        "weekly_activity": bars,
        "events": state["events"][:10],
    }


@app.post("/api/rule-proposals", status_code=201)
def create_rule_proposal(payload: RuleProposalCreate, user: dict = Depends(get_current_user)) -> dict:
    state = _workspace(user)
    if payload.draft_id:
        _draft(state, payload.draft_id)
    proposal = {
        "id": str(uuid4()),
        "title": payload.title.strip(),
        "proposed_text": payload.proposed_text.strip(),
        "rationale": payload.rationale.strip(),
        "draft_id": payload.draft_id,
        "finding_id": payload.finding_id,
        "submitted_by": user["id"],
        "submitted_by_name": user["name"],
        "status": "pending",
        "created_at": now_iso(),
        "decision_comment": "",
    }
    state.setdefault("proposals", []).insert(0, proposal)
    _event(state, None, user["name"], "Rule improvement proposed", proposal["title"])
    _save(state, user)
    return proposal


@app.get("/api/admin/dashboard")
def admin_dashboard(user: dict = Depends(require_roles("admin"))) -> dict:
    state = _workspace(user)
    users = auth_store.list_users(user["organization_id"])
    organization = auth_store.organization(user["organization_id"])
    proposals = state.get("proposals", [])
    return {
        "organization": organization,
        "users": [public_user(item) | {"created_at": item.get("created_at")} for item in users],
        "proposals": proposals,
        "drafts": state["drafts"],
        "metrics": {
            "users": len(users),
            "active_users": sum(1 for item in users if item.get("active")),
            "pending_proposals": sum(1 for item in proposals if item.get("status") == "pending"),
            "approved_rules": len(state["brand"].get("sources", [])) + len(state["brand"].get("facts", [])) + len(state["brand"].get("terminology", [])),
            "submissions": len(state["drafts"]),
        },
        "brand": state["brand"],
    }


@app.patch("/api/admin/organization")
def update_organization(payload: OrganizationUpdate, user: dict = Depends(require_roles("admin"))) -> dict:
    updated = auth_store.update_organization(
        user["organization_id"],
        {"name": payload.name.strip(), "industry": payload.industry.strip(), "tagline": payload.tagline.strip()},
    )
    state = _workspace(user)
    state["brand"]["organization"].update({key: updated[key] for key in ("name", "industry", "tagline")})
    _save(state, user)
    _event(state, None, user["name"], "Organization profile updated", updated["name"])
    return updated


@app.patch("/api/admin/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, user: dict = Depends(require_roles("admin"))) -> dict:
    target = auth_store.user_by_id(user_id)
    if not target or target.get("organization_id") != user["organization_id"]:
        raise HTTPException(status_code=404, detail="User not found in this organization.")
    changes = payload.model_dump(exclude_none=True)
    if user_id == user["id"] and changes.get("active") is False:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own administrator account.")
    if target.get("role") == "admin" and (changes.get("role") != "admin" or changes.get("active") is False):
        admins = [item for item in auth_store.list_users(user["organization_id"]) if item.get("role") == "admin" and item.get("active")]
        if len(admins) <= 1:
            raise HTTPException(status_code=409, detail="Keep at least one active administrator in the organization.")
    updated = auth_store.update_user(user_id, changes)
    state = _workspace(user)
    _event(state, None, user["name"], "User access updated", f"{target['email']} · {', '.join(changes.keys())}")
    _save(state, user)
    return public_user(updated)


@app.post("/api/admin/users", status_code=202)
def invite_user(payload: AdminUserCreate, user: dict = Depends(require_roles("admin"))) -> dict:
    email = normalize_email(str(payload.email))
    if not password_is_strong(payload.temporary_password):
        raise HTTPException(status_code=422, detail="Use at least 10 characters with an uppercase letter, lowercase letter, and number in the temporary password.")
    if auth_store.user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    new_user = {
        "id": str(uuid4()),
        "email": email,
        "name": payload.name.strip(),
        "password_hash": hash_password(payload.temporary_password),
        "role": payload.role,
        "organization_id": user["organization_id"],
        "email_verified": False,
        "active": True,
        "created_at": utcnow(),
        "invited_by": user["id"],
    }
    try:
        auth_store.create_user(new_user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _send_code(new_user, "verify_email")
    state = _workspace(user)
    _event(state, None, user["name"], "Organization member invited", email)
    _save(state, user)
    return {"user": public_user(new_user), "message": "Invitation created. Share the temporary password securely; the member must verify their email before signing in."}


@app.get("/api/admin/proposals")
def list_rule_proposals(user: dict = Depends(require_roles("admin"))) -> list[dict]:
    return _workspace(user).get("proposals", [])


@app.post("/api/admin/proposals/{proposal_id}/decision")
def decide_rule_proposal(proposal_id: str, payload: ProposalDecision, user: dict = Depends(require_roles("admin"))) -> dict:
    state = _workspace(user)
    proposal = next((item for item in state.get("proposals", []) if item["id"] == proposal_id), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Rule proposal not found.")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=409, detail="This proposal already has an administrator decision.")
    proposal["status"] = payload.decision
    proposal["decision_comment"] = payload.comment.strip()
    proposal["decided_by"] = user["id"]
    proposal["decided_at"] = now_iso()
    if payload.decision == "approved":
        source = {
            "id": str(uuid4()),
            "title": proposal["title"],
            "type": "Admin-approved rule improvement",
            "summary": proposal["proposed_text"][:120],
            "content": proposal["proposed_text"],
            "updated": datetime.now(timezone.utc).strftime("%b %d, %Y"),
            "status": "Approved",
            "approved_by": user["id"],
            "proposal_id": proposal_id,
        }
        state["brand"]["sources"].insert(0, source)
    _event(state, None, user["name"], f"Rule proposal {payload.decision}", proposal["title"])
    _save(state, user)
    return proposal


@app.get("/")
def root() -> dict:
    return {"message": "BrandGuard AI API is running.", "docs": "/docs"}
