"""Nori Gmail — read-only OAuth, bounded metadata sync, and job-mail labels.

This module never sends email and never requests message-modification scopes.
OAuth tokens are encrypted for the current Windows user with DPAPI. Synced
headers and short snippets are stored in the local Nori state directory.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
_MAX_RESPONSE = 2_000_000
_FLOW_SECONDS = 600


class GmailError(Exception):
    """Sanitized Gmail integration error that never includes credentials."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte))]


class WindowsDPAPISecretStore:
    """Encrypt small OAuth records for the current Windows user."""

    _ENTROPY = b"Nori AI Gmail OAuth v1"

    def __init__(self, directory: str | Path | None = None) -> None:
        if sys.platform != "win32":
            raise GmailError("Gmail credential storage currently requires Windows.")
        root = Path(directory) if directory else Path(
            os.environ.get("LOCALAPPDATA") or Path.home()
        ) / "NoriAI" / "gmail"
        self.directory = root

    @staticmethod
    def _blob(data: bytes):
        buffer = ctypes.create_string_buffer(data)
        return (_DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))),
                buffer)

    def _crypt(self, data: bytes, protect: bool) -> bytes:
        source, source_buffer = self._blob(data)
        entropy, entropy_buffer = self._blob(self._ENTROPY)
        output = _DataBlob()
        function = (ctypes.windll.crypt32.CryptProtectData if protect
                    else ctypes.windll.crypt32.CryptUnprotectData)
        try:
            ok = function(ctypes.byref(source), None, ctypes.byref(entropy),
                          None, None, 0x1, ctypes.byref(output))
            if not ok:
                raise GmailError("Windows could not protect the Gmail credentials.")
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            del source_buffer, entropy_buffer
            if output.pbData:
                ctypes.windll.kernel32.LocalFree(output.pbData)

    def _path(self, name: str) -> Path:
        return self.directory / f"{hashlib.sha256(name.encode('utf-8')).hexdigest()}.bin"

    def get(self, name: str) -> str | None:
        """Return one decrypted value, or ``None`` when absent."""
        try:
            path = self._path(name)
            if not path.is_file():
                return None
            return self._crypt(path.read_bytes(), False).decode("utf-8")
        except GmailError:
            raise
        except Exception as exc:
            raise GmailError("The saved Gmail credentials could not be read.") from exc

    def set(self, name: str, value: str) -> None:
        """Encrypt and atomically save one value."""
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self._path(name)
            temporary = path.with_suffix(f".{secrets.token_hex(6)}.tmp")
            temporary.write_bytes(self._crypt(value.encode("utf-8"), True))
            os.replace(temporary, path)
        except GmailError:
            raise
        except Exception as exc:
            raise GmailError("The Gmail credentials could not be saved.") from exc

    def delete(self, name: str) -> None:
        """Delete one local encrypted value when it exists."""
        try:
            self._path(name).unlink(missing_ok=True)
        except Exception as exc:
            raise GmailError("The Gmail credentials could not be removed.") from exc


@dataclass(frozen=True)
class JobMessage:
    """Bounded Gmail metadata shown in the Nori Inbox."""

    id: str
    threadId: str
    timestamp: int
    subject: str
    sender: str
    date: str
    snippet: str
    category: str
    confidence: str


_PATTERNS = {
    "verification": (r"\bverif(?:y|ication)\b.{0,80}\b(?:email|application|candidate)\b",),
    "acknowledgment": (r"\breceived your (?:job )?application\b",
                         r"\bthank you for (?:your interest|applying)\b"),
    "interview": (r"\binterview (?:availability|request|confirmation|details|invitation)\b",
                  r"\b(?:schedule|scheduling|reschedule)\b.{0,60}\binterview\b"),
    "offer": (r"\b(?:employment|job|formal) offer\b", r"\bextend (?:you )?an? offer\b"),
    "rejection": (r"\bnot (?:be )?moving forward\b", r"\bpursu(?:e|ing) other candidates\b",
                  r"\bposition has been filled\b"),
    "action_required": (r"\baction required\b", r"\bcomplete (?:the|your) (?:assessment|questionnaire)\b"),
}


def _classify_job_message(subject: str, snippet: str = "", sender: str = "") -> dict:
    """Classify job-mail text conservatively without a network request.

    Args:
        subject: message subject.
        snippet: short Gmail snippet.
        sender: sender header.

    Returns:
        dict: category, confidence, and all matched categories. Never raises.
    """
    try:
        text = " ".join(f"{subject} {snippet} {sender}".replace("\x00", " ").split())[:12000]
        matches = [name for name, patterns in _PATTERNS.items()
                   if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)]
        if len(matches) == 1:
            return {"category": matches[0], "confidence": "high", "matches": matches}
        if len(matches) > 1:
            return {"category": "ambiguous", "confidence": "low", "matches": matches}
        return {"category": "other", "confidence": "low", "matches": []}
    except Exception:
        return {"category": "other", "confidence": "low", "matches": []}


def _json_secret(store: WindowsDPAPISecretStore, name: str) -> dict:
    try:
        value = json.loads(store.get(name) or "null")
    except Exception as exc:
        raise GmailError("The saved Gmail authorization is invalid.") from exc
    if not isinstance(value, dict):
        raise GmailError("The saved Gmail authorization is missing.")
    return value


def _redirect(value: str):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except Exception as exc:
        raise GmailError("The Gmail redirect URL is invalid.") from exc
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or not port or parsed.query or parsed.fragment
            or parsed.path != "/api/inbox/gmail/callback"):
        raise GmailError("Gmail requires this Nori server's local callback URL.")
    return parsed


def _http_json(url: str, *, method: str = "GET", data: dict | None = None,
               headers: dict | None = None) -> dict:
    encoded = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(url, data=encoded, method=method,
                      headers=headers or {})
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(_MAX_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise GmailError("Google rejected or could not complete the Gmail request.") from exc
    if len(raw) > _MAX_RESPONSE:
        raise GmailError("The Gmail response was too large.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise GmailError("Google returned an invalid Gmail response.") from exc
    if not isinstance(value, dict):
        raise GmailError("Google returned an invalid Gmail response.")
    return value


def gmail_begin_authorization(client_id: str, redirect_uri: str,
                              secret_directory: str | None = None,
                              client_secret: str | None = None) -> str:
    """Start read-only Gmail OAuth with PKCE and return its authorization URL.

    Args:
        client_id: Google OAuth desktop client ID.
        redirect_uri: this Nori server's local callback URL.
        secret_directory: optional DPAPI store directory.
        client_secret: optional client secret for Web Application OAuth clients.

    Returns:
        str: JSON result with ``ok`` and ``authorizationUrl``. Never raises.
    """
    try:
        client = str(client_id or "").strip()
        if not client or len(client) > 1000:
            raise GmailError("A Google OAuth client ID is required.")
        _redirect(redirect_uri)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        pending = {"clientId": client, "redirectUri": redirect_uri, "state": state,
                   "verifier": verifier, "createdAt": int(time.time())}
        secret_val = str(client_secret or "").strip()
        store = WindowsDPAPISecretStore(secret_directory)
        if secret_val:
            pending["clientSecret"] = secret_val
            store.set("nori.gmail.client_secret", secret_val)
        store.set("nori.gmail.pending", json.dumps(pending))
        query = urlencode({"client_id": client, "redirect_uri": redirect_uri,
                           "response_type": "code", "scope": GMAIL_READONLY_SCOPE,
                           "state": state, "code_challenge": challenge,
                           "code_challenge_method": "S256", "access_type": "offline",
                           "prompt": "consent", "include_granted_scopes": "false"})
        return json.dumps({"ok": True, "authorizationUrl": f"{_AUTH_URL}?{query}",
                           "scope": GMAIL_READONLY_SCOPE, "error": ""})
    except Exception as exc:
        return json.dumps({"ok": False, "authorizationUrl": "", "error": str(exc)})


def gmail_complete_authorization(callback_url: str,
                                 secret_directory: str | None = None) -> str:
    """Validate an OAuth callback and save encrypted read-only tokens.

    Args:
        callback_url: full callback URL received by FastAPI.
        secret_directory: optional DPAPI store directory.

    Returns:
        str: token-free JSON authorization status. Never raises.
    """
    try:
        store = WindowsDPAPISecretStore(secret_directory)
        pending = _json_secret(store, "nori.gmail.pending")
        expected = _redirect(str(pending.get("redirectUri") or ""))
        actual = urlsplit(callback_url)
        if (actual.scheme, actual.hostname, actual.port, actual.path) != (
                expected.scheme, expected.hostname, expected.port, expected.path):
            raise GmailError("The Gmail callback did not match this Nori server.")
        values = parse_qs(actual.query, keep_blank_values=True)
        states = values.get("state", [])
        if len(states) != 1 or not secrets.compare_digest(states[0], str(pending.get("state") or "")):
            raise GmailError("The Gmail callback state did not match.")
        if values.get("error"):
            raise GmailError("Google authorization was cancelled.")
        codes = values.get("code", [])
        if len(codes) != 1 or not codes[0] or len(codes[0]) > 4096:
            raise GmailError("The Gmail callback did not include a valid code.")
        if time.time() - int(pending.get("createdAt") or 0) > _FLOW_SECONDS:
            raise GmailError("The Gmail authorization expired; connect again.")
        payload = {"client_id": str(pending["clientId"]), "code": codes[0],
                   "code_verifier": str(pending["verifier"]),
                   "redirect_uri": str(pending["redirectUri"]),
                   "grant_type": "authorization_code"}
        client_secret = (
            str(pending.get("clientSecret") or "")
            or str(store.get("nori.gmail.client_secret") or "")
            or os.environ.get("NORI_GMAIL_CLIENT_SECRET", "")
        ).strip()
        if client_secret:
            payload["client_secret"] = client_secret
        token = _http_json(_TOKEN_URL, method="POST", data=payload,
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
        scopes = set(str(token.get("scope") or GMAIL_READONLY_SCOPE).split())
        if scopes != {GMAIL_READONLY_SCOPE}:
            raise GmailError("Google did not grant exactly Gmail read-only access.")
        access = str(token.get("access_token") or "")
        refresh = str(token.get("refresh_token") or "")
        expires = int(token.get("expires_in") or 0)
        if not access or not refresh or not 60 <= expires <= 86400:
            raise GmailError("Google returned incomplete Gmail credentials.")
        record = {"accessToken": access, "refreshToken": refresh,
                  "expiresAt": int(time.time()) + expires,
                  "clientId": payload["client_id"], "scope": GMAIL_READONLY_SCOPE}
        if client_secret:
            record["clientSecret"] = client_secret
            store.set("nori.gmail.client_secret", client_secret)
        store.set("nori.gmail.tokens", json.dumps(record))
        store.delete("nori.gmail.pending")
        return json.dumps({"ok": True, "authorized": True, "scope": GMAIL_READONLY_SCOPE,
                           "error": ""})
    except Exception as exc:
        return json.dumps({"ok": False, "authorized": False, "error": str(exc)})


def gmail_connection_status(secret_directory: str | None = None) -> str:
    """Return token-free Gmail connection status.

    Args:
        secret_directory: optional DPAPI store directory.

    Returns:
        str: JSON ``{ok, authorized, scope, error}``. Never raises.
    """
    try:
        raw = WindowsDPAPISecretStore(secret_directory).get("nori.gmail.tokens")
        if not raw:
            return json.dumps({"ok": True, "authorized": False,
                               "scope": GMAIL_READONLY_SCOPE, "error": ""})
        record = json.loads(raw)
        return json.dumps({"ok": True, "authorized": bool(record.get("refreshToken")),
                           "scope": record.get("scope") or GMAIL_READONLY_SCOPE, "error": ""})
    except Exception as exc:
        return json.dumps({"ok": False, "authorized": False, "error": str(exc)})


def _tokens(store: WindowsDPAPISecretStore) -> dict:
    record = _json_secret(store, "nori.gmail.tokens")
    if int(record.get("expiresAt") or 0) > time.time() + 60:
        return record
    payload = {"client_id": str(record.get("clientId") or ""),
               "refresh_token": str(record.get("refreshToken") or ""),
               "grant_type": "refresh_token"}
    client_secret = (
        str(record.get("clientSecret") or "")
        or str(store.get("nori.gmail.client_secret") or "")
        or os.environ.get("NORI_GMAIL_CLIENT_SECRET", "")
    ).strip()
    if client_secret:
        payload["client_secret"] = client_secret
    token = _http_json(_TOKEN_URL, method="POST", data=payload,
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
    access = str(token.get("access_token") or "")
    expires = int(token.get("expires_in") or 0)
    if not access or not 60 <= expires <= 86400:
        raise GmailError("Google returned an invalid refreshed Gmail credential.")
    record.update(accessToken=access, expiresAt=int(time.time()) + expires)
    store.set("nori.gmail.tokens", json.dumps(record))
    return record


def _gmail_get(store: WindowsDPAPISecretStore, path: str, params: dict) -> dict:
    record = _tokens(store)
    query = urlencode(params, doseq=True)
    return _http_json(f"{_GMAIL_URL}/{path.lstrip('/')}?{query}",
                      headers={"Authorization": f"Bearer {record['accessToken']}"})


def _parse_message(raw: dict, message_id: str) -> JobMessage:
    if str(raw.get("id") or "") != message_id:
        raise GmailError("Google returned mismatched Gmail metadata.")
    headers = {}
    for row in ((raw.get("payload") or {}).get("headers") or [])[:100]:
        if isinstance(row, dict):
            name = str(row.get("name") or "").lower()
            if name in {"subject", "from", "date"} and name not in headers:
                headers[name] = " ".join(str(row.get("value") or "").split())[:2000]
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    snippet = " ".join(str(raw.get("snippet") or "").split())[:2000]
    classification = _classify_job_message(subject, snippet, sender)
    return JobMessage(id=message_id, threadId=str(raw.get("threadId") or "")[:128],
                      timestamp=max(0, int(raw.get("internalDate") or 0)),
                      subject=subject, sender=sender, date=headers.get("date", ""),
                      snippet=snippet, category=classification["category"],
                      confidence=classification["confidence"])


def _save_inbox(messages: list[dict], inbox_path: str) -> dict:
    """Merge Gmail metadata into a bounded local inbox.

    Args:
        messages: normalized message dictionaries.
        inbox_path: local JSON path.

    Returns:
        dict: ``{ok, count, messages, error}``. Never raises.
    """
    try:
        existing = _load_inbox(inbox_path).get("messages", [])
        merged = {str(item.get("id") or ""): item for item in existing if item.get("id")}
        for item in messages:
            if isinstance(item, dict) and item.get("id"):
                merged[str(item["id"])] = item
        rows = sorted(merged.values(), key=lambda item: int(item.get("timestamp") or 0),
                      reverse=True)[:500]
        path = Path(inbox_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"messages": rows}, indent=2), encoding="utf-8")
        os.replace(temporary, path)
        return {"ok": True, "count": len(rows), "messages": rows, "error": ""}
    except Exception as exc:
        return {"ok": False, "count": 0, "messages": [], "error": str(exc)}


def _load_inbox(inbox_path: str) -> dict:
    """Load locally synced message metadata.

    Args:
        inbox_path: local inbox JSON path.

    Returns:
        dict: bounded message list and count. Never raises.
    """
    try:
        value = json.loads(Path(inbox_path).read_text(encoding="utf-8"))
        rows = value.get("messages", []) if isinstance(value, dict) else []
        rows = rows[:500] if isinstance(rows, list) else []
        return {"ok": True, "count": len(rows), "messages": rows, "error": ""}
    except FileNotFoundError:
        return {"ok": True, "count": 0, "messages": [], "error": ""}
    except Exception as exc:
        return {"ok": False, "count": 0, "messages": [], "error": str(exc)}


def gmail_sync_messages(inbox_path: str, max_messages: int = 50,
                        secret_directory: str | None = None) -> str:
    """Fetch and locally persist bounded Gmail metadata and snippets.

    Args:
        inbox_path: local JSON path for metadata.
        max_messages: one to one hundred recent job-related messages.
        secret_directory: optional DPAPI store directory.

    Returns:
        str: token-free JSON with normalized messages. Never raises.
    """
    try:
        limit = max(1, min(int(max_messages), 100))
        store = WindowsDPAPISecretStore(secret_directory)
        query = "newer_than:180d {application interview recruiter hiring offer assessment candidate}"
        listing = _gmail_get(store, "messages", {"maxResults": limit, "q": query})
        identifiers = [str(item.get("id")) for item in listing.get("messages", [])[:limit]
                       if isinstance(item, dict) and item.get("id")]
        messages = []
        for message_id in identifiers:
            raw = _gmail_get(store, f"messages/{message_id}", {
                "format": "metadata",
                "metadataHeaders": ["Subject", "From", "Date"],
            })
            messages.append(asdict(_parse_message(raw, message_id)))
        return json.dumps(_save_inbox(messages, inbox_path))
    except Exception as exc:
        return json.dumps({"ok": False, "count": 0, "messages": [], "error": str(exc)})


def gmail_disconnect(secret_directory: str | None = None) -> str:
    """Delete local Gmail OAuth records without contacting Google.

    Args:
        secret_directory: optional DPAPI store directory.

    Returns:
        str: token-free disconnect result. Never raises.
    """
    try:
        store = WindowsDPAPISecretStore(secret_directory)
        store.delete("nori.gmail.tokens")
        store.delete("nori.gmail.pending")
        return json.dumps({"ok": True, "authorized": False, "error": ""})
    except Exception as exc:
        return json.dumps({"ok": False, "authorized": False, "error": str(exc)})


def gmail_load_inbox(inbox_path: str) -> str:
    """Return locally cached Gmail metadata without making a network request.

    Args:
        inbox_path: local inbox JSON path.

    Returns:
        str: JSON containing a bounded message list. Never raises.
    """
    try:
        return json.dumps(_load_inbox(inbox_path))
    except Exception as exc:
        return json.dumps({"ok": False, "count": 0, "messages": [], "error": str(exc)})


def gmail_classify_message(subject: str, snippet: str = "", sender: str = "") -> str:
    """Classify job-mail text without making a network request.

    Args:
        subject: message subject.
        snippet: short Gmail snippet.
        sender: sender header.

    Returns:
        str: JSON category result. Never raises.
    """
    try:
        return json.dumps(_classify_job_message(subject, snippet, sender))
    except Exception:
        return json.dumps({"category": "other", "confidence": "low", "matches": []})


_OTP_PATTERNS = (
    re.compile(r"\b(?:verification|security|confirmation|passcode|one-time\s+passcode|code|pin)(?:\s+(?:code|passcode|pin))?(?:\s+is|[:=-])?\s*([0-9]{4,8})\b", re.IGNORECASE),
    re.compile(r"\b([0-9]{4,8})\s+is\s+your\s+(?:verification|security|confirmation|one-time)?\s*(?:code|passcode|pin)\b", re.IGNORECASE),
    re.compile(r"\b(?:use|enter)\s+(?:code\s+)?([0-9]{4,8})\b", re.IGNORECASE),
    re.compile(r"\b(?:code|pin|passcode)\s*[:=-]\s*([0-9]{4,8})\b", re.IGNORECASE),
)


def extract_otp_from_text(text: str) -> str:
    """Extract a 4-to-8 digit verification PIN/code from message text.

    Args:
        text: Email subject, snippet, or body text.

    Returns:
        str: Extracted OTP string, or empty string if not found.
    """
    if not text:
        return ""
    clean = " ".join(str(text).split())
    for pat in _OTP_PATTERNS:
        match = pat.search(clean)
        if match:
            return match.group(1)
    return ""


def gmail_extract_recent_otp(domain_hint: str = "", max_age_seconds: int = 300,
                             secret_directory: str | None = None,
                             inbox_path: str | None = None) -> str:
    """Locate and extract a recent verification code from Gmail or local inbox cache.

    Args:
        domain_hint: Optional domain or sender name hint (e.g. 'workday', 'adp').
        max_age_seconds: Max age of the message in seconds (default 300).
        secret_directory: Optional DPAPI store directory.
        inbox_path: Optional path to local inbox cache JSON.

    Returns:
        str: JSON string with {ok, code, source, subject, sender, timestamp, error}. Never raises.
    """
    try:
        now = time.time()
        # 1) Try direct Gmail API fetch if authorized
        try:
            store = WindowsDPAPISecretStore(secret_directory)
            raw_tokens = store.get("nori.gmail.tokens")
            if raw_tokens:
                query = "newer_than:2d (verification OR passcode OR code OR pin OR otp)"
                if domain_hint:
                    query = f"{query} {domain_hint}"
                listing = _gmail_get(store, "messages", {"maxResults": 10, "q": query})
                for item in listing.get("messages", []):
                    if not isinstance(item, dict) or not item.get("id"):
                        continue
                    msg_id = str(item["id"])
                    raw_msg = _gmail_get(store, f"messages/{msg_id}", {
                        "format": "metadata",
                        "metadataHeaders": ["Subject", "From", "Date"],
                    })
                    internal_ms = max(0, int(raw_msg.get("internalDate") or 0))
                    msg_ts = internal_ms / 1000.0 if internal_ms > 1e11 else float(internal_ms)
                    if msg_ts > 0 and (now - msg_ts) > max_age_seconds:
                        continue
                    parsed = _parse_message(raw_msg, msg_id)
                    code = extract_otp_from_text(f"{parsed.subject} {parsed.snippet}")
                    if code:
                        return json.dumps({
                            "ok": True,
                            "code": code,
                            "source": "gmail-api",
                            "subject": parsed.subject,
                            "sender": parsed.sender,
                            "timestamp": internal_ms,
                            "error": "",
                        })
        except Exception:
            pass

        # 2) Try local cached inbox messages
        cache_path = inbox_path
        if not cache_path:
            default_cache = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                "loot", "state", "gmail_inbox.json"
            )
            if os.path.exists(default_cache):
                cache_path = default_cache

        if cache_path and os.path.exists(cache_path):
            data = _load_inbox(cache_path)
            for msg in data.get("messages", []):
                raw_ts = int(msg.get("timestamp") or 0)
                msg_ts = raw_ts / 1000.0 if raw_ts > 1e11 else float(raw_ts)
                if msg_ts > 0 and (now - msg_ts) > max_age_seconds:
                    continue
                subj = msg.get("subject", "")
                snip = msg.get("snippet", "")
                sender = msg.get("sender", "")
                if domain_hint and domain_hint.lower() not in f"{subj} {snip} {sender}".lower():
                    continue
                code = extract_otp_from_text(f"{subj} {snip}")
                if code:
                    return json.dumps({
                        "ok": True,
                        "code": code,
                        "source": "inbox-cache",
                        "subject": subj,
                        "sender": sender,
                        "timestamp": raw_ts,
                        "error": "",
                    })

        return json.dumps({
            "ok": False,
            "code": "",
            "source": "",
            "subject": "",
            "sender": "",
            "timestamp": 0,
            "error": "No recent verification code found.",
        })
    except Exception as exc:
        return json.dumps({
            "ok": False,
            "code": "",
            "source": "",
            "subject": "",
            "sender": "",
            "timestamp": 0,
            "error": str(exc),
        })

