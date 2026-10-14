"""Tests for nori_gmail OTP extraction, classification, and store."""
import json
import time
import pytest

from backend.src.tools.nori_gmail import (
    extract_otp_from_text,
    gmail_extract_recent_otp,
    gmail_classify_message,
)


def test_extract_otp_patterns():
    # Various real-world ATS verification email patterns
    cases = [
        ("Your verification code is 849201", "849201"),
        ("Workday security code: 492018", "492018"),
        ("Your one-time passcode is 392182 to continue", "392182"),
        ("Enter 582910 to verify your email address", "582910"),
        ("Your confirmation PIN: 4829", "4829"),
        ("Code: 12345678", "12345678"),
        ("123456 is your verification code for ADP", "123456"),
        ("789012 is your security passcode", "789012"),
    ]
    for text, expected in cases:
        assert extract_otp_from_text(text) == expected, f"Failed for text: {text}"


def test_extract_otp_negative():
    assert extract_otp_from_text("Thank you for your application!") == ""
    assert extract_otp_from_text("Call us at 555-123-4567") == ""
    assert extract_otp_from_text("") == ""


def test_gmail_extract_recent_otp_from_cache(tmp_path):
    inbox_file = tmp_path / "inbox.json"
    now_ms = int(time.time() * 1000)
    inbox_data = {
        "messages": [
            {
                "id": "msg-1",
                "subject": "Workday Verification Code",
                "snippet": "Your verification code is 654321 to access your account.",
                "sender": "no-reply@myworkday.com",
                "timestamp": now_ms - 5000,
            },
            {
                "id": "msg-old",
                "subject": "Old Code",
                "snippet": "Your verification code is 111111",
                "sender": "no-reply@myworkday.com",
                "timestamp": now_ms - 500000,  # > 300s old
            }
        ]
    }
    inbox_file.write_text(json.dumps(inbox_data), encoding="utf-8")

    res = json.loads(gmail_extract_recent_otp(
        domain_hint="workday",
        max_age_seconds=60,
        inbox_path=str(inbox_file)
    ))
    assert res["ok"] is True
    assert res["code"] == "654321"
    assert res["source"] == "inbox-cache"


def test_gmail_extract_recent_otp_not_found(tmp_path):
    inbox_file = tmp_path / "inbox.json"
    inbox_file.write_text(json.dumps({"messages": []}), encoding="utf-8")

    res = json.loads(gmail_extract_recent_otp(
        domain_hint="unknown",
        max_age_seconds=60,
        inbox_path=str(inbox_file)
    ))
    assert res["ok"] is False
    assert res["code"] == ""
