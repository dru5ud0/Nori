"""Shared conservative adapter profile for common form-based ATS hosts.

This module remains as an extension point for ordinary HTML ATS forms that do
not yet have dedicated host behavior. All currently scheduled ATSes have moved
to dedicated adapters.
"""

from __future__ import annotations

GENERIC_EXPERIMENTAL_ATS = ()


def _generic_ats_profile(ats_id: str) -> dict:
    """Return conservative submit and receipt selectors for one ATS.

    Args:
        ats_id: detected ATS identifier.

    Returns:
        dict: walker profile consumed by ``tsenta_apply``. The profile never
        opts into unattended submission and never treats a generic success
        phrase as a verified receipt by itself.
    """
    _ = str(ats_id or "")
    return {
        "submit_selectors": (
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
        ),
        "confirm_selectors": (
            "application submitted",
            "thank you for applying",
            "thank you for your application",
        ),
    }
