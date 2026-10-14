"""tsenta_feed — job watch / feed ingestion (M6, optional).

Standalone job feed from PUBLIC ATS board APIs only (no Tsenta backend):
- Greenhouse boards API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs
- Lever postings API:   https://api.lever.co/v0/postings/{company}?mode=json
- Plain URL lists (JSON array of URLs, or text file one URL per line)

Feeds are normalized to {id, title, url, location, updated_at, companyName,
companyDomain, logoUrl} and can be persisted as JSON. new_feed_jobs() dedupes against the pipeline job store so a
sweep never re-applies to a URL already tracked.

All public functions return strings or dicts and catch exceptions internally.
"""

from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import urlsplit

try:
    from backend.src.tools.tsenta_pipeline import list_jobs, default_store_path
except ImportError:
    from tsenta_pipeline import list_jobs, default_store_path

_DEFAULT_FEED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", "..", "loot", "state", "feed.json")

_KNOWN_COMPANY_DOMAINS = {
    "mozilla": "mozilla.org",
}


def default_feed_path() -> str:
    """Resolve the default feed store path (loot/state/feed.json)."""
    return os.path.abspath(_DEFAULT_FEED)


def _http_get_json(url: str, timeout: float = 30.0):
    """Fetch and parse JSON from a URL; raises on transport/parse errors."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "tsenta-clone/0.1 (+personal job tool)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def company_identity(company_name: str = "", source: str = "", url: str = "") -> dict:
    """Build stable company branding metadata from known feed identifiers.

    Args:
        company_name: employer display name when supplied by the ATS.
        source: ATS board token or company slug.
        url: posting URL used to recover a missing board slug.

    Returns:
        dict: {companyName, companyDomain, logoUrl}. Empty values are returned
        when no company can be inferred. Never raises.
    """
    try:
        slug = str(source or "").strip().lower()
        if not slug and url:
            parts = urlsplit(str(url))
            host = (parts.hostname or "").lower()
            path_parts = [part for part in parts.path.split("/") if part]
            if path_parts and ("greenhouse.io" in host or "lever.co" in host):
                slug = path_parts[0].lower()

        name = str(company_name or "").strip()
        if not name and slug:
            name = slug.replace("-", " ").replace("_", " ").title()

        domain = _KNOWN_COMPANY_DOMAINS.get(slug, "")
        if not domain and "." in slug and " " not in slug:
            domain = slug
        if not domain and slug:
            domain = f"{slug}.com"

        logo_url = (f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
                    if domain else "")
        return {
            "companyName": name,
            "companyDomain": domain,
            "logoUrl": logo_url,
        }
    except Exception:
        return {"companyName": "", "companyDomain": "", "logoUrl": ""}


def fetch_greenhouse_jobs(board_token: str, limit: int = 100, timeout: float = 30.0) -> list:
    """Fetch open jobs from a Greenhouse public board.

    Args:
        board_token: public board token, e.g. "mozilla".
        limit: max jobs to return (board API caps at 500/request).
        timeout: HTTP timeout seconds.

    Returns:
        list of normalized jobs with company branding; [] on any failure.
    """
    jobs = []
    try:
        data = _http_get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs", timeout)
        for job in (data.get("jobs") or [])[:limit]:
            try:
                identity = company_identity(job.get("company_name") or "",
                                            board_token,
                                            job.get("absolute_url") or "")
                jobs.append({
                    "id": job.get("id"),
                    "title": job.get("title") or "",
                    "url": job.get("absolute_url") or "",
                    "location": (job.get("location") or {}).get("name") or "",
                    "updated_at": job.get("updated_at") or "",
                    **identity,
                })
            except Exception:
                continue
    except Exception:
        return []
    return jobs


def fetch_lever_jobs(company: str, limit: int = 100, timeout: float = 30.0) -> list:
    """Fetch open postings from a Lever public API.

    Args:
        company: Lever company slug, e.g. "mozilla".
        limit: max postings to return.
        timeout: HTTP timeout seconds.

    Returns:
        list of normalized jobs with company branding; [] on any failure.
    """
    jobs = []
    try:
        data = _http_get_json(
            f"https://api.lever.co/v0/postings/{company}?mode=json", timeout)
        for job in (data or [])[:limit]:
            try:
                identity = company_identity(source=company,
                                            url=job.get("hostedUrl") or "")
                jobs.append({
                    "id": job.get("id"),
                    "title": job.get("text") or "",
                    "url": job.get("hostedUrl") or "",
                    "location": (job.get("categories") or {}).get("location") or "",
                    "updated_at": str(job.get("createdAt") or ""),
                    **identity,
                })
            except Exception:
                continue
    except Exception:
        return []
    return jobs


def fetch_feed(source: str, limit: int = 100, timeout: float = 30.0) -> list:
    """Fetch a job feed from a source spec.

    Args:
        source: "greenhouse:<board_token>" | "lever:<company>" | "urls:<path>".
        limit: max jobs to return.
        timeout: HTTP timeout seconds.

    Returns:
        list of normalized jobs with company branding; [] on any failure.
    """
    source = str(source or "")
    try:
        if source.startswith("greenhouse:"):
            return fetch_greenhouse_jobs(source.split(":", 1)[1].strip(), limit, timeout)
        if source.startswith("lever:"):
            return fetch_lever_jobs(source.split(":", 1)[1].strip(), limit, timeout)
        if source.startswith("urls:"):
            return load_urls(source.split(":", 1)[1].strip())
    except Exception:
        pass
    return []


def load_urls(path: str) -> list:
    """Load a list of URLs from a JSON array file or a text file (one per line).

    Args:
        path: path to the URL list.

    Returns:
        list of {id, title, url, location, updated_at} with url set from each
        line; [] on any failure.
    """
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
        try:
            parsed = json.loads(content)
            urls = parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            urls = [line.strip() for line in content.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        for index, url in enumerate(urls):
            if isinstance(url, str) and url.startswith("http"):
                entries.append({"id": f"url_{index}", "title": "",
                                "url": url, "location": "", "updated_at": "",
                                **company_identity(url=url)})
    except Exception:
        return []
    return entries


def jobs_to_urls(jobs: list) -> list:
    """Extract the URLs from a normalized feed list.

    Args:
        jobs: list of {url, ...}.

    Returns:
        list of unique http(s) URLs in order. Never raises.
    """
    urls = []
    try:
        for job in (jobs or []):
            url = str(job.get("url") or "") if isinstance(job, dict) else ""
            if url.startswith("http") and url not in urls:
                urls.append(url)
    except Exception:
        pass
    return urls


def save_feed(feed: list, path: str | None = None) -> str:
    """Persist a normalized feed list as JSON.

    Args:
        feed: list of {id, title, url, location, updated_at}.
        path: output path (default loot/state/feed.json).

    Returns:
        str: JSON of {"ok": True, "count": n} or {"ok": False, "error": ...}.
    """
    path = path or default_feed_path()
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(feed if isinstance(feed, list) else [], handle,
                      ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return json.dumps({"ok": True, "count": len(feed) if isinstance(feed, list) else 0})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "save-failed"})


def load_feed(path: str | None = None) -> list:
    """Load a persisted feed list.

    Args:
        path: input path (default loot/state/feed.json).

    Returns:
        list of feed entries; [] on any failure. Never raises.
    """
    try:
        with open(path or default_feed_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def new_feed_jobs(feed: list, store_path: str | None = None) -> list:
    """Filter a feed down to jobs not already tracked in the pipeline store.

    Args:
        feed: normalized feed list.
        store_path: pipeline store path (default pipeline store).

    Returns:
        list of feed entries whose URL is not in the pipeline store. Never raises.
    """
    try:
        listing = json.loads(list_jobs(store_path))
        known = {str(job.get("url") or "") for job in listing.get("applications", [])}
    except Exception:
        known = set()
    result = []
    for job in (feed or []):
        try:
            if str(job.get("url") or "") not in known:
                result.append(job)
        except Exception:
            continue
    return result
