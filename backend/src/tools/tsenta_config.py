"""tsenta_config — application/automation configuration (M1).

Port of the recovered Tsenta configuration surfaces:
- extension apply prefs (extension/background.js, createApplication defaults):
  { optimizationMode, autoApproveResume, autoSubmitApplication, coverLetterMode,
    autoApproveCoverLetter, reviewBeforeSubmit }
- desktop auto-apply config (internal_api_map.md): { resumeOptimizationMode,
  autoApprove, reviewBeforeSubmit, coverLetterOptimizationMode, saveTimestamp,
  source }
- POST /applications body defaults: { url, useOptimizedResume, requiresPreview,
  coverLetterMode, optimizationMode, jobDescription, resumeProfileId, atsHint,
  companyName }

Public functions return strings or dicts and catch exceptions internally.
"""

from __future__ import annotations

import json

# Recovered mode values. "aggressive" is documented for resume rewrite
# (ATS_SCRAPING_ENGINE.md §Resume Optimization); "honest" is the only observed
# cover-letter mode.
OPTIMIZATION_MODES = ("honest", "aggressive")
COVER_LETTER_MODES = ("honest", "generated")

# Extension apply-preference defaults (recovered verbatim).
DEFAULT_APPLY_PREFERENCES = {
    "optimizationMode": "honest",
    "autoApproveResume": True,
    "autoSubmitApplication": False,
    "coverLetterMode": "honest",
    "autoApproveCoverLetter": True,
    "reviewBeforeSubmit": False,
    "autoAcceptDisclosures": False,
}

# POST /applications body defaults (recovered verbatim from createApplication).
APPLICATION_DEFAULTS = {
    "useOptimizedResume": True,
    "requiresPreview": False,
    "coverLetterMode": "honest",
    "optimizationMode": "honest",
    "autoAcceptDisclosures": False,
}

_BOOL_FLAGS = ("autoApproveResume", "autoSubmitApplication", "autoApproveCoverLetter",
               "reviewBeforeSubmit", "useOptimizedResume", "requiresPreview",
               "autoAcceptDisclosures")


def default_config() -> dict:
    """Return the recovered default apply configuration.

    Returns:
        dict: extension defaults + application body defaults combined.
        Never raises.
    """
    config = dict(DEFAULT_APPLY_PREFERENCES)
    config.update(APPLICATION_DEFAULTS)
    return config


def config_from_json(text: str) -> dict:
    """Parse a JSON config string, merged over defaults with validation.

    Args:
        text: JSON string with any subset of config keys (e.g. from
            GET /users/{uid}/apply-preferences or auto-apply-config).

    Returns:
        dict: defaults merged with parsed values; invalid enum values and
        non-boolean flags fall back to defaults. Malformed input yields
        defaults. Never raises.
    """
    config = default_config()
    if not text:
        return config
    try:
        data = json.loads(text)
    except Exception:
        return config
    if not isinstance(data, dict):
        return config
    for key, value in data.items():
        if key in _BOOL_FLAGS:
            if isinstance(value, bool):
                config[key] = value
        elif key == "optimizationMode":
            if value in OPTIMIZATION_MODES:
                config[key] = value
        elif key == "coverLetterMode":
            if value in COVER_LETTER_MODES:
                config[key] = value
        elif key in ("resumeOptimizationMode", "coverLetterOptimizationMode"):
            # Desktop auto-apply-config naming -> normalized to our keys.
            if value in OPTIMIZATION_MODES:
                config["optimizationMode" if key.startswith("resume") else "coverLetterMode"] = value
        elif key in ("autoApprove", "autoApproveResume", "autoApproveCoverLetter",
                     "autoSubmitApplication", "reviewBeforeSubmit", "requiresPreview",
                     "useOptimizedResume", "saveTimestamp", "source"):
            config[key] = value
        else:
            # Unknown keys pass through untouched (forward compatibility).
            config[key] = value
    return config


def config_to_json(config: dict) -> str:
    """Serialize a config dict to compact JSON.

    Args:
        config: config dict.

    Returns:
        str: compact JSON; "{}" on failure. Never raises.
    """
    if not isinstance(config, dict):
        return "{}"
    try:
        return json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def validate_config(config: dict) -> dict:
    """Validate a config dict against recovered constraints.

    Args:
        config: config dict.

    Returns:
        dict: {"valid": bool, "errors": [str, ...]} where errors describe each
        offending key. Never raises.
    """
    errors = []
    if not isinstance(config, dict):
        return {"valid": False, "errors": ["config is not an object"]}
    mode = config.get("optimizationMode")
    if mode is not None and mode not in OPTIMIZATION_MODES:
        errors.append(f"optimizationMode '{mode}' not in {sorted(OPTIMIZATION_MODES)}")
    cl_mode = config.get("coverLetterMode")
    if cl_mode is not None and cl_mode not in COVER_LETTER_MODES:
        errors.append(f"coverLetterMode '{cl_mode}' not in {sorted(COVER_LETTER_MODES)}")
    for flag in _BOOL_FLAGS:
        value = config.get(flag)
        if value is not None and not isinstance(value, bool):
            errors.append(f"{flag} must be a boolean, got {type(value).__name__}")
    return {"valid": not errors, "errors": errors}


def application_body(url: str, config: dict = None, **overrides) -> dict:
    """Build a POST /applications body from config + overrides.

    Args:
        url: job/apply URL (required).
        config: config dict (defaults when omitted).
        **overrides: explicit keys that win (atsHint, companyName, jobDescription,
            resumeProfileId, coverLetterMode, optimizationMode, useOptimizedResume,
            requiresPreview, autoApproveCoverLetter).

    Returns:
        dict: the create-application body in the recovered shape:
        {url, useOptimizedResume, requiresPreview, autoApproveCoverLetter,
         coverLetterMode, optimizationMode, jobDescription, resumeProfileId,
         atsHint, companyName}. Never raises.
    """
    merged = default_config()
    if isinstance(config, dict):
        merged.update({k: v for k, v in config.items() if k in merged})
    merged.update(overrides)
    body = {
        "url": url,
        "useOptimizedResume": bool(merged.get("useOptimizedResume")),
        "requiresPreview": bool(merged.get("requiresPreview")),
        "autoApproveCoverLetter": bool(merged.get("autoApproveCoverLetter")),
        "coverLetterMode": merged.get("coverLetterMode") or "honest",
        "optimizationMode": merged.get("optimizationMode") or "honest",
        "jobDescription": merged.get("jobDescription") or "",
        "resumeProfileId": merged.get("resumeProfileId") or "",
        "atsHint": merged.get("atsHint") or "",
        "companyName": merged.get("companyName") or "",
    }
    return body


def auto_apply_config(config: dict = None) -> dict:
    """Render the desktop-style auto-apply-config payload (recovered shape).

    Args:
        config: config dict (defaults when omitted).

    Returns:
        dict: {resumeOptimizationMode, autoApprove, reviewBeforeSubmit,
        coverLetterOptimizationMode, saveTimestamp, source} — the
        GET /users/{uid}/auto-apply-config surface. Never raises.
    """
    merged = default_config()
    if isinstance(config, dict):
        merged.update({k: v for k, v in config.items() if k in merged})
    return {
        "resumeOptimizationMode": (merged.get("optimizationMode") or "honest").upper(),
        "autoApprove": bool(merged.get("autoApproveResume")),
        "reviewBeforeSubmit": bool(merged.get("reviewBeforeSubmit")),
        "coverLetterOptimizationMode": (merged.get("coverLetterMode") or "honest").upper(),
        "saveTimestamp": merged.get("saveTimestamp") or "",
        "source": merged.get("source") or "web",
    }
