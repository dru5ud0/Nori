"""Persistent Nori AI overnight monitoring and Telegram notifications."""

from __future__ import annotations

import json
import hashlib
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone


_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", "..", "loot", "state", "nori-monitor.json")


def default_monitor_path() -> str:
    """Return the absolute default monitor-settings path.

    Returns:
        str: absolute path to loot/state/nori-monitor.json. Never raises.
    """
    return os.path.abspath(_DEFAULT_PATH)


def default_monitor_settings() -> dict:
    """Return safe defaults for the Nori AI overnight monitor.

    Returns:
        dict: disabled monitor settings with a 30-minute interval. Never
        raises and never enables job submission.
    """
    return {
        "enabled": False,
        "query": "Cybersecurity Analyst",
        "location": "Chicago, IL",
        "remoteOnly": False,
        "intervalMinutes": 30,
        "limit": 50,
        "minScore": 25,
        "savedSearchUrl": "",
        "excludedTitles": "",
        "minimumSalary": 0,
        "strictLocation": False,
        "applicationMode": "notify",
        "maxApplicationsPerCycle": 3,
        "dailyApplicationCap": 10,
        "dailyApplicationsUsed": 0,
        "dailyApplicationsRemaining": 10,
        "dailyUsageDate": "",
        "minMatchQuality": "stretch",
        "standingInstructions": "",
        "lanes": [{
            "id": "primary",
            "name": "Primary",
            "enabled": True,
            "query": "Cybersecurity Analyst",
            "location": "Chicago, IL",
            "remoteOnly": False,
            "minScore": 25,
            "minMatchQuality": "stretch",
        }],
        "lastPreparedCount": 0,
        "lastAppliedCount": 0,
        "lastNeedsReviewCount": 0,
        "telegramBotToken": "",
        "telegramChatId": "",
        "telegramUpdateOffset": 0,
        "seenUrls": [],
        "lastRunAt": "",
        "nextRunAt": "",
        "lastError": "",
        "lastFoundCount": 0,
        "lastNewCount": 0,
        "notificationsSent": 0,
        "runHistory": [],
        "recentAlerts": [],
    }


def load_monitor_settings(path: str | None = None, include_secrets: bool = False) -> dict:
    """Load local monitor settings and merge schema defaults.

    Args:
        path: optional JSON file path.
        include_secrets: include the stored Telegram bot token when true.

    Returns:
        dict: schema-complete settings. The public form exposes only
        telegramConfigured and never returns the bot token. Never raises.
    """
    settings = default_monitor_settings()
    saved_has_lanes = False
    try:
        with open(path or default_monitor_path(), "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        if isinstance(saved, dict):
            saved_has_lanes = isinstance(saved.get('lanes'), list)
            settings.update(saved)
    except Exception:
        pass
    settings["telegramBotToken"] = str(
        os.environ.get("NORI_TELEGRAM_BOT_TOKEN") or settings.get("telegramBotToken") or ""
    )
    settings["telegramChatId"] = str(
        os.environ.get("NORI_TELEGRAM_CHAT_ID") or settings.get("telegramChatId") or ""
    )
    if not saved_has_lanes and isinstance(settings.get('lanes'), list) and settings['lanes']:
        # Existing Nori installs predate lanes. Make the first lane an exact
        # view of the established single-search settings instead of silently
        # narrowing the user's query to the schema example.
        settings['lanes'][0].update({
            'query': settings.get('query', ''),
            'location': settings.get('location', ''),
            'remoteOnly': bool(settings.get('remoteOnly')),
            'minScore': int(settings.get('minScore') or 0),
            'minMatchQuality': settings.get('minMatchQuality', 'stretch'),
        })
    if include_secrets:
        return settings
    public = dict(settings)
    public["telegramConfigured"] = bool(
        settings.get("telegramBotToken") and settings.get("telegramChatId")
    )
    public["telegramBotToken"] = ""
    public.pop("seenUrls", None)
    public.pop("telegramUpdateOffset", None)
    return public


def save_monitor_settings(settings: dict, path: str | None = None) -> str:
    """Atomically persist normalized monitor settings.

    Args:
        settings: settings dictionary, including existing runtime status.
        path: optional JSON file path.

    Returns:
        str: JSON {ok, settings} with the bot token removed, or an error.
        Never raises.
    """
    try:
        current = load_monitor_settings(path, include_secrets=True)
        incoming = settings if isinstance(settings, dict) else {}
        for key in default_monitor_settings():
            if key in incoming:
                current[key] = incoming[key]
        current["enabled"] = bool(current.get("enabled"))
        current["remoteOnly"] = bool(current.get("remoteOnly"))
        current['strictLocation'] = bool(current.get('strictLocation'))
        current['savedSearchUrl'] = str(current.get('savedSearchUrl') or '')[:20000]
        current['excludedTitles'] = str(current.get('excludedTitles') or '')[:1000]
        current['minimumSalary'] = max(0, min(int(current.get('minimumSalary') or 0), 1000000))
        current['maxApplicationsPerCycle'] = max(1, min(int(current.get('maxApplicationsPerCycle') or 3), 10))
        current['dailyApplicationCap'] = max(1, min(int(current.get('dailyApplicationCap') or 10), 150))
        current['dailyApplicationsUsed'] = max(0, min(
            int(current.get('dailyApplicationsUsed') or 0), current['dailyApplicationCap']))
        current['dailyApplicationsRemaining'] = max(
            0, current['dailyApplicationCap'] - current['dailyApplicationsUsed'])
        current['dailyUsageDate'] = str(current.get('dailyUsageDate') or '')[:10]
        if current.get('applicationMode') not in ('notify', 'prepare', 'apply'):
            current['applicationMode'] = 'notify'
        if current.get('minMatchQuality') not in ('excellent', 'strong', 'good', 'stretch'):
            current['minMatchQuality'] = 'stretch'
        current['standingInstructions'] = str(current.get('standingInstructions') or '')[:2000].strip()
        raw_lanes = current.get('lanes')
        if not isinstance(raw_lanes, list):
            raw_lanes = []
        lanes = []
        for index, lane in enumerate(raw_lanes[:5]):
            if not isinstance(lane, dict):
                continue
            lane_id = str(lane.get('id') or f'lane-{index + 1}')[:50].strip()
            if not lane_id:
                lane_id = f'lane-{index + 1}'
            quality = str(lane.get('minMatchQuality') or 'stretch').lower()
            if quality not in ('excellent', 'strong', 'good', 'stretch'):
                quality = 'stretch'
            lanes.append({
                'id': lane_id,
                'name': str(lane.get('name') or f'Lane {index + 1}')[:80].strip(),
                'enabled': bool(lane.get('enabled', True)),
                'query': str(lane.get('query') or current.get('query') or '')[:200].strip(),
                'location': str(lane.get('location') or current.get('location') or '')[:100].strip(),
                'remoteOnly': bool(lane.get('remoteOnly', current.get('remoteOnly'))),
                'minScore': max(0, min(int(lane.get('minScore') or current.get('minScore') or 0), 100)),
                'minMatchQuality': quality,
            })
        if not lanes:
            lanes = default_monitor_settings()['lanes']
        current['lanes'] = lanes
        current["query"] = str(current.get("query") or "")[:200].strip()
        current["location"] = str(current.get("location") or "")[:100].strip()
        current["intervalMinutes"] = max(10, min(int(current.get("intervalMinutes") or 30), 1440))
        current["limit"] = max(1, min(int(current.get("limit") or 50), 150))
        current["minScore"] = max(0, min(int(current.get("minScore") or 0), 100))
        current["telegramBotToken"] = str(current.get("telegramBotToken") or "").strip()
        current["telegramChatId"] = str(current.get("telegramChatId") or "").strip()
        if not isinstance(current.get("seenUrls"), list):
            current["seenUrls"] = []
        raw_history = current.get("runHistory")
        if not isinstance(raw_history, list):
            raw_history = []
        history = []
        for entry in raw_history[:50]:
            if not isinstance(entry, dict):
                continue
            history.append({
                "runId": str(entry.get("runId") or "")[:80],
                "startedAt": str(entry.get("startedAt") or "")[:40],
                "finishedAt": str(entry.get("finishedAt") or "")[:40],
                "durationMs": max(0, int(entry.get("durationMs") or 0)),
                "status": str(entry.get("status") or "failed")[:20],
                "mode": str(entry.get("mode") or current.get("applicationMode")
                            or "notify")[:20],
                "laneCount": max(0, min(int(entry.get("laneCount") or 0), 5)),
                "found": max(0, int(entry.get("found") or 0)),
                "new": max(0, int(entry.get("new") or 0)),
                "notified": max(0, int(entry.get("notified") or 0)),
                "prepared": max(0, int(entry.get("prepared") or 0)),
                "applied": max(0, int(entry.get("applied") or 0)),
                "needsReview": max(0, int(entry.get("needsReview") or 0)),
                "error": str(entry.get("error") or "")[:500],
            })
        current["runHistory"] = history
        raw_alerts = current.get("recentAlerts")
        if not isinstance(raw_alerts, list):
            raw_alerts = []
        alerts = []
        seen_alert_urls = set()
        for entry in raw_alerts[:50]:
            normalized = _normalize_monitor_alert(entry)
            url = normalized.get("url")
            if not url or url in seen_alert_urls:
                continue
            seen_alert_urls.add(url)
            alerts.append(normalized)
        current["recentAlerts"] = alerts
        target = path or default_monitor_path()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temp = target + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=False, indent=2)
        os.replace(temp, target)
        return json.dumps({"ok": True,
                           "settings": load_monitor_settings(target, include_secrets=False)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc) or "monitor-save-failed"})


def roll_daily_application_budget(settings: dict, now: datetime | None = None) -> dict:
    """Roll the monitor's shared daily application budget at UTC midnight.

    Args:
        settings: mutable monitor settings dictionary.
        now: optional timezone-aware timestamp used by tests and callers.

    Returns:
        dict: the same settings dictionary with a current usage date, a
        clamped cap, and a reset usage counter when the day changed. Never
        raises.
    """
    try:
        if not isinstance(settings, dict):
            return {}
        current = now if isinstance(now, datetime) else datetime.now(timezone.utc)
        day = current.astimezone(timezone.utc).date().isoformat()
        cap = max(1, min(int(settings.get('dailyApplicationCap') or 10), 150))
        usage_date = str(settings.get('dailyUsageDate') or '')[:10]
        used = max(0, min(int(settings.get('dailyApplicationsUsed') or 0), cap))
        if usage_date != day:
            used = 0
        settings['dailyApplicationCap'] = cap
        settings['dailyApplicationsUsed'] = used
        settings['dailyUsageDate'] = day
        settings['dailyApplicationsRemaining'] = max(0, cap - used)
        return settings
    except Exception:
        return settings if isinstance(settings, dict) else {}


def append_monitor_run(settings: dict, result: dict,
                       started_at: datetime | None = None,
                       finished_at: datetime | None = None,
                       status: str = "") -> dict:
    """Prepend one bounded automation-cycle audit record.

    Args:
        settings: mutable monitor settings dictionary.
        result: cycle result containing counts and an optional error.
        started_at: optional timezone-aware cycle start.
        finished_at: optional timezone-aware cycle finish.
        status: optional explicit completed, partial, blocked, or failed state.

    Returns:
        dict: the same settings dictionary with at most 50 normalized history
        rows, newest first. Telegram credentials and job/profile data are never
        recorded. Never raises.
    """
    try:
        if not isinstance(settings, dict):
            return {}
        payload = result if isinstance(result, dict) else {}
        finished = (finished_at if isinstance(finished_at, datetime)
                    else datetime.now(timezone.utc))
        started = started_at if isinstance(started_at, datetime) else finished
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        error = str(payload.get("error") or "")[:500]
        resolved_status = str(status or "").lower()
        if resolved_status not in ("completed", "partial", "blocked", "failed"):
            resolved_status = ("failed" if not payload.get("ok") else
                               "partial" if error else "completed")
        active_lanes = [lane for lane in (settings.get("lanes") or [])
                        if isinstance(lane, dict) and lane.get("enabled", True)
                        and str(lane.get("query") or "").strip()]
        started_text = started.astimezone(timezone.utc).isoformat()
        finished_text = finished.astimezone(timezone.utc).isoformat()
        entry = {
            "runId": hashlib.sha256(
                f"{started_text}:{finished_text}".encode("utf-8")
            ).hexdigest()[:16],
            "startedAt": started_text,
            "finishedAt": finished_text,
            "durationMs": max(0, int((finished - started).total_seconds() * 1000)),
            "status": resolved_status,
            "mode": str(settings.get("applicationMode") or "notify")[:20],
            "laneCount": len(active_lanes),
            "found": max(0, int(payload.get("count") or 0)),
            "new": max(0, int(payload.get("newCount") or 0)),
            "notified": max(0, int(payload.get("notified") or 0)),
            "prepared": max(0, int(payload.get("prepared") or 0)),
            "applied": max(0, int(payload.get("applied") or 0)),
            "needsReview": max(0, int(payload.get("needsReview") or 0)),
            "error": error,
        }
        old = settings.get("runHistory")
        settings["runHistory"] = [entry] + [item for item in (
            old if isinstance(old, list) else []) if isinstance(item, dict)][:49]
        return settings
    except Exception:
        return settings if isinstance(settings, dict) else {}


def _normalize_monitor_alert(value: dict, found_at: str = "") -> dict:
    """Return one bounded, secret-free local monitor alert."""
    try:
        item = value if isinstance(value, dict) else {}
        url = str(item.get("url") or "").strip().rstrip("/")[:20000]
        score = max(0, min(int(item.get("matchScore") or 0), 100))
        return {
            "id": str(item.get("id") or hashlib.sha256(
                url.encode("utf-8")).hexdigest()[:16])[:80],
            "url": url,
            "title": str(item.get("title") or "")[:300],
            "companyName": str(item.get("companyName") or item.get("company") or "")[:300],
            "location": str(item.get("location") or "")[:300],
            "matchScore": score,
            "matchQuality": str(item.get("matchQuality") or "")[:40],
            "foundAt": str(item.get("foundAt") or found_at or "")[:40],
            "telegramNotified": bool(item.get("telegramNotified")),
        }
    except Exception:
        return {"id": "", "url": "", "title": "", "companyName": "",
                "location": "", "matchScore": 0, "matchQuality": "",
                "foundAt": "", "telegramNotified": False}


def append_monitor_alerts(settings: dict, jobs: list,
                          found_at: datetime | None = None,
                          notified_urls: set | None = None) -> dict:
    """Persist newly discovered matches in Nori's bounded local alert inbox.

    Args:
        settings: mutable monitor settings dictionary.
        jobs: ranked HiringCafe jobs discovered during the current cycle.
        found_at: optional timezone-aware discovery time.
        notified_urls: normalized URLs successfully sent through Telegram.

    Returns:
        dict: the same settings dictionary with at most 50 unique alerts,
        newest first. Candidate/profile data and Telegram secrets are never
        stored. Never raises.
    """
    try:
        if not isinstance(settings, dict):
            return {}
        moment = found_at if isinstance(found_at, datetime) else datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        timestamp = moment.astimezone(timezone.utc).isoformat()
        notified = {str(url or "").strip().rstrip("/")
                    for url in (notified_urls or set())}
        old_by_url = {}
        for item in settings.get("recentAlerts") or []:
            normalized = _normalize_monitor_alert(item)
            if normalized.get("url"):
                old_by_url[normalized["url"]] = normalized
        additions = []
        added_urls = set()
        for job in jobs if isinstance(jobs, list) else []:
            normalized = _normalize_monitor_alert(job, timestamp)
            url = normalized.get("url")
            if not url or url in added_urls:
                continue
            previous = old_by_url.get(url) or {}
            normalized["foundAt"] = previous.get("foundAt") or timestamp
            normalized["telegramNotified"] = bool(
                previous.get("telegramNotified") or url in notified)
            additions.append(normalized)
            added_urls.add(url)
        remaining = [item for url, item in old_by_url.items() if url not in added_urls]
        settings["recentAlerts"] = (additions + remaining)[:50]
        return settings
    except Exception:
        return settings if isinstance(settings, dict) else {}


def monitor_preview(settings: dict, jobs: list, tracked_urls: set | None = None,
                    days: int = 7) -> dict:
    """Build an honest budget and candidate preview without running a search.

    Args:
        settings: current normalized monitor settings.
        jobs: already saved/ranked feed items; no network call is made.
        tracked_urls: normalized URLs already present in the application store.
        days: preview horizon, clamped to one through thirty days.

    Returns:
        dict: current eligible candidate counts, recent measured averages, and
        maximum preparation budget. Projections are labeled estimates and are
        zero when no completed history exists. Never raises.
    """
    try:
        settings = settings if isinstance(settings, dict) else {}
        horizon = max(1, min(int(days or 7), 30))
        tracked = {str(value or "").rstrip("/") for value in (tracked_urls or set())}
        lanes = [lane for lane in (settings.get("lanes") or [])
                 if isinstance(lane, dict) and lane.get("enabled", True)
                 and str(lane.get("query") or settings.get("query") or "").strip()]
        thresholds = [lane_match_threshold(lane, settings.get("minScore", 0))
                      for lane in lanes]
        threshold = min(thresholds) if thresholds else max(
            int(settings.get("minScore") or 0),
            match_quality_threshold(settings.get("minMatchQuality")))
        candidates = []
        seen = set()
        for job in jobs if isinstance(jobs, list) else []:
            if not isinstance(job, dict):
                continue
            url = str(job.get("url") or "").rstrip("/")
            if (not url or url in seen or url in tracked
                    or int(job.get("matchScore") or 0) < threshold):
                continue
            seen.add(url)
            candidates.append(job)
        cap = max(1, min(int(settings.get("dailyApplicationCap") or 10), 150))
        interval = max(10, min(int(settings.get("intervalMinutes") or 30), 1440))
        cycles_per_day = max(1, 1440 // interval)
        history = [entry for entry in (settings.get("runHistory") or [])
                   if isinstance(entry, dict) and entry.get("status") in (
                       "completed", "partial")][:20]
        average_new = (round(sum(int(entry.get("new") or 0) for entry in history)
                             / len(history), 1) if history else 0)
        projected_new = round(average_new * cycles_per_day * horizon)
        maximum = cap * horizon
        return {
            "ok": True,
            "days": horizon,
            "activeLanes": len(lanes),
            "minimumScore": threshold,
            "currentEligibleCandidates": len(candidates),
            "dailyApplicationCap": cap,
            "maximumPreparations": maximum,
            "cyclesPerDay": cycles_per_day,
            "recentRunsMeasured": len(history),
            "averageNewPerRun": average_new,
            "projectedNewJobs": projected_new,
            "projectedPreparations": min(projected_new, maximum),
            "estimateAvailable": bool(history),
        }
    except Exception as exc:
        return {"ok": False, "days": 7, "error": str(exc) or "preview-failed"}


def match_quality_threshold(value: str) -> int:
    """Map a human match-quality bar to the minimum profile score.

    Args:
        value: excellent, strong, good, or stretch.

    Returns:
        int: minimum score used by overnight preparation. Never raises.
    """
    try:
        return {"excellent": 75, "strong": 60, "good": 45,
                "stretch": 25}.get(str(value or "").lower(), 25)
    except Exception:
        return 25


def lane_match_threshold(lane: dict, fallback: int = 25) -> int:
    """Return the effective score threshold for one automation lane."""
    try:
        lane = lane if isinstance(lane, dict) else {}
        return max(int(lane.get('minScore') or fallback),
                   match_quality_threshold(lane.get('minMatchQuality')))
    except Exception:
        return max(int(fallback or 0), 25)


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        str: timezone-aware ISO timestamp. Never raises.
    """
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return ""


def keep_system_awake(enabled: bool) -> str:
    """Prevent Windows system sleep while overnight monitoring is enabled.

    Args:
        enabled: true to keep the system awake while allowing the display to
            turn off; false to restore normal power behavior.

    Returns:
        str: JSON {ok, enabled}. Non-Windows systems return ok without making
        a power-policy change. Never raises.
    """
    try:
        if os.name == "nt":
            import ctypes
            es_continuous = 0x80000000
            es_system_required = 0x00000001
            flags = es_continuous | (es_system_required if enabled else 0)
            if not ctypes.windll.kernel32.SetThreadExecutionState(flags):
                return json.dumps({"ok": False, "enabled": bool(enabled),
                                   "error": "windows-awake-request-failed"})
        return json.dumps({"ok": True, "enabled": bool(enabled), "error": ""})
    except Exception as exc:
        return json.dumps({"ok": False, "enabled": bool(enabled),
                           "error": str(exc) or "awake-request-failed"})


def send_telegram_jobs(bot_token: str, chat_id: str, jobs: list,
                       dashboard_url: str = "http://127.0.0.1:8000/jobs") -> str:
    """Send new job alerts through the Telegram Bot API.

    Args:
        bot_token: Telegram bot token from BotFather.
        chat_id: destination chat id.
        jobs: ranked normalized job dictionaries.
        dashboard_url: local Nori AI Browse-jobs address.

    Returns:
        str: JSON {ok, sent, sentUrls, error}. Each alert includes a remote
        Prepare application callback and the employer posting. Never raises.
    """
    token = str(bot_token or "").strip()
    destination = str(chat_id or "").strip()
    if not token or not destination:
        return json.dumps({"ok": False, "sent": 0, "error": "telegram-not-configured"})
    sent = 0
    sent_urls = []
    try:
        endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
        for job in (jobs or [])[:8]:
            if not isinstance(job, dict) or not str(job.get("url") or "").startswith("https://"):
                continue
            title = str(job.get("title") or "New role")
            company = str(job.get("companyName") or "Unknown company")
            location = str(job.get("location") or "Location not listed")
            score = int(job.get("matchScore") or 0)
            keyboard = {"inline_keyboard": [[
                {"text": "Prepare application", "callback_data": 'nori:prepare:' + _job_key(job['url'])},
                {"text": "Open posting", "url": job["url"]},
            ]]}
            payload = urllib.parse.urlencode({
                "chat_id": destination,
                "text": f"Nori AI found a {score}% match\n{title}\n{company} · {location}",
                "disable_web_page_preview": "true",
                "reply_markup": json.dumps(keyboard, separators=(",", ":")),
            }).encode("utf-8")
            request = urllib.request.Request(endpoint, data=payload, method="POST")
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8", errors="replace"))
            if result.get("ok"):
                sent += 1
                sent_urls.append(job['url'])
            else:
                raise RuntimeError(result.get('description') or 'telegram-send-rejected')
        return json.dumps({"ok": True, "sent": sent, "sentUrls": sent_urls, "error": ""})
    except Exception as exc:
        return json.dumps({"ok": False, "sent": sent, "sentUrls": sent_urls,
                           "error": str(exc).replace(token, '[redacted]') or "telegram-send-failed"})


def _job_key(url: str) -> str:
    return hashlib.sha256(str(url).rstrip('/').encode()).hexdigest()[:24]


def _telegram_request(token: str, method: str, payload: dict) -> dict:
    """Make a bounded Bot API call; never expose its credential-bearing URL."""
    try:
        request = urllib.request.Request(f'https://api.telegram.org/bot{token}/{method}',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        return {'ok': False, 'description': str(exc).replace(token, '[redacted]')}


def _telegram_commands(settings: dict) -> dict:
    """Poll callbacks from the configured private chat only; ignore other users."""
    offset = int(settings.get('telegramUpdateOffset') or 0)
    result = _telegram_request(settings['telegramBotToken'], 'getUpdates',
        {'offset': offset, 'timeout': 5, 'limit': 20, 'allowed_updates': ['callback_query']})
    commands = []
    if not result.get('ok'):
        return {'commands': [], 'offset': offset, 'error': result.get('description', 'telegram-poll-failed')}
    for update in result.get('result') or []:
        offset = max(offset, int(update.get('update_id') or 0) + 1)
        callback = update.get('callback_query') or {}
        chat = (callback.get('message') or {}).get('chat') or {}
        allowed = (chat.get('type') == 'private'
                   and str(chat.get('id')) == str(settings.get('telegramChatId'))
                   and str((callback.get('from') or {}).get('id')) == str(chat.get('id')))
        if allowed and str(callback.get('data') or '').startswith('nori:'):
            commands.append({**callback, '_nextOffset': int(update.get('update_id') or 0) + 1})
    return {'commands': commands, 'offset': offset, 'error': ''}


def _telegram_status(settings: dict, message: str, application_id: str = '') -> dict:
    """Send status; only a ready review draft receives an explicit Submit button."""
    payload = {'chat_id': settings['telegramChatId'], 'text': str(message)[:4000]}
    if application_id:
        payload['reply_markup'] = {'inline_keyboard': [[{
            'text': 'Submit this application', 'callback_data': 'nori:apply:' + application_id}]]}
    return _telegram_request(settings['telegramBotToken'], 'sendMessage', payload)
