"""M1 unit tests: tsenta_profiles + tsenta_config."""

import json

import pytest

from backend.src.tools.tsenta_config import (
    APPLICATION_DEFAULTS,
    DEFAULT_APPLY_PREFERENCES,
    application_body,
    auto_apply_config,
    config_from_json,
    config_to_json,
    default_config,
    validate_config,
)
from backend.src.tools.tsenta_profiles import (
    EEO_SAFE_DEFAULTS,
    REQUIRED_FIELDS,
    empty_profile,
    experience_bullets,
    profile_from_json,
    profile_get,
    profile_has_resume,
    profile_to_json,
    safe_eeo_profile,
    skills_flat,
    validate_profile,
    work_authorization_summary,
)

# Recovered real-profile leaf shapes (from application_detail_jefferies.json)
JEFFERIES_PERSONAL = {
    "city": "New York", "email": "ravenxtest003366@emalupe.com", "phone": "+15551234567",
    "state": "New York", "address": "New York, NY, USA", "country": "United States",
    "zipCode": "10001", "isOver18": True, "lastName": "Suresh", "firstName": "Drupadh",
    "githubUrl": "https://github.com", "dateOfBirth": "", "linkedinUrl": "https://linkedin.com/in/raven-test",
}
JEFFERIES_AUTH = {
    "visaType": None, "optStatus": None, "needsSponsorship": False,
    "isAuthorizedToWork": True,
    "workAuthorizations": [{"visaType": None, "optStatus": None, "visaStatus": None,
                            "countryCode": "US", "needsSponsorship": False,
                            "authorizationBasis": "citizen", "isAuthorizedToWork": True}],
    "citizenshipCountries": ["US"],
}
JEFFERIES_DEI = {"gender": "", "ethnicity": "", "isVeteran": False, "hasDisability": False,
                 "isTransgender": False, "sexualOrientation": ""}


class TestEmptyProfile:
    def test_all_recovered_sections_present(self):
        profile = empty_profile()
        for section in ["projects", "education", "resumeStyles", "certifications",
                        "customSections", "hiddenSections", "workExperience",
                        "backgroundCheck", "skillCategories", "workPreferences",
                        "hiddenHeaderLinks", "workAuthorization", "personalInformation",
                        "diversityEquityInclusion", "relevantCoursework",
                        "resumeFormat", "hasDocx", "bulletPreservation"]:
            assert section in profile, section

    def test_personal_information_keys(self):
        info = empty_profile()["personalInformation"]
        for key in ["firstName", "lastName", "email", "phone", "address", "city",
                    "state", "zipCode", "country", "linkedinUrl", "githubUrl",
                    "dateOfBirth", "isOver18", "website", "title", "summary"]:
            assert key in info, key

    def test_fresh_copy_per_call(self):
        a, b = empty_profile(), empty_profile()
        a["personalInformation"]["firstName"] = "x"
        assert b["personalInformation"]["firstName"] == ""


class TestFromJson:
    def test_round_trip_preserves_leaf_shapes(self):
        raw = json.dumps({
            "personalInformation": JEFFERIES_PERSONAL,
            "workAuthorization": JEFFERIES_AUTH,
            "diversityEquityInclusion": JEFFERIES_DEI,
            "resumeStyles": {"fitToOnePage": True},
            "resumeFormat": "pdf",
            "hasDocx": True,
        })
        profile = profile_from_json(raw)
        assert profile["personalInformation"]["firstName"] == "Drupadh"
        assert profile["personalInformation"]["isOver18"] is True
        assert profile["workAuthorization"]["citizenshipCountries"] == ["US"]
        assert profile["workAuthorization"]["workAuthorizations"][0]["authorizationBasis"] == "citizen"
        assert profile["resumeFormat"] == "pdf"
        assert profile["hasDocx"] is True

    def test_missing_sections_defaulted(self):
        profile = profile_from_json('{"personalInformation": {"firstName": "A"}}')
        assert profile["education"] == []
        assert profile["diversityEquityInclusion"] == empty_profile()["diversityEquityInclusion"]
        assert profile["resumeStyles"] == {"fitToOnePage": True}

    def test_unknown_top_level_keys_dropped(self):
        profile = profile_from_json('{"personalInformation": {}, "hackerField": 1}')
        assert "hackerField" not in profile

    def test_malformed_inputs(self):
        for text in [None, "", "not json", "[]", "123", "{"]:
            assert profile_from_json(text) == empty_profile()

    def test_array_sections_preserved(self):
        raw = json.dumps({
            "workExperience": [{"id": "x", "role": "Analyst", "company": "PNC",
                                "startDate": "Jul 2025", "endDate": "Present",
                                "isCurrentRole": True, "achievements": [],
                                "responsibilities": ["Did things"], "technologies": ["SIEM"]}],
            "skillCategories": [{"id": "s", "name": "Security", "order": 0,
                                 "skills": ["SIEM", "EDR"]}],
        })
        profile = profile_from_json(raw)
        assert profile["workExperience"][0]["role"] == "Analyst"
        assert profile["skillCategories"][0]["skills"] == ["SIEM", "EDR"]


class TestToJson:
    def test_serialize(self):
        profile = empty_profile()
        profile["personalInformation"]["firstName"] = "Drupadh"
        text = profile_to_json(profile)
        assert json.loads(text)["personalInformation"]["firstName"] == "Drupadh"

    def test_non_dict_safe(self):
        assert profile_to_json(None) == "{}"
        assert profile_to_json("x") == "{}"


class TestProfileGet:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("personalInformation.firstName", "Drupadh"),
            ("personalInformation.isOver18", "true"),
            ("workAuthorization.needsSponsorship", "false"),
            ("workAuthorization.citizenshipCountries", "US"),
            ("workAuthorization.workAuthorizations.0.countryCode", "US"),
            ("workAuthorization.workAuthorizations.5.countryCode", ""),
            ("personalInformation.missingKey", ""),
            ("nonexistent.section.deep", ""),
            ("workAuthorization.citizenshipCountries.0", "US"),
        ],
    )
    def test_dotted_lookup(self, path, expected):
        profile = profile_from_json(json.dumps({
            "personalInformation": JEFFERIES_PERSONAL,
            "workAuthorization": JEFFERIES_AUTH,
        }))
        assert profile_get(profile, path) == expected

    def test_empty_values_return_empty_string(self):
        profile = empty_profile()
        assert profile_get(profile, "personalInformation.firstName") == ""
        assert profile_get(profile, "workAuthorization.isAuthorizedToWork") == ""

    def test_non_dict_profile_safe(self):
        assert profile_get(None, "a.b") == ""
        assert profile_get("x", "a") == ""


class TestCompletenessGate:
    def test_complete_profile_valid(self):
        profile = profile_from_json(json.dumps({
            "personalInformation": JEFFERIES_PERSONAL,
            "workAuthorization": JEFFERIES_AUTH,
            "resumeFormat": "pdf",
        }))
        result = validate_profile(profile)
        assert result["valid"] is True
        assert result["missing"] == []

    def test_missing_fields_report_shape(self):
        result = validate_profile(empty_profile())
        assert result["valid"] is False
        assert isinstance(result["missing"], list)
        for entry in result["missing"]:
            assert set(entry) == {"field", "label", "section"}
        fields = {entry["field"] for entry in result["missing"]}
        assert "firstName" in fields and "email" in fields and "resumeFormat" in fields

    def test_partial_completeness(self):
        profile = profile_from_json(json.dumps({
            "personalInformation": {"firstName": "A", "lastName": "B", "email": "a@b.c",
                                    "phone": "1", "address": "x", "city": "y",
                                    "state": "z", "zipCode": "1", "country": "US"},
        }))
        result = validate_profile(profile)
        fields = {entry["field"] for entry in result["missing"]}
        assert "isAuthorizedToWork" in fields
        assert "firstName" not in fields

    def test_required_fields_matches_recovered_gate(self):
        assert len(REQUIRED_FIELDS) >= 12

    def test_non_dict_profile(self):
        result = validate_profile(None)
        assert result["valid"] is False
        assert len(result["missing"]) == len(REQUIRED_FIELDS)


class TestEEOSafeDefaults:
    def test_safe_eeo_profile(self):
        profile = profile_from_json(json.dumps({"personalInformation": JEFFERIES_PERSONAL}))
        safe = safe_eeo_profile(profile)
        assert safe["diversityEquityInclusion"] == EEO_SAFE_DEFAULTS["diversityEquityInclusion"]
        assert safe["workAuthorization"] == EEO_SAFE_DEFAULTS["workAuthorization"]
        assert safe["personalInformation"]["firstName"] == "Drupadh"  # untouched

    def test_eeo_defaults_shape(self):
        dei = EEO_SAFE_DEFAULTS["diversityEquityInclusion"]
        assert dei["isVeteran"] is False and dei["hasDisability"] is False
        auth = EEO_SAFE_DEFAULTS["workAuthorization"]
        assert auth["isAuthorizedToWork"] is True
        assert auth["needsSponsorship"] is False
        assert auth["workAuthorizations"][0]["authorizationBasis"] == "citizen"


class TestProfileHelpers:
    def test_resume_presence(self):
        assert profile_has_resume(profile_from_json('{"resumeFormat": "pdf"}')) is True
        assert profile_has_resume(empty_profile()) is False

    def test_work_authorization_summary(self):
        profile = profile_from_json(json.dumps({"workAuthorization": JEFFERIES_AUTH}))
        summary = work_authorization_summary(profile)
        assert "authorized:true" in summary
        assert "needsSponsorship:false" in summary
        assert "countries:US" in summary

    def test_work_authorization_summary_unknown(self):
        assert work_authorization_summary(empty_profile()) == "unknown"
        assert work_authorization_summary(None) == "unknown"

    def test_skills_flat(self):
        profile = profile_from_json(json.dumps({
            "skillCategories": [{"name": "A", "skills": ["SIEM", "EDR"]},
                                {"name": "B", "skills": []},
                                {"name": "C", "skills": ["AWS"]}],
        }))
        assert skills_flat(profile) == "SIEM, EDR, AWS"

    def test_skills_flat_empty(self):
        assert skills_flat(empty_profile()) == ""
        assert skills_flat(None) == ""

    def test_experience_bullets(self):
        profile = profile_from_json(json.dumps({
            "workExperience": [
                {"role": "Analyst", "company": "PNC", "startDate": "Jul 2025",
                 "endDate": "Present", "responsibilities": ["Did A", "Did B"],
                 "achievements": []},
            ],
        }))
        text = experience_bullets(profile)
        assert "Analyst at PNC (Jul 2025 - Present)" in text
        assert "Did A | Did B" in text

    def test_experience_bullets_empty(self):
        assert experience_bullets(empty_profile()) == ""
        assert experience_bullets(None) == ""


class TestConfigDefaults:
    def test_defaults_match_recovered_extension_prefs(self):
        config = default_config()
        assert config["optimizationMode"] == "honest"
        assert config["autoApproveResume"] is True
        assert config["autoSubmitApplication"] is False
        assert config["coverLetterMode"] == "honest"
        assert config["autoApproveCoverLetter"] is True
        assert config["reviewBeforeSubmit"] is False

    def test_defaults_match_recovered_application_body(self):
        config = default_config()
        assert config["useOptimizedResume"] is True
        assert config["requiresPreview"] is False


class TestConfigFromJson:
    def test_merge_over_defaults(self):
        config = config_from_json('{"optimizationMode": "aggressive", "reviewBeforeSubmit": true}')
        assert config["optimizationMode"] == "aggressive"
        assert config["reviewBeforeSubmit"] is True
        assert config["autoApproveResume"] is True  # untouched default

    def test_invalid_enum_falls_back(self):
        config = config_from_json('{"optimizationMode": "banana", "coverLetterMode": "creative"}')
        assert config["optimizationMode"] == "honest"
        assert config["coverLetterMode"] == "honest"

    def test_non_bool_flag_falls_back(self):
        config = config_from_json('{"autoApproveResume": "yes"}')
        assert config["autoApproveResume"] is True

    def test_desktop_auto_apply_naming(self):
        config = config_from_json('{"resumeOptimizationMode": "aggressive", "coverLetterOptimizationMode": "honest"}')
        assert config["optimizationMode"] == "aggressive"
        assert config["coverLetterMode"] == "honest"

    def test_unknown_keys_pass_through(self):
        config = config_from_json('{"saveTimestamp": "2026-08-08", "source": "web", "custom": 1}')
        assert config["saveTimestamp"] == "2026-08-08"
        assert config["custom"] == 1

    def test_malformed_inputs(self):
        for text in [None, "", "not json", "[]", "{"]:
            assert config_from_json(text) == default_config()

    def test_to_json_round_trip(self):
        config = config_from_json('{"optimizationMode": "aggressive"}')
        assert json.loads(config_to_json(config))["optimizationMode"] == "aggressive"
        assert config_to_json(None) == "{}"


class TestConfigValidation:
    def test_valid(self):
        result = validate_config(default_config())
        assert result["valid"] is True and result["errors"] == []

    def test_bad_enum(self):
        result = validate_config({"optimizationMode": "banana"})
        assert result["valid"] is False
        assert any("optimizationMode" in e for e in result["errors"])

    def test_bad_flag_type(self):
        result = validate_config({"autoApproveResume": "yes"})
        assert result["valid"] is False
        assert any("autoApproveResume" in e for e in result["errors"])

    def test_non_dict(self):
        result = validate_config(None)
        assert result["valid"] is False


class TestApplicationBody:
    def test_shape_matches_recovered_contract(self):
        body = application_body("https://jobs.lever.co/company/1")
        assert list(body) == ["url", "useOptimizedResume", "requiresPreview",
                              "autoApproveCoverLetter", "coverLetterMode",
                              "optimizationMode", "jobDescription",
                              "resumeProfileId", "atsHint", "companyName"]
        assert body["url"] == "https://jobs.lever.co/company/1"
        assert body["useOptimizedResume"] is True
        assert body["requiresPreview"] is False
        assert body["coverLetterMode"] == "honest"
        assert body["optimizationMode"] == "honest"

    def test_overrides_win(self):
        body = application_body("u", config={"optimizationMode": "aggressive"},
                                atsHint="lever", companyName="Acme",
                                jobDescription="JD", resumeProfileId="p1",
                                coverLetterMode="honest")
        assert body["atsHint"] == "lever"
        assert body["companyName"] == "Acme"
        assert body["jobDescription"] == "JD"
        assert body["resumeProfileId"] == "p1"
        assert body["optimizationMode"] == "aggressive"

    def test_never_raises(self):
        body = application_body(None)
        assert body["url"] is None


class TestAutoApplyConfig:
    def test_desktop_payload_shape(self):
        payload = auto_apply_config()
        assert list(payload) == ["resumeOptimizationMode", "autoApprove",
                                 "reviewBeforeSubmit", "coverLetterOptimizationMode",
                                 "saveTimestamp", "source"]
        assert payload["resumeOptimizationMode"] == "HONEST"
        assert payload["autoApprove"] is True
        assert payload["reviewBeforeSubmit"] is False
        assert payload["source"] == "web"

    def test_respects_config(self):
        payload = auto_apply_config({"optimizationMode": "aggressive",
                                     "reviewBeforeSubmit": True})
        assert payload["resumeOptimizationMode"] == "AGGRESSIVE"
        assert payload["reviewBeforeSubmit"] is True
