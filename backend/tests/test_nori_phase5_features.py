"""Tests for Phase 5 features: auto-consent, OTP resolution, and candidate vault login."""
import json
import os
import time
import pytest

from backend.src.tools.tsenta_apply import (
    default_answerer,
    _handle_candidate_account_login,
    _handle_email_otp_gate,
)
from backend.src.tools.tsenta_vault import (
    get_employer_account,
    save_employer_account,
)
from backend.src.tools.tsenta_trace import Trace


def test_consent_default_requires_review():
    field = {
        "field_id": "consent_1",
        "label": "I agree to the privacy policy and consent to data processing",
        "kind": "checkbox",
        "required": True,
        "options": [],
    }
    answer = default_answerer(field, {}, {}, Trace())
    assert answer["source"] == "skip"
    assert "review" in answer["reason"].lower()


def test_consent_auto_accepted_when_configured():
    field = {
        "field_id": "consent_1",
        "label": "I agree to the privacy policy and consent to data processing",
        "kind": "checkbox",
        "required": True,
        "options": [],
    }
    config = {"autoAcceptDisclosures": True}
    answer = default_answerer(field, {}, config, Trace())
    assert answer["source"] == "profile-direct"
    assert answer["value"] is True
    assert answer["display"] == "Yes"


def test_consent_signature_auto_signed_when_configured():
    field = {
        "field_id": "sig_1",
        "label": "Please type your full legal name as your electronic signature",
        "kind": "text",
        "required": True,
        "options": [],
    }
    profile = {
        "personalInformation": {
            "firstName": "Alex",
            "lastName": "Taylor",
        }
    }
    config = {"autoAcceptDisclosures": True}
    answer = default_answerer(field, profile, config, Trace())
    assert answer["source"] == "profile-direct"
    assert answer["value"] == "Alex Taylor"


def test_otp_field_answering_from_gmail(monkeypatch):
    import backend.src.tools.tsenta_apply as ta

    monkeypatch.setattr(
        ta,
        "gmail_extract_recent_otp",
        lambda *args, **kwargs: json.dumps({
            "ok": True,
            "code": "481920",
            "source": "gmail-api",
        })
    )

    field = {
        "field_id": "verification_pin",
        "label": "Enter the verification code sent to your email",
        "kind": "text",
        "required": True,
        "options": [],
    }
    answer = default_answerer(field, {}, {}, Trace())
    assert answer["source"] == "profile-direct"
    assert answer["value"] == "481920"


class MockElement:
    def __init__(self, tag="input", is_vis=True):
        self.tag = tag
        self._visible = is_vis
        self.filled_value = None
        self.clicked = False

    def is_visible(self):
        return self._visible

    def fill(self, val):
        self.filled_value = val

    def click(self, timeout=None):
        self.clicked = True


class MockSurface:
    def __init__(self):
        self.elements = {
            "input[data-automation-id='email'], input[type='email'], input[name='email'], input[id*='email' i], input[name*='user' i], input[id*='user' i]": MockElement(),
            "input[data-automation-id='password'], input[type='password'], input[name='password'], input[id*='password' i]": MockElement(),
            "button[data-automation-id='signInSubmitButton'], button[type='submit'], button:has-text('Sign In'), button:has-text('Log In'), input[type='submit']": MockElement(tag="button"),
        }

    def query_selector(self, selector):
        return self.elements.get(selector)

    def wait_for_timeout(self, ms):
        pass


def test_candidate_account_login(tmp_path, monkeypatch):
    vault_file = str(tmp_path / "accounts.json")
    monkeypatch.setattr("backend.src.tools.tsenta_apply.get_employer_account",
                        lambda ats, dom: {"email": "alex.taylor@gmail.com", "password": "AlexSecure2026!"})
    saved_accounts = {}
    monkeypatch.setattr("backend.src.tools.tsenta_apply.save_employer_account",
                        lambda ats, dom, em, pw: saved_accounts.update({f"{ats}:{dom}": {"email": em, "password": pw}}) or True)

    surface = MockSurface()
    profile = {
        "personalInformation": {
            "email": "alex.taylor@gmail.com"
        }
    }
    url = "https://keybank.myworkdayjobs.com/Careers/job/R-1234"

    success = _handle_candidate_account_login(surface, "workday", url, profile)
    assert success is True
    assert surface.elements["input[data-automation-id='email'], input[type='email'], input[name='email'], input[id*='email' i], input[name*='user' i], input[id*='user' i]"].filled_value == "alex.taylor@gmail.com"
    assert surface.elements["input[data-automation-id='password'], input[type='password'], input[name='password'], input[id*='password' i]"].filled_value == "AlexSecure2026!"
    assert surface.elements["button[data-automation-id='signInSubmitButton'], button[type='submit'], button:has-text('Sign In'), button:has-text('Log In'), input[type='submit']"].clicked is True
