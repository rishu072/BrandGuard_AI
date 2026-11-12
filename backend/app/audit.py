import json
import re
from typing import Any
from uuid import uuid4

from .config import GEMINI_API_KEY, GEMINI_MODEL
from .vector import retrieve_qdrant_sources


def _finding(
    *,
    category: str,
    severity: str,
    title: str,
    explanation: str,
    excerpt: str,
    suggestion: str,
    source_id: str,
    source_title: str,
    source_excerpt: str,
    confidence: int = 96,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "category": category,
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "excerpt": excerpt,
        "suggestion": suggestion,
        "source_id": source_id,
        "source_title": source_title,
        "source_excerpt": source_excerpt,
        "confidence": confidence,
        "decision": "open",
    }


def _sentence_excerpt(text: str, start: int, end: int) -> str:
    left = max((text.rfind(mark, 0, start) for mark in ".!?;\n"), default=-1) + 1
    right_candidates = [position for mark in ".!?;\n" if (position := text.find(mark, end)) >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return text[left:right].strip()


def run_deterministic_checks(text: str, brand: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for rule in brand.get("terminology", []):
        for variant in rule.get("avoid", []):
            match = re.search(re.escape(variant), text, re.IGNORECASE)
            if not match:
                continue
            findings.append(
                _finding(
                    category="Terminology",
                    severity=rule.get("severity", "medium"),
                    title="Use the approved brand name",
                    explanation=rule.get("reason", "Use the approved terminology consistently."),
                    excerpt=match.group(0),
                    suggestion=rule.get("preferred", ""),
                    source_id=rule.get("source_id", "voice"),
                    source_title=rule.get("source_title", "Terminology guide"),
                    source_excerpt=rule.get("source_excerpt", ""),
                    confidence=100,
                )
            )

    for fact in brand.get("facts", []):
        if fact.get("status") != "approved":
            continue
        key = fact.get("match_key", "").lower()
        approved_value = str(fact.get("value", ""))
        if key == "hydration":
            matches = list(re.finditer(r"\b(\d{1,3})\s*[- ]?\s*hour(?:s)?(?:\s+hydration)?\b", text, re.IGNORECASE))
            for match in matches:
                if match.group(1) != approved_value:
                    findings.append(
                        _finding(
                            category="Approved facts",
                            severity="high",
                            title="Hydration duration conflicts with the approved fact",
                            explanation="The draft gives a different duration than the approved product claim.",
                            excerpt=match.group(0),
                            suggestion=f"{approved_value}-hour hydration",
                            source_id=fact["id"],
                            source_title=fact["title"],
                            source_excerpt=fact["source_excerpt"],
                            confidence=100,
                        )
                    )
        elif key == "discount":
            matches = list(re.finditer(r"\b(\d{1,3})\s*%\s*(?:off|discount)\b", text, re.IGNORECASE))
            for match in matches:
                if match.group(1) != approved_value:
                    findings.append(
                        _finding(
                            category="Approved facts",
                            severity="critical",
                            title="Promotion amount is not approved",
                            explanation="The percentage in this draft does not match the active, approved offer.",
                            excerpt=match.group(0),
                            suggestion=f"{approved_value}% off",
                            source_id=fact["id"],
                            source_title=fact["title"],
                            source_excerpt=fact["source_excerpt"],
                            confidence=100,
                        )
                    )

    for pattern, title, explanation, source_excerpt, severity in [
        (
            r"\b(?:guaranteed|guarantee|cure|cures|cured|cures|treats?|heal(?:s|ed)?)\b",
            "Remove the medical or guaranteed outcome",
            "This wording promises a treatment result that the brand has not approved for marketing content.",
            "Product copy must not promise to cure, treat, or guarantee a health outcome.",
            "critical",
        ),
        (
            r"\b(?:#\s*1|number\s+one|best\s+in\s+(?:the\s+)?(?:world|india)|world'?s\s+best)\b",
            "Support or remove the superlative claim",
            "A top-ranked or 'best' claim needs current, approved substantiation.",
            "Comparative and ranking claims require a current approved evidence source.",
            "high",
        ),
        (
            r"\b(?:miracle|flawless|instant(?:ly)?|perfect)\b",
            "Replace exaggerated language",
            "This absolute or exaggerated phrasing conflicts with the brand's evidence-led voice.",
            "Use specific, balanced language. Avoid absolutes, miracle claims, and guaranteed results.",
            "medium",
        ),
    ]:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            excerpt = _sentence_excerpt(text, match.start(), match.end())
            if severity == "critical":
                suggestion = "Describe an approved product benefit without promising a medical outcome."
            elif severity == "high":
                suggestion = "Describe a substantiated product benefit and remove the unsupported ranking."
            else:
                suggestion = "A thoughtfully formulated serum for your everyday skin care routine."
            findings.append(
                _finding(
                    category="Claims",
                    severity=severity,
                    title=title,
                    explanation=explanation,
                    excerpt=excerpt,
                    suggestion=suggestion,
                    source_id="claims",
                    source_title="Claims and evidence policy",
                    source_excerpt=source_excerpt,
                    confidence=94,
                )
            )

    if re.search(r"\bskincare\b", text, re.IGNORECASE):
        match = re.search(r"\bskincare\b", text, re.IGNORECASE)
        findings.append(
            _finding(
                category="Terminology",
                severity="low",
                title="Use the preferred product category term",
                explanation="The brand style guide uses 'skin care' as two words.",
                excerpt=match.group(0),
                suggestion="skin care",
                source_id="terminology",
                source_title="Brand terminology",
                source_excerpt="Preferred: skin care. Avoid: skincare.",
                confidence=100,
            )
        )

    return _dedupe(findings)


def retrieve_sources(
    text: str,
    brand: dict[str, Any],
    limit: int = 4,
    organization_id: str = "org-demo",
) -> list[dict[str, str]]:
    approved = [
        source
        for source in brand.get("sources", [])
        if source.get("status", "Approved").lower() == "approved"
    ] + [fact for fact in brand.get("facts", []) if fact.get("status", "").lower() == "approved"]
    by_id = {str(source.get("id", "")): source for source in approved}
    vector_results = retrieve_qdrant_sources(text, brand, organization_id, limit)
    if vector_results is not None:
        safe_results = []
        for result in vector_results:
            source = by_id.get(str(result.get("id", "")))
            if not source:
                continue
            excerpt = source.get("source_excerpt") or source.get("content") or source.get("summary", "")
            if excerpt:
                safe_results.append(
                    {
                        "id": str(source.get("id", "")),
                        "title": str(source.get("title", "Approved source")),
                        "excerpt": str(excerpt)[:1200],
                    }
                )
        return safe_results[:limit]

    terms = {token.lower() for token in re.findall(r"[A-Za-z]{3,}", text)}
    candidates = approved
    scored: list[tuple[int, dict[str, str]]] = []
    for source in candidates:
        haystack = " ".join(
            str(source.get(key, ""))
            for key in ("title", "summary", "content", "source_excerpt", "value")
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append(
                (
                    score,
                    {
                        "id": source.get("id", ""),
                        "title": source.get("title", "Approved source"),
                        "excerpt": source.get("source_excerpt") or source.get("content") or source.get("summary", ""),
                    },
                )
            )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [source for _, source in scored[:limit]]


def run_gemini_analysis(text: str, sources: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not GEMINI_API_KEY:
        return []
    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        source_text = "\n".join(
            f"- {item.get('title')}: {item.get('excerpt')}" for item in sources
        ) or "- No relevant approved source found."
        prompt = f"""
You are a cautious brand-compliance reviewer. Review the submitted marketing text using only the approved source excerpts below.
Return a JSON array with zero to four findings. Each item must have: category, severity (low, medium, high, critical), title,
explanation, excerpt (exact words from the draft), suggestion (a minimal, purpose-preserving rewrite), source_title,
source_excerpt, confidence (integer 0-100). Do not invent facts. If the evidence is insufficient, do not make a factual accusation.
Approved sources:
{source_text}

Draft:
{text}
"""
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.15},
        )
        decoded = json.loads(response.text or "[]")
        if isinstance(decoded, dict):
            decoded = decoded.get("findings", [])
        findings: list[dict[str, Any]] = []
        for item in decoded[:4]:
            if not isinstance(item, dict) or not item.get("excerpt"):
                continue
            excerpt = str(item["excerpt"])
            if excerpt.lower() not in text.lower():
                continue
            cited_title = str(item.get("source_title", "")).strip().lower()
            approved_source = next(
                (source for source in sources if source.get("title", "").strip().lower() == cited_title),
                None,
            )
            if approved_source is None:
                continue
            severity = str(item.get("severity", "medium")).lower()
            if severity not in {"low", "medium", "high", "critical"}:
                severity = "medium"
            findings.append(
                _finding(
                    category=str(item.get("category", "Tone and messaging")),
                    severity=severity,
                    title=str(item.get("title", "Review this phrasing")),
                    explanation=str(item.get("explanation", "Review this phrase against the approved brand sources.")),
                    excerpt=excerpt,
                    suggestion=str(item.get("suggestion", "")),
                    source_id=approved_source.get("id", ""),
                    source_title=approved_source.get("title", "Approved source"),
                    source_excerpt=approved_source.get("excerpt", ""),
                    confidence=max(0, min(100, int(item.get("confidence", 70)))),
                )
            )
        return findings
    except Exception as exc:
        raise RuntimeError("Gemini provider request failed.") from exc


def _dedupe(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in findings:
        key = (item["category"], item["excerpt"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    unique.sort(key=lambda item: (severity_order.get(item["severity"], 4), -item["confidence"]))
    return unique
