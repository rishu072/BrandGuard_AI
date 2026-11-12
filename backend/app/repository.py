from copy import deepcopy
from datetime import datetime, timezone
import logging

from .config import DEFAULT_ORGANIZATION_ID, DEMO_MODE, MONGODB_DATABASE, MONGODB_URI

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def blank_state(organization: dict | None = None) -> dict:
    organization = organization or {}
    return {
        "brand": {
            "organization": {
                "name": organization.get("name", "New organization"),
                "industry": organization.get("industry", ""),
                "tagline": organization.get("tagline", ""),
                "brand_score": 0,
            },
            "sources": [],
            "facts": [],
            "terminology": [],
            "assets": [],
        },
        "drafts": [],
        "proposals": [],
        "events": [],
    }


def seed_state(organization: dict | None = None) -> dict:
    brand = {
        "organization": {
            "name": (organization or {}).get("name", "Aster & Oak"),
            "industry": (organization or {}).get("industry", "Science-led skin care"),
            "tagline": (organization or {}).get("tagline", "Care that feels like you."),
            "brand_score": 92,
        },
        "sources": [
            {
                "id": "voice",
                "title": "Voice & messaging guide",
                "type": "Guideline",
                "summary": "Warm, clear, evidence-led, and quietly optimistic.",
                "content": "Lead with useful specifics. Be warm, clear, evidence-led, and quietly optimistic. Never promise a guaranteed result.",
                "updated": "Oct 14, 2026",
                "status": "Approved",
            },
            {
                "id": "claims",
                "title": "Claims and evidence policy",
                "type": "Guideline",
                "summary": "Health, ranking, comparative, and guaranteed claims require substantiation.",
                "content": "Do not promise to cure, treat, or guarantee a health outcome. Comparative and ranking claims require a current approved evidence source.",
                "updated": "Oct 10, 2026",
                "status": "Approved",
            },
            {
                "id": "visuals",
                "title": "Visual identity quick guide",
                "type": "Asset guidance",
                "summary": "Use approved logo lockups and current packaging photography.",
                "content": "Use the current Aster & Oak logo lockup. Keep clear space around the mark and do not recolor it.",
                "updated": "Sep 28, 2026",
                "status": "Approved",
            },
        ],
        "facts": [
            {
                "id": "fact-hydration",
                "title": "Daily Veil hydration claim",
                "value": "48",
                "match_key": "hydration",
                "source_excerpt": "Daily Veil provides up to 48-hour hydration in the approved consumer claim.",
                "status": "approved",
                "updated": "Oct 18, 2026",
            },
            {
                "id": "fact-offer",
                "title": "November launch promotion",
                "value": "20",
                "match_key": "discount",
                "source_excerpt": "The active launch offer is 20% off through November 30, 2026.",
                "status": "approved",
                "updated": "Oct 20, 2026",
            },
            {
                "id": "fact-formula",
                "title": "Daily Veil formula",
                "value": "fragrance-free",
                "match_key": "formula",
                "source_excerpt": "Daily Veil is fragrance-free and suitable for sensitive skin.",
                "status": "approved",
                "updated": "Oct 08, 2026",
            },
        ],
        "terminology": [
            {
                "id": "term-name",
                "preferred": "Aster & Oak",
                "avoid": ["Aster and Oak"],
                "reason": "Use the approved ampersand brand lockup in running copy.",
                "severity": "medium",
                "source_id": "voice",
                "source_title": "Brand terminology",
                "source_excerpt": "The approved brand name is written as Aster & Oak.",
            },
            {
                "id": "term-category",
                "preferred": "skin care",
                "avoid": ["skincare"],
                "reason": "The brand style guide uses 'skin care' as two words.",
                "severity": "low",
                "source_id": "voice",
                "source_title": "Brand terminology",
                "source_excerpt": "Preferred: skin care. Avoid: skincare.",
            },
        ],
        "assets": [
            {
                "id": "asset-logo",
                "name": "Aster & Oak primary logo",
                "type": "Logo",
                "details": "Dark pine wordmark · SVG + PNG",
                "status": "Approved",
                "updated": "Sep 28, 2026",
            },
            {
                "id": "asset-daily-veil",
                "name": "Daily Veil product photography",
                "type": "Photography",
                "details": "Current packaging · 6 approved images",
                "status": "Approved",
                "updated": "Oct 06, 2026",
            },
        ],
    }
    draft_id = "draft-sample-01"
    sample = (
        "At Aster and Oak, our new Daily Veil serum is here. Get 40% off and enjoy "
        "72-hour hydration. This miracle serum is guaranteed to clear acne in one week. "
        "Shop now for the #1 skincare routine in India!"
    )
    from .audit import retrieve_sources, run_deterministic_checks

    sources = retrieve_sources(sample, brand)
    findings = run_deterministic_checks(sample, brand)
    draft = {
        "id": draft_id,
        "title": "Daily Veil launch · Instagram",
        "channel": "Instagram",
        "text": sample,
        "status": "needs_review",
        "author": "Maya Chen",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "revision": 1,
        "findings": findings,
        "sources_used": sources,
        "analysis_mode": "rules + source retrieval",
        "provider_note": "Demo mode · no external AI provider was called.",
        "review_comment": "",
    }
    sample_two_text = (
        "A softer start to your morning. Daily Veil gives skin up to 48-hour hydration, "
        "with a fragrance-free formula made for sensitive skin. Find your everyday ritual."
    )
    draft_two = {
        "id": "draft-sample-02",
        "title": "A softer morning · Email",
        "channel": "Email",
        "text": sample_two_text,
        "status": "in_review",
        "author": "Jordan Lee",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "revision": 1,
        "findings": [],
        "sources_used": retrieve_sources(sample_two_text, brand),
        "analysis_mode": "rules + source retrieval",
        "provider_note": "Demo mode · no external AI provider was called.",
        "review_comment": "",
    }
    sample_three_text = (
        "Make room for a calmer skincare ritual. Daily Veil is fragrance-free and "
        "ready for the everyday moments that feel like you."
    )
    third_findings = run_deterministic_checks(sample_three_text, brand)
    draft_three = {
        "id": "draft-sample-03",
        "title": "A calmer ritual · Blog",
        "channel": "Blog",
        "text": sample_three_text,
        "status": "needs_review",
        "author": "Maya Chen",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "revision": 1,
        "findings": third_findings,
        "sources_used": retrieve_sources(sample_three_text, brand),
        "analysis_mode": "rules + source retrieval",
        "provider_note": "Demo mode · no external AI provider was called.",
        "review_comment": "",
    }
    return {
        "brand": brand,
        "drafts": [draft, draft_two, draft_three],
        "proposals": [],
        "events": [
            {
                "id": "event-seed-01",
                "draft_id": draft_id,
                "draft_title": draft["title"],
                "actor": "Maya Chen",
                "action": "Submitted for review",
                "detail": "First compliance check completed",
                "created_at": now_iso(),
            },
            {
                "id": "event-seed-02",
                "draft_id": "draft-sample-02",
                "draft_title": "Autumn campaign · Email",
                "actor": "Jordan Lee",
                "action": "Submitted for review",
                "detail": "Email copy is ready for a human decision",
                "created_at": now_iso(),
            },
            {
                "id": "event-seed-03",
                "draft_id": "draft-sample-03",
                "draft_title": "Daily routine · Blog",
                "actor": "Maya Chen",
                "action": "Compliance check completed",
                "detail": "One terminology finding to review",
                "created_at": now_iso(),
            },
        ],
    }


class Repository:
    def __init__(self) -> None:
        self._memory: dict[str, dict] = {DEFAULT_ORGANIZATION_ID: seed_state()}
        self._collection = None
        self.mode = "demo-memory"
        if not DEMO_MODE:
            if not MONGODB_URI:
                raise RuntimeError("MONGODB_URI is required when DEMO_MODE=false.")
            try:
                from pymongo import MongoClient

                client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=1800, tz_aware=True)
                client.admin.command("ping")
                self._collection = client[MONGODB_DATABASE]["workspaces"]
                self.mode = "mongodb"
            except Exception as exc:
                raise RuntimeError("MongoDB could not be reached; production data will not fall back to memory.") from exc

    def load(self, organization_id: str = DEFAULT_ORGANIZATION_ID, organization: dict | None = None) -> dict:
        if self._collection is not None:
            saved = self._collection.find_one({"_id": organization_id})
            if saved is None and organization_id == DEFAULT_ORGANIZATION_ID:
                saved = self._collection.find_one({"_id": "state"})
            if saved:
                saved.pop("_id", None)
                self._memory[organization_id] = saved
                if organization_id not in {"org-demo", ""}:
                    saved.setdefault("brand", {}).setdefault("organization", {})
                    org = saved["brand"]["organization"]
                    if organization:
                        org.update({k: organization[k] for k in ("name", "industry", "tagline") if k in organization})
            else:
                self._memory[organization_id] = seed_state(organization) if organization_id == DEFAULT_ORGANIZATION_ID else blank_state(organization)
                self.save(self._memory[organization_id], organization_id)
        elif organization_id not in self._memory:
            self._memory[organization_id] = seed_state(organization) if organization_id == DEFAULT_ORGANIZATION_ID else blank_state(organization)
        elif organization and organization_id != DEFAULT_ORGANIZATION_ID:
            org = self._memory[organization_id]["brand"]["organization"]
            org.update({k: organization[k] for k in ("name", "industry", "tagline") if k in organization})
        return deepcopy(self._memory[organization_id])

    def save(self, state: dict, organization_id: str = DEFAULT_ORGANIZATION_ID) -> None:
        self._memory[organization_id] = deepcopy(state)
        if self._collection is not None:
            self._collection.replace_one({"_id": organization_id}, {"_id": organization_id, **state}, upsert=True)


repository = Repository()
