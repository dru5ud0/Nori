"""Local recruiter/vendor CRM and STEM-OPT qualification scoring.

The networking store is deliberately separate from the application store. It
tracks public professional information, evidence, recruiter/vendor signals,
relationship status, and review-only outreach drafts. Nothing in this module
sends a message or performs an external account action.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

try:  # Windows process-safe byte-range locking.
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows fallback
    msvcrt = None


_DEFAULT_STORE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "loot", "state", "networking.json",
)

STATUSES = (
    "discovered", "vetted", "contacted", "replied", "rtr",
    "submitted", "interview", "closed", "archived",
)

CHICAGO_TERMS = (
    "chicago", "chicagoland", "illinois", "elk grove village",
    "schaumburg", "naperville", "oak brook", "oakbrook", "rosemont",
    "downers grove", "deerfield", "northbrook", "arlington heights",
    "hoffman estates", "lisle", "lombard", "itasca", "des plaines",
    "evanston", "skokie", "united airlines", "ual",
)

_SIGNAL_PATTERNS = {
    "chicagoRelevant": re.compile(
        r"\b(?:" + "|".join(re.escape(term) for term in CHICAGO_TERMS) + r")\b",
        re.IGNORECASE,
    ),
    "directClient": re.compile(r"\bdirect\s+(?:end\s+)?clients?\b", re.IGNORECASE),
    "w2": re.compile(r"\bw\s*[-/]?\s*2\b", re.IGNORECASE),
    "c2c": re.compile(r"\bc\s*[-/]?\s*2\s*[-/]?\s*c\b|corp(?:oration)?\s+to\s+corp", re.IGNORECASE),
    "rtr": re.compile(r"\brtr\b|right\s+to\s+represent", re.IGNORECASE),
    "optEad": re.compile(r"\bopt(?:\s+ead)?\b", re.IGNORECASE),
    "stemOpt": re.compile(r"\bstem\s*opt\b", re.IGNORECASE),
    "eVerify": re.compile(r"\be\s*[- ]?verify\b", re.IGNORECASE),
    "i983": re.compile(r"\b(?:form\s+)?i\s*[- ]?983\b", re.IGNORECASE),
    "h1b": re.compile(r"\bh\s*[- ]?1b\b|visa\s+sponsorship", re.IGNORECASE),
    "unitedAirlines": re.compile(r"\bunited\s+airlines\b|\bual\b", re.IGNORECASE),
}

_SCORE_WEIGHTS = {
    "chicagoRelevant": 15,
    "directClient": 15,
    "w2": 12,
    "c2c": 4,
    "rtr": 5,
    "optEad": 12,
    "stemOpt": 10,
    "eVerify": 10,
    "i983": 10,
    "h1b": 3,
    "unitedAirlines": 9,
}

_RISK_PATTERNS = {
    "upfront-fee": re.compile(r"upfront fee|training fee|registration fee|pay us", re.IGNORECASE),
    "sensitive-id-request": re.compile(r"send (?:your )?(?:ssn|passport|ead card|bank|credit card)", re.IGNORECASE),
    "1099-only": re.compile(r"1099\s+only|only\s+1099", re.IGNORECASE),
    "vague-client": re.compile(r"confidential client|client cannot be disclosed", re.IGNORECASE),
}


def default_network_store_path() -> str:
    """Return the absolute local networking-store path.

    Returns:
        Absolute path to ``loot/state/networking.json``. The parent directory
        is created when a record is first saved.
    """
    return os.path.abspath(_DEFAULT_STORE)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_url(value: str) -> str:
    try:
        parts = urlsplit(str(value or "").strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return ""
        hostname = parts.hostname.lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        netloc = hostname
        if parts.port:
            netloc = f"{hostname}:{parts.port}"
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), netloc, path, "", ""))
    except Exception:
        return ""


def _text_blob(contact: dict) -> str:
    evidence = contact.get("evidence") or []
    evidence_text = " ".join(
        str(item.get("text") or "") for item in evidence if isinstance(item, dict)
    )
    values = [
        contact.get("name"), contact.get("headline"), contact.get("location"),
        contact.get("company"), contact.get("about"), contact.get("rawText"),
        contact.get("notes"), " ".join(contact.get("tags") or []), evidence_text,
    ]
    return "\n".join(str(value or "") for value in values)


def _score_contact(contact: dict) -> dict:
    text = _text_blob(contact)
    explicit = contact.get("signals") if isinstance(contact.get("signals"), dict) else {}
    signals = {
        name: bool(explicit.get(name)) or bool(pattern.search(text))
        for name, pattern in _SIGNAL_PATTERNS.items()
    }
    risk_flags = list(contact.get("riskFlags") or [])
    for flag, pattern in _RISK_PATTERNS.items():
        if pattern.search(text) and flag not in risk_flags:
            risk_flags.append(flag)

    reasons = []
    score = 0
    for name, weight in _SCORE_WEIGHTS.items():
        if signals.get(name):
            score += weight
            reasons.append({"signal": name, "points": weight})
    if contact.get("email"):
        score += 3
        reasons.append({"signal": "contactable", "points": 3})
    degree = str(contact.get("connectionDegree") or "").lower()
    if degree.startswith("1"):
        score += 5
        reasons.append({"signal": "firstDegree", "points": 5})

    penalties = {
        "upfront-fee": 40,
        "sensitive-id-request": 35,
        "1099-only": 18,
        "vague-client": 8,
        "duplicate-rtr": 25,
    }
    for flag in risk_flags:
        penalty = penalties.get(flag, 0)
        if penalty:
            score -= penalty
            reasons.append({"signal": flag, "points": -penalty})

    return {
        "score": max(0, min(100, score)),
        "signals": signals,
        "riskFlags": sorted(set(risk_flags)),
        "scoreReasons": reasons,
    }


def network_score(contact: dict) -> str:
    """Score a recruiter/vendor record without persisting it.

    Args:
        contact: Contact dictionary containing public profile fields, evidence,
            optional explicit signals, and risk flags.

    Returns:
        JSON string containing ``score``, detected ``signals``, ``riskFlags``,
        and point-by-point ``scoreReasons``. Errors are returned as JSON.
    """
    try:
        return json.dumps({"ok": True, **_score_contact(dict(contact or {}))})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def _load_store(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("contacts"), dict):
            data.setdefault("relationships", [])
            return data
    except Exception:
        pass
    return {"contacts": {}, "relationships": []}


def _save_store(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


@contextmanager
def _store_lock(path: str, timeout_ms: int = 15000):
    if msvcrt is None:
        yield
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle = open(path + ".lock", "a+")
    deadline = time.time() + timeout_ms / 1000.0
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            if time.time() >= deadline:
                handle.close()
                raise OSError("network-store-lock-timeout")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()


def _merge_evidence(existing: list, incoming: list) -> list:
    merged = list(existing or [])
    seen = {
        (str(item.get("sourceUrl") or ""), str(item.get("text") or ""))
        for item in merged if isinstance(item, dict)
    }
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        normalized = {
            "sourceUrl": _normalize_url(item.get("sourceUrl") or ""),
            "text": str(item.get("text") or "").strip()[:12000],
            "capturedAt": int(item.get("capturedAt") or _now_ms()),
            "kind": str(item.get("kind") or "profile"),
        }
        key = (normalized["sourceUrl"], normalized["text"])
        if normalized["text"] and key not in seen:
            merged.append(normalized)
            seen.add(key)
    return merged[-100:]


def network_upsert_contact(contact: dict, store_path: str | None = None) -> str:
    """Create or update a recruiter/vendor contact in the local store.

    Deduplication uses normalized LinkedIn URL first, then email. New evidence
    is appended without duplicates and the qualification score is recomputed.

    Args:
        contact: Contact dictionary. Common fields are ``name``, ``linkedinUrl``,
            ``headline``, ``location``, ``company``, ``email``, ``about``,
            ``rawText``, ``evidence``, ``signals``, ``tags``, and ``status``.
        store_path: Optional alternate JSON store path for tests or isolation.

    Returns:
        JSON string containing ``ok``, ``created``, and the normalized
        ``contact``. Errors are returned as JSON and never raised.
    """
    path = os.path.abspath(store_path or default_network_store_path())
    try:
        incoming = dict(contact or {})
        for key, limit in {
            "name": 200, "headline": 500, "location": 300, "company": 300,
            "email": 320, "about": 12000, "rawText": 50000, "notes": 12000,
        }.items():
            if key in incoming and incoming[key] is not None:
                incoming[key] = str(incoming[key]).strip()[:limit]
        if isinstance(incoming.get("tags"), list):
            incoming["tags"] = list(dict.fromkeys(str(tag).strip()[:80] for tag in incoming["tags"] if str(tag).strip()))[:50]
        linkedin_url = _normalize_url(incoming.get("linkedinUrl") or incoming.get("url") or "")
        email = str(incoming.get("email") or "").strip().lower()
        if linkedin_url:
            parts = urlsplit(linkedin_url)
            if parts.hostname and parts.hostname.endswith("linkedin.com") and not parts.path.startswith("/in/"):
                return json.dumps({"ok": False, "error": "invalid-linkedin-profile-url"})
        if not incoming.get("name") and not linkedin_url and not email:
            return json.dumps({"ok": False, "error": "contact-identity-required"})

        with _store_lock(path):
            store = _load_store(path)
            existing_id = ""
            for contact_id, item in store["contacts"].items():
                if linkedin_url and _normalize_url(item.get("linkedinUrl") or "") == linkedin_url:
                    existing_id = contact_id
                    break
                if email and str(item.get("email") or "").lower() == email:
                    existing_id = contact_id
                    break

            created = not bool(existing_id)
            contact_id = existing_id or f"contact_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            current = dict(store["contacts"].get(contact_id) or {})
            record = dict(current)
            for key, value in incoming.items():
                if key in ("id", "score", "scoreReasons", "evidence"):
                    continue
                if value not in (None, "", [], {}):
                    record[key] = value
            record.update({
                "id": contact_id,
                "linkedinUrl": linkedin_url or current.get("linkedinUrl", ""),
                "email": email or current.get("email", ""),
                "status": str(record.get("status") or "discovered"),
                "createdAt": int(current.get("createdAt") or _now_ms()),
                "updatedAt": _now_ms(),
                "evidence": _merge_evidence(current.get("evidence") or [], incoming.get("evidence") or []),
            })
            if record["status"] not in STATUSES:
                record["status"] = "discovered"
            scored = _score_contact(record)
            record.update(scored)
            store["contacts"][contact_id] = record
            _save_store(store, path)
        return json.dumps({"ok": True, "created": created, "contact": record})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def network_list_contacts(
    store_path: str | None = None,
    query: str = "",
    status: str = "",
    chicago_only: bool = False,
) -> str:
    """List locally stored recruiter/vendor contacts.

    Args:
        store_path: Optional alternate JSON store path.
        query: Case-insensitive text search across name, employer, headline,
            location, notes, tags, and evidence.
        status: Optional exact pipeline status filter.
        chicago_only: When true, return only contacts with detected Chicago,
            Illinois, suburb, United Airlines, or UAL evidence.

    Returns:
        JSON string containing ``ok``, ``contacts``, ``count``, and summary
        counts. Errors are returned as JSON.
    """
    path = os.path.abspath(store_path or default_network_store_path())
    try:
        store = _load_store(path)
        contacts = list(store["contacts"].values())
        needle = str(query or "").strip().lower()
        if needle:
            contacts = [item for item in contacts if needle in _text_blob(item).lower()]
        if status:
            contacts = [item for item in contacts if item.get("status") == status]
        if chicago_only:
            contacts = [item for item in contacts if (item.get("signals") or {}).get("chicagoRelevant")]
        contacts.sort(key=lambda item: (int(item.get("score") or 0), int(item.get("updatedAt") or 0)), reverse=True)
        summary = {state: 0 for state in STATUSES}
        for item in store["contacts"].values():
            summary[item.get("status") or "discovered"] = summary.get(item.get("status") or "discovered", 0) + 1
        return json.dumps({
            "ok": True,
            "count": len(contacts),
            "contacts": contacts,
            "summary": summary,
            "relationships": store.get("relationships", []),
        })
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc), "contacts": [], "count": 0})


def network_get_contact(contact_id: str, store_path: str | None = None) -> str:
    """Get one recruiter/vendor contact by id.

    Args:
        contact_id: Local contact identifier.
        store_path: Optional alternate JSON store path.

    Returns:
        JSON string containing ``ok`` and ``contact``; returns ``not-found`` in
        the error field when absent. Never raises.
    """
    try:
        store = _load_store(os.path.abspath(store_path or default_network_store_path()))
        contact = store["contacts"].get(str(contact_id))
        if not contact:
            return json.dumps({"ok": False, "error": "not-found"})
        return json.dumps({"ok": True, "contact": contact})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def network_update_contact(
    contact_id: str,
    updates: dict,
    store_path: str | None = None,
) -> str:
    """Update status, notes, signals, tags, risks, or evidence for a contact.

    Args:
        contact_id: Existing local contact identifier.
        updates: Partial contact dictionary to merge.
        store_path: Optional alternate JSON store path.

    Returns:
        JSON string with the updated contact or a ``not-found`` error. The score
        is recomputed after every update. Never raises.
    """
    path = os.path.abspath(store_path or default_network_store_path())
    try:
        with _store_lock(path):
            store = _load_store(path)
            current = store["contacts"].get(str(contact_id))
            if not current:
                return json.dumps({"ok": False, "error": "not-found"})
            merged = dict(current)
            for key, value in dict(updates or {}).items():
                if key in ("id", "createdAt", "score", "scoreReasons", "evidence"):
                    continue
                merged[key] = value
            merged["evidence"] = _merge_evidence(current.get("evidence") or [], (updates or {}).get("evidence") or [])
            merged["updatedAt"] = _now_ms()
            if merged.get("status") not in STATUSES:
                merged["status"] = "discovered"
            merged.update(_score_contact(merged))
            store["contacts"][str(contact_id)] = merged
            _save_store(store, path)
        return json.dumps({"ok": True, "contact": merged})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def network_delete_contact(contact_id: str, store_path: str | None = None) -> str:
    """Delete an invalid or unwanted local networking contact.

    Args:
        contact_id: Existing local contact identifier.
        store_path: Optional alternate JSON store path.

    Returns:
        JSON string containing ``ok`` and ``deleted``. Returns ``not-found``
        when the contact is absent and never raises an unhandled exception.
    """
    path = os.path.abspath(store_path or default_network_store_path())
    try:
        with _store_lock(path):
            store = _load_store(path)
            if str(contact_id) not in store["contacts"]:
                return json.dumps({"ok": False, "error": "not-found"})
            del store["contacts"][str(contact_id)]
            store["relationships"] = [
                relation for relation in store.get("relationships", [])
                if relation.get("sourceId") != contact_id and relation.get("targetId") != contact_id
            ]
            _save_store(store, path)
        return json.dumps({"ok": True, "deleted": str(contact_id)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def network_draft_outreach(contact_id: str, store_path: str | None = None) -> str:
    """Create a review-only outreach draft for one contact.

    The draft states the Chicago-area search, STEM-OPT requirements, W2/E-Verify
    employer relationship, Form I-983 need, and role-specific RTR preference.
    It is stored locally but never sent.

    Args:
        contact_id: Existing local contact identifier.
        store_path: Optional alternate JSON store path.

    Returns:
        JSON string containing ``ok``, ``draft``, and the updated contact.
        Errors are returned as JSON and never raised.
    """
    path = os.path.abspath(store_path or default_network_store_path())
    try:
        found = json.loads(network_get_contact(contact_id, path))
        if not found.get("ok"):
            return json.dumps(found)
        contact = found["contact"]
        first_name = str(contact.get("name") or "there").split()[0]
        company = str(contact.get("company") or "your team")
        draft = (
            f"Hi {first_name}, I am exploring Chicago-area cybersecurity and cloud security "
            f"contract opportunities and saw your work with {company}. I am authorized to work "
            "on STEM OPT and need a W2 employer enrolled in E-Verify that can provide the "
            "required supervision and complete Form I-983. Do you currently represent any "
            "Chicago or nearby direct-client roles that fit? I am comfortable signing a "
            "role-specific RTR after confirming the end client, requisition, rate, employer, "
            "and vendor chain. Thank you."
        )
        updated = json.loads(network_update_contact(contact_id, {"outreachDraft": draft}, path))
        return json.dumps({"ok": bool(updated.get("ok")), "draft": draft, "contact": updated.get("contact")})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})
