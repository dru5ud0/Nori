"""Tests for the local recruiter/vendor CRM."""

from __future__ import annotations

import json

from backend.src.tools.tsenta_networking import (
    network_delete_contact, network_draft_outreach,
    network_list_contacts,
    network_score,
    network_update_contact,
    network_upsert_contact,
)


def test_detects_high_value_stem_opt_chicago_signals():
    result = json.loads(network_score({
        "name": "Recruiter Example",
        "location": "Elk Grove Village, Illinois",
        "about": "Direct clients including UAL. OPT EAD candidates. W2 and C2C.",
        "connectionDegree": "1st",
        "email": "recruiter@example.test",
        "evidence": [{"text": "E-Verify employer willing to complete Form I-983 for STEM OPT"}],
    }))
    assert result["ok"] is True
    assert result["signals"]["chicagoRelevant"] is True
    assert result["signals"]["unitedAirlines"] is True
    assert result["signals"]["stemOpt"] is True
    assert result["signals"]["i983"] is True
    assert result["score"] >= 80


def test_upsert_deduplicates_and_filters_chicago(tmp_path):
    store = str(tmp_path / "networking.json")
    first = json.loads(network_upsert_contact({
        "name": "Samar Singh",
        "linkedinUrl": "https://www.linkedin.com/in/samar-singh-017298158/",
        "headline": "Director of Operations at Pride RPO",
        "location": "Elk Grove Village, Illinois",
        "evidence": [{"sourceUrl": "https://www.linkedin.com/in/samar-singh-017298158/", "text": "Recruitment leader"}],
    }, store))
    second = json.loads(network_upsert_contact({
        "name": "Samar Singh",
        "linkedinUrl": "https://www.linkedin.com/in/samar-singh-017298158",
        "notes": "Referred an account contact",
    }, store))
    assert first["created"] is True
    assert second["created"] is False
    assert first["contact"]["id"] == second["contact"]["id"]

    listing = json.loads(network_list_contacts(store, chicago_only=True))
    assert listing["count"] == 1
    assert listing["contacts"][0]["signals"]["chicagoRelevant"] is True


def test_rejects_non_profile_linkedin_urls(tmp_path):
    store = str(tmp_path / "networking.json")
    result = json.loads(network_upsert_contact({
        "name": "Ad Options",
        "linkedinUrl": "https://www.linkedin.com/notifications",
    }, store))
    assert result == {"ok": False, "error": "invalid-linkedin-profile-url"}


def test_deletes_invalid_contact(tmp_path):
    store = str(tmp_path / "networking.json")
    created = json.loads(network_upsert_contact({
        "name": "Delete Me",
        "linkedinUrl": "https://linkedin.com/in/delete-me",
    }, store))
    deleted = json.loads(network_delete_contact(created["contact"]["id"], store))
    assert deleted["ok"] is True
    assert json.loads(network_list_contacts(store))["count"] == 0


def test_update_risks_and_review_only_draft(tmp_path):
    store = str(tmp_path / "networking.json")
    created = json.loads(network_upsert_contact({
        "name": "Shagufta Khan",
        "linkedinUrl": "https://www.linkedin.com/in/shagufta-khan-01436073/",
        "company": "Pyramid Consulting",
        "about": "Direct clients, OPT EAD, W2 and C2C, UAL.",
    }, store))
    contact_id = created["contact"]["id"]

    updated = json.loads(network_update_contact(contact_id, {
        "status": "vetted",
        "riskFlags": ["duplicate-rtr"],
    }, store))
    assert updated["contact"]["status"] == "vetted"
    assert "duplicate-rtr" in updated["contact"]["riskFlags"]

    drafted = json.loads(network_draft_outreach(contact_id, store))
    assert drafted["ok"] is True
    assert "STEM OPT" in drafted["draft"]
    assert "Form I-983" in drafted["draft"]
    assert "role-specific RTR" in drafted["draft"]
