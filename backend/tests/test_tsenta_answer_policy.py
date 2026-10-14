"""Unit tests for tsenta_answer_policy (India and multi-country safety rules)."""

from backend.src.tools.tsenta_answer_policy import (
    IN_STATE_NAMES,
    US_STATE_NAMES,
    country_option_aliases,
    declared_eligibility,
    question_country,
    state_option_aliases,
)


def test_in_state_names_aliases():
    """Verify Indian state abbreviations and full names generate correct aliases."""
    # Karnataka (KA)
    aliases_ka = state_option_aliases("KA")
    assert "karnataka" in aliases_ka
    assert "ka" in aliases_ka

    aliases_karnataka = state_option_aliases("Karnataka")
    assert "karnataka" in aliases_karnataka
    assert "ka" in aliases_karnataka

    # Maharashtra (MH)
    aliases_mh = state_option_aliases("MH")
    assert "maharashtra" in aliases_mh
    assert "mh" in aliases_mh

    # Telangana (TS)
    aliases_ts = state_option_aliases("TS")
    assert "telangana" in aliases_ts
    assert "ts" in aliases_ts


def test_country_calling_codes_india():
    """Verify Indian phone calling code aliases (+91, India)."""
    aliases = country_option_aliases("India")
    assert "india" in aliases
    assert "+91" in aliases
    assert "india (+91)" in aliases


def test_question_country_detection():
    """Verify country detection for explicit countries and Indian tech hub authorization."""
    assert question_country("Are you legally authorized to work in India?") == "IN"
    assert question_country("Will you require sponsorship to work in India?") == "IN"
    assert question_country("Are you authorized to work in the United States?") == "US"
    # Tech hub mentioned in authorization context
    assert question_country("Are you legally authorized to work in Bengaluru?") == "IN"
    assert question_country("Do you have legal work authorization for our Hyderabad office?") == "IN"


def test_declared_eligibility_multi_country_consensus():
    """Verify that multi-country records consensus resolves un-targeted questions."""
    profile = {
        "workAuthorization": {
            "isAuthorizedToWork": True,
            "needsSponsorship": False,
            "workAuthorizations": [
                {
                    "countryCode": "US",
                    "isAuthorizedToWork": True,
                    "needsSponsorship": False,
                },
                {
                    "countryCode": "IN",
                    "isAuthorizedToWork": True,
                    "needsSponsorship": False,
                },
            ],
            "citizenshipCountries": ["IN"],
        },
        "personalInformation": {
            "country": "India",
        },
    }

    # Explicit question for India
    assert declared_eligibility(profile, "Are you authorized to work in India?", "isAuthorizedToWork") is True
    assert declared_eligibility(profile, "Do you require sponsorship in India?", "needsSponsorship") is False

    # Explicit question for US
    assert declared_eligibility(profile, "Are you authorized to work in the United States?", "isAuthorizedToWork") is True
    assert declared_eligibility(profile, "Do you require sponsorship in the US?", "needsSponsorship") is False

    # Un-targeted question ("in this position / country") with both records agreeing
    assert declared_eligibility(profile, "Are you legally authorized to work?", "isAuthorizedToWork") is True
    assert declared_eligibility(profile, "Will you now or in the future require sponsorship?", "needsSponsorship") is False
