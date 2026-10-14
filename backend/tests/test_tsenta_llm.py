"""M4 tests: tsenta_llm.py — LLM answer-sourcing engine.

Covers: config resolution from env, chat_completion transport (success and
every failure mode), answerer routing (profile-direct / llm / skip / fallback
matching the recovered trace semantics), option matching, and integration with
answer_fields. No network calls: the transport is injected or monkeypatched.
"""

import json
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "tools"))

from tsenta_llm import (  # noqa: E402
    chat_completion,
    llm_config,
    make_llm_answerer,
    _match_option,
    _profile_digest,
)
from tsenta_profiles import empty_profile  # noqa: E402
from tsenta_trace import FALLBACK_TEXT, FALLBACK_REASON, Trace  # noqa: E402


def _profile(**overrides):
    profile = empty_profile()
    info = profile["personalInformation"]
    info["firstName"] = "Drupadh"
    info["lastName"] = "Suresh"
    info["email"] = "raven.test@my-privatemail.com"
    info["phone"] = "+15551234567"
    info["city"] = "New York"
    info["state"] = "New York"
    info["zipCode"] = "10001"
    info["country"] = "United States"
    info["summary"] = "QA automation engineer with 6 years of experience."
    profile["workExperience"] = [
        {"title": "QA Automation Engineer", "company": "Acme Corp",
         "summary": "Built Playwright test suites for SaaS products."},
    ]
    profile["skillCategories"] = [{"skills": [{"name": "Python"}, {"name": "Playwright"}]}]
    profile["workAuthorization"] = {
        "needsSponsorship": "false", "isAuthorizedToWork": "true",
    }
    for key, value in overrides.items():
        if "." in key:
            section, field = key.split(".", 1)
            profile[section][field] = value
        else:
            profile[key] = value
    return profile


class FakeChat:
    """Records messages; returns the canned content or an echo of the last user text."""

    def __init__(self, content="Echoed answer"):
        self.content = content
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        if self.content == "__echo__":
            return str(messages[-1]["content"])
        return self.content


def _field(field_id="question_1", label="Question 1", kind="text", required=False,
           options=None, hidden=False):
    return {"field_id": field_id, "label": label, "kind": kind,
            "required": required, "options": options or [], "hidden": hidden}


class TestLlmConfig:
    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("YUNWU_API_KEY", "k-test")
        cfg = llm_config()
        assert cfg["api_key"] == "k-test"
        assert cfg["base_url"] == "https://yunwu.ai/v1"
        assert cfg["model"] == "deepseek-v4-flash"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("YUNWU_BASE_URL", "https://proxy.example/v2")
        monkeypatch.setenv("YUNWU_MODEL", "gemini-2.5-flash")
        cfg = llm_config()
        assert cfg["base_url"] == "https://proxy.example/v2"
        assert cfg["model"] == "gemini-2.5-flash"

    def test_kwargs_override_env(self, monkeypatch):
        monkeypatch.setenv("YUNWU_MODEL", "default-model")
        cfg = llm_config(model="gpt-5-mini", temperature=0.9)
        assert cfg["model"] == "gpt-5-mini"
        assert cfg["temperature"] == 0.9
        assert cfg["timeout"] == 60

    def test_missing_key_is_empty_string(self, monkeypatch):
        monkeypatch.delenv("YUNWU_API_KEY", raising=False)
        assert llm_config()["api_key"] == ""


class TestChatCompletion:
    def _install_fake_open(self, monkeypatch, payload, status=200):
        import urllib.request as ur

        class FakeResponse:
            def __init__(self, body):
                self._body = body
                self.status = status

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self._body

        def fake_urlopen(request, timeout=60):
            return FakeResponse(json.dumps(payload).encode())

        monkeypatch.setattr(ur, "urlopen", fake_urlopen)

    def test_success(self, monkeypatch):
        self._install_fake_open(monkeypatch, {
            "choices": [{"message": {"content": "Yes"}}]})
        out = chat_completion([{"role": "user", "content": "hi"}],
                              {"api_key": "k"})
        assert out == "Yes"

    def test_empty_content_becomes_empty_string(self, monkeypatch):
        self._install_fake_open(monkeypatch, {
            "choices": [{"message": {"content": None}}]})
        assert chat_completion([{"role": "user", "content": "hi"}],
                               {"api_key": "k"}) == ""

    def test_no_api_key_returns_empty(self, monkeypatch):
        def boom(request, timeout=60):
            raise AssertionError("must not hit the network")
        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert chat_completion([{"role": "user", "content": "hi"}],
                               {"api_key": ""}) == ""

    def test_http_error_returns_empty(self, monkeypatch):
        def boom(request, timeout=60):
            raise OSError("connection refused")
        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert chat_completion([{"role": "user", "content": "hi"}],
                               {"api_key": "k"}) == ""

    def test_garbage_response_returns_empty(self, monkeypatch):
        class FakeResponse:
            def read(self):
                return b"not json at all"

        def fake_urlopen(request, timeout=60):
            return FakeResponse()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        assert chat_completion([{"role": "user", "content": "hi"}],
                               {"api_key": "k"}) == ""

    def test_never_raises(self, monkeypatch):
        def boom(request, timeout=60):
            raise RuntimeError("whatever")
        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert chat_completion([{"role": "user", "content": "hi"}],
                               {"api_key": "k"}) == ""


class TestProfileDigest:
    def test_renders_core_fields(self):
        digest = _profile_digest(_profile())
        assert "Drupadh" in digest
        assert "QA Automation Engineer" in digest
        assert "Acme Corp" in digest
        assert "Python" in digest

    def test_empty_profile_never_raises(self):
        digest = _profile_digest({})
        assert digest == "(profile is empty)"

    def test_bad_types_never_raise(self):
        assert _profile_digest(None) == "(profile is empty)"
        assert _profile_digest({"workExperience": "junk"}) == "(profile is empty)"


class TestMatchOption:
    def test_exact_match_ci(self):
        opts = [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]
        assert _match_option(opts, "no")["value"] == "no"

    def test_contained_match(self):
        opts = [{"value": "v1", "label": "Not a Protected Veteran"}]
        assert _match_option(opts, "Not a Protected Veteran.")["value"] == "v1"

    def test_no_match(self):
        assert _match_option([{"value": "a", "label": "Alpha"}], "Beta") is None

    def test_empty_answer(self):
        assert _match_option([{"value": "a", "label": "Alpha"}], "  ") is None

    def test_empty_options(self):
        assert _match_option([], "anything") is None

    def test_most_specific_label_wins_over_short_no(self):
        # The long phrase also matches the short "No" (label in text); the
        # LONGEST label must win so it is not shadowed by "No".
        opts = [{"value": "no", "label": "No"},
                {"value": "no_disability", "label": "No, I do not have a disability"}]
        assert _match_option(opts, "No, I do not have a disability.")["value"] == "no_disability"
        # Exact text for the short label still matches it exactly.
        assert _match_option(opts, "no")["value"] == "no"

    def test_longest_text_overlap_wins(self):
        opts = [{"value": "a", "label": "One year"},
                {"value": "b", "label": "More than one year"}]
        assert _match_option(opts, "more than one year sounds fine")["value"] == "b"


class TestAnswererRouting:
    """Matches the recovered trace distribution: profile-direct / llm / skip / fallback."""

    def test_profile_direct_map(self):
        answerer = make_llm_answerer(_profile())
        f = _field("basicInformation.firstName", "First Name", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "Drupadh"
        assert answer["source"] == "profile-direct"

    def test_profile_direct_email(self):
        answerer = make_llm_answerer(_profile())
        f = _field("email", "Email", kind="email", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "raven.test@my-privatemail.com"
        assert answer["source"] == "profile-direct"

    def test_dayforce_history_is_profile_direct_and_never_sent_to_model(self):
        profile = _profile()
        profile["workExperience"] = [{
            "role": "SOC Analyst", "company": "Example Security",
            "startDate": "Jul 2023", "endDate": "",
        }]
        chat = FakeChat("wrong")
        answerer = make_llm_answerer(profile, chat=chat)
        answer = answerer(_field(
            "work-history-positiontitle-text-input", "Position Title",
            required=True), {}, {}, None)
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "SOC Analyst"
        assert chat.calls == []

    def test_dayforce_preferred_contact_uses_email_without_model(self):
        chat = FakeChat("Mobile Phone")
        answerer = make_llm_answerer(_profile(), chat=chat)
        answer = answerer(_field(
            "jobPostingApplication_personalInfo_preferredContactMethod",
            "Preferred Contact Method", kind="select", required=True,
            options=[{"label": "Mobile Phone", "value": "mobile"},
                     {"label": "Email", "value": "email"}]), {}, {}, None)
        assert answer["value"] == "email"
        assert answer["source"] == "profile-direct"
        assert chat.calls == []

    def test_missing_pay_expectation_is_not_invented_by_model(self):
        chat = FakeChat("$100,000 per year")
        answerer = make_llm_answerer(_profile(), chat=chat)
        answer = answerer(_field(
            "screener-question-2-textarea",
            "Rate of pay expected (please indicate per hour, week, year):",
            kind="textarea", required=True), {}, {}, None)
        assert answer["source"] == "skip"
        assert answer["value"] == ""
        assert chat.calls == []

    def test_conditional_followup_is_not_sent_to_model_or_profile_map(self):
        chat = FakeChat("Made-up explanation")
        answerer = make_llm_answerer(_profile(), chat=chat)
        answer = answerer(_field(
            "screener-question-9-textarea",
            'If you answered "yes" to either, state dates and reasons.',
            kind="textarea"), {}, {}, None)
        assert answer["source"] == "skip"
        assert answer["value"] == ""
        assert chat.calls == []

    def test_consent_checkbox_auto_accepted(self):
        # GDPR/privacy consent checkboxes are now auto-answered Yes (profile-direct)
        answerer = make_llm_answerer(_profile())
        f = _field("consent", "I consent to data processing", kind="checkbox")
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "Yes"
        assert answer["source"] == "profile-direct"

    def test_sponsorship_no_comes_from_profile(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_sponsor", "Do you require visa sponsorship?",
                   kind="radio", required=True,
                   options=[{"value": "spon_yes", "label": "Yes"},
                            {"value": "spon_no", "label": "No"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "spon_no"
        assert answer["source"] == "profile-direct"
        assert answer["display"] == "No"

    def test_authorized_yes_comes_from_profile(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_auth", "Are you legally authorized to work in the US?",
                   kind="radio", required=True,
                   options=[{"value": "a_yes", "label": "Yes"},
                            {"value": "a_no", "label": "No"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "a_yes"
        assert answer["source"] == "profile-direct"
        assert answer["display"] == "Yes"

    def test_unknown_employee_relationship_needs_review(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_rel", "Are you a relative of a company employee?",
                   kind="radio", required=True,
                   options=[{"value": "r_yes", "label": "Yes"},
                            {"value": "r_no", "label": "No"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["source"] == "skip"

    def test_unknown_veteran_status_needs_review(self):
        answerer = make_llm_answerer(_profile())
        f = _field("veteran_status", "Veteran Status", kind="radio", required=True,
                   options=[{"value": "prot", "label": "I identify as a protected veteran"},
                            {"value": "not_prot", "label": "Not a Protected Veteran"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["source"] == "skip"

    def test_unknown_disability_status_needs_review(self):
        answerer = make_llm_answerer(_profile())
        f = _field("disability", "Do you have a disability?", kind="radio",
                   required=True,
                   options=[{"value": "d_yes", "label": "Yes, I have a disability"},
                            {"value": "d_no", "label": "No, I do not have a disability"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["source"] == "skip"

    def test_race_declines(self):
        answerer = make_llm_answerer(_profile())
        f = _field("race", "Race/Ethnicity", kind="select", required=True,
                   options=[{"value": "decline", "label": "Decline to self-identify"},
                            {"value": "white", "label": "White"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "decline"
        assert answer["source"] == "profile-direct"
        assert answer["reason"] == "No demographic identity inferred"

    def test_how_did_you_hear_other(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_hear", "How did you hear about us?", kind="radio",
                   required=True,
                   options=[{"value": "src_other", "label": "Other"},
                            {"value": "src_ref", "label": "Referral"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "src_other"
        assert answer["source"] == "llm"
        assert answer["display"] == "Other"

    def test_how_did_you_hear_no_other_requires_review(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_hear", "How did you hear about us?", kind="radio",
                   required=True,
                   options=[{"value": "src_lk", "label": "LinkedIn"},
                            {"value": "src_jb", "label": "Job Board"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["source"] == "skip"

    def test_consent_text_kind_requires_review(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_privacy", "Applicant Privacy Notice*", kind="text", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["source"] == "skip"

    def test_authorized_text_kind_answers_yes_not_country(self):
        # Live trace regression: a text-kind authorization question must be
        # answered "Yes", NOT with the profile country ("...the country to
        # which you are applying..." contains "country").
        answerer = make_llm_answerer(_profile())
        f = _field("q_auth", "Are you authorized to work lawfully in the country "
                             "to which you are applying?", kind="text", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "Yes"
        assert answer["source"] == "profile-direct"

    def test_sponsorship_text_kind_answers_no(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_spon", "Do you now or in the future require sponsorship?",
                   kind="text", required=False)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "No"

    def test_canada_authorization_is_not_inferred_from_us_profile(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_auth_ca", "Are you legally authorized to work in Canada?",
                   kind="radio", required=True,
                   options=[{"value": "yes", "label": "Yes"},
                            {"value": "no", "label": "No"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["source"] == "skip"
        assert "country" in answer["reason"].lower()

    def test_how_did_you_hear_text_kind_uses_profile_value(self):
        profile = _profile()
        profile["workPreferences"]["howDidYouHearAboutRole"] = "LinkedIn"
        answerer = make_llm_answerer(profile)
        f = _field("q_hear", "How did you hear about this job?", kind="text", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "LinkedIn"

    def test_optional_open_question_model_echoing_fallback_skips(self):
        # Live trace regression: optional EEO questions (race/gender...) get
        # the fallback text echoed by the model — leave them BLANK instead.
        chat = FakeChat(FALLBACK_TEXT)
        answerer = make_llm_answerer(_profile(), chat=chat)
        f = _field("q_race", "Which of the following best describes your race?",
                   kind="text", required=False)
        answer = answerer(f, {}, {}, None)
        assert answer["source"] == "skip"
        assert answer["value"] == ""
        assert answer["reason"] == "unanswerable optional question"

    def test_optional_transgender_text_skips_not_fallback(self):
        # Live trace regression: "Do you personally identify as transgender?"
        # is optional and has no options — must skip, not fill fallback text.
        answerer = make_llm_answerer(_profile())
        f = _field("q_trans", "Do you personally identify as transgender?",
                   kind="text", required=False)
        answer = answerer(f, {}, {}, None)
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_other_source_followup_uses_profile_or_llm(self):
        answerer = make_llm_answerer(_profile())
        f = _field("q_other", "Name of the Other Source", kind="text")
        answer = answerer(f, {}, {}, None)
        assert answer["source"] == "llm"

    def test_hidden_skipped(self):
        answerer = make_llm_answerer(_profile())
        f = _field("secret", "Hidden field", hidden=True)
        answer = answerer(f, {}, {}, None)
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_open_required_textarea_llm_answer(self):
        chat = FakeChat("I am a QA automation engineer with 6 years of experience.")
        answerer = make_llm_answerer(_profile(), chat=chat)
        f = _field("why_you", "Why do you want to work here?",
                   kind="textarea", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"].startswith("I am a QA automation engineer")
        assert answer["source"] == "llm"
        assert len(chat.calls) == 1
        prompt = chat.calls[0][-1]["content"]
        assert "Acme Corp" in prompt
        assert "Why do you want to work here?" in prompt

    def test_open_optional_question_llm_answer(self):
        chat = FakeChat("Sure, here is my experience.")
        answerer = make_llm_answerer(_profile(), chat=chat)
        f = _field("tell_us", "Tell us about yourself", kind="textarea")
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "Sure, here is my experience."
        assert answer["source"] == "llm"

    def test_open_required_no_llm_falls_back_to_text(self):
        answerer = make_llm_answerer(_profile(), llm_cfg={"api_key": ""})
        f = _field("why_you", "Why do you want to work here?",
                   kind="textarea", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == FALLBACK_TEXT
        assert answer["source"] == "fallback"
        assert answer["reason"] == "llm unavailable (no API key)"

    def test_open_optional_no_llm_skips(self):
        answerer = make_llm_answerer(_profile(), llm_cfg={"api_key": ""})
        f = _field("tell_us", "Tell us about yourself", kind="textarea")
        answer = answerer(f, {}, {}, None)
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_select_llm_picks_option_and_maps_value(self):
        chat = FakeChat("Six months to a year")
        answerer = make_llm_answerer(_profile(), chat=chat)
        f = _field("relocation", "How soon can you start?",
                   kind="select", required=True,
                   options=[{"value": "6m", "label": "Six months to a year"},
                            {"value": "1m", "label": "Within a month"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "6m"
        assert answer["display"] == "Six months to a year"
        assert answer["source"] == "llm"

    def test_select_llm_unavailable_required_requires_review(self):
        answerer = make_llm_answerer(_profile(), llm_cfg={"api_key": ""})
        f = _field("relocation", "Relocation", kind="select", required=True,
                   options=[{"value": "6m", "label": "Six months"},
                            {"value": "1m", "label": "Within a month"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["source"] == "skip"
        assert "safely" in answer["reason"]

    def test_select_llm_unavailable_optional_skips(self):
        answerer = make_llm_answerer(_profile(), llm_cfg={"api_key": ""})
        f = _field("relocation", "Relocation", kind="select",
                   options=[{"value": "6m", "label": "Six months"}])
        answer = answerer(f, {}, {}, None)
        assert answer["source"] == "skip"

    def test_unmatched_required_text_falls_back_verbatim(self):
        answerer = make_llm_answerer(_profile(), llm_cfg={"api_key": ""})
        f = _field("q_middle", "Middle Name", kind="text", required=True)
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == FALLBACK_TEXT
        assert answer["source"] == "fallback"
        assert answer["reason"] == "llm unavailable (no API key)"

    def test_answerer_never_raises_on_bad_field(self):
        answerer = make_llm_answerer(_profile(), llm_cfg={"api_key": ""})
        assert answerer(None, {}, {}, None) is not None
        assert answerer({"label": None}, {}, {}, None) is not None

    def test_profile_direct_beats_llm_route(self):
        chat = FakeChat("wrong answer")
        answerer = make_llm_answerer(_profile(), chat=chat)
        f = _field("candidate_phone", "Phone Number", kind="phone")
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "+15551234567"
        assert answer["source"] == "profile-direct"
        assert chat.calls == []

    def test_job_context_included_in_prompt(self):
        chat = FakeChat("answer")
        answerer = make_llm_answerer(_profile(), chat=chat,
                                     job_context={"company": "Mozilla"})
        f = _field("why", "Why us?", kind="textarea", required=True)
        answerer(f, {}, {}, None)
        assert "Mozilla" in chat.calls[0][-1]["content"]

    def test_health_status_is_not_inferred_by_llm(self):
        chat = FakeChat("No, I do not have a disability")
        answerer = make_llm_answerer(_profile(), chat=chat)
        f = _field("q_disability", "Do you have a disability?", kind="radio",
                   required=True,
                   options=[{"value": "d_yes", "label": "Yes, I have a disability"},
                            {"value": "d_no", "label": "No, I do not have a disability"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == ""
        assert answer["display"] == ""
        assert answer["source"] == "skip"

    def test_llm_picks_option_through_generic_path(self):
        chat = FakeChat("Six months to a year is fine.")
        answerer = make_llm_answerer(_profile(), chat=chat)
        f = _field("start_date", "Preferred start date?", kind="radio",
                   required=True,
                   options=[{"value": "immediate", "label": "Immediately"},
                            {"value": "6m", "label": "Six months to a year"}])
        answer = answerer(f, {}, {}, None)
        assert answer["value"] == "6m"
        assert answer["display"] == "Six months to a year"
        assert answer["source"] == "llm"

    def test_llm_answerer_recalls_from_persistent_memory(self, tmp_path):
        from backend.src.tools.tsenta_memory import remember_answer
        mem_file = str(tmp_path / "llm_test_mem.json")
        remember_answer(
            label="What is your favorite cloud security framework?",
            value="NIST CSF 2.0",
            kind="text",
            path=mem_file,
        )
        chat = FakeChat("Should not be called because memory has the answer")
        import os
        os.environ["TSENTA_MEMORY_PATH"] = mem_file
        try:
            answerer = make_llm_answerer(_profile(), chat=chat)
            f = _field("q_cloud_sec", "What is your favorite cloud security framework?", kind="text", required=True)
            answer = answerer(f, {}, {}, None)
            assert answer["source"] == "user-memory"
            assert answer["value"] == "NIST CSF 2.0"
            assert len(chat.calls) == 0  # LLM was never contacted!
        finally:
            os.environ.pop("TSENTA_MEMORY_PATH", None)


class TestLiveLlm:
    """Live LLM smoke tests. Skipped unless LIVE=1 (or run with pytest -m live)."""

    @pytest.mark.live
    def test_live_chat_completion(self):
        if os.environ.get("LIVE") != "1":
            pytest.skip("live test: set LIVE=1")
        cfg = llm_config()
        if not cfg["api_key"]:
            pytest.skip("YUNWU_API_KEY not set")
        out = chat_completion([
            {"role": "system", "content": "Reply with the single word OK."},
            {"role": "user", "content": "Are you online?"},
        ], cfg)
        assert out.strip().upper() == "OK"

    @pytest.mark.live
    def test_live_llm_answer_open_question(self):
        if os.environ.get("LIVE") != "1":
            pytest.skip("live test: set LIVE=1")
        cfg = llm_config()
        if not cfg["api_key"]:
            pytest.skip("YUNWU_API_KEY not set")
        profile = _profile()
        answerer = make_llm_answerer(profile, llm_cfg=cfg)
        f = _field("why_you", "Why do you want to work here?",
                   kind="textarea", required=True)
        answer = answerer(f, {}, {}, None)
        # Honest mode: the model either answers (llm) or declines with the
        # verbatim fallback text (fallback) — both are valid for a required
        # open question; it must never be empty or a skip.
        assert answer["source"] in ("llm", "fallback")
        assert answer["value"]

    @pytest.mark.live
    def test_live_llm_select_option_mapping(self):
        if os.environ.get("LIVE") != "1":
            pytest.skip("live test: set LIVE=1")
        cfg = llm_config()
        if not cfg["api_key"]:
            pytest.skip("YUNWU_API_KEY not set")
        answerer = make_llm_answerer(_profile(), llm_cfg=cfg)
        f = _field("employer", "Where do you currently work?",
                   kind="select", required=True,
                   options=[{"value": "acme", "label": "Acme Corp"},
                            {"value": "other", "label": "Another company"},
                            {"value": "none", "label": "Not employed"}])
        answer = answerer(f, {}, {}, None)
        assert answer["source"] == "llm"
        assert answer["value"] == "acme"
        assert answer["display"] == "Acme Corp"


class TestAnswererIntegration:
    def test_answer_fields_with_llm_answerer(self):
        try:
            from backend.src.tools.tsenta_apply import answer_fields
        except ImportError:
            from tsenta_apply import answer_fields

        fields = [
            _field("basicInformation.firstName", "First Name", required=True),
            _field("email", "Email", kind="email", required=True),
            _field("q_sponsor", "Do you require sponsorship?", kind="radio",
                   required=True,
                   options=[{"value": "y", "label": "Yes"}, {"value": "n", "label": "No"}]),
            _field("why", "Why do you want this job?", kind="textarea", required=True),
            _field("q_optional", "Optional question", kind="text"),
        ]
        chat = FakeChat("I love building test infrastructure.")
        trace = Trace()
        actions = answer_fields(fields, _profile(), {}, trace,
                                answerer=make_llm_answerer(_profile(), chat=chat))
        by_id = {a["field_id"]: a for a in actions}
        assert by_id["basicInformation.firstName"]["source"] == "profile-direct"
        assert by_id["email"]["source"] == "profile-direct"
        assert by_id["q_sponsor"]["source"] == "profile-direct"
        assert by_id["why"]["source"] == "llm"
        assert by_id["q_optional"]["source"] == "skip"
        sources = [a["source"] for a in actions]
        assert sources.count("profile-direct") == 3
        assert sources.count("llm") == 1
        trace_answers = trace.to_json()
        assert "llm" in trace_answers
        assert trace.derivedMissingFields is not None

    def test_llm_answer_fields_wrapper(self):
        from tsenta_llm import llm_answer_fields

        fields = [
            _field("basicInformation.firstName", "First Name", required=True),
            _field("why", "Why do you want this job?", kind="textarea", required=True),
        ]
        chat = FakeChat("Because of the mission.")
        actions = llm_answer_fields(fields, _profile(), {}, chat=chat)
        by_id = {a["field_id"]: a for a in actions}
        assert by_id["basicInformation.firstName"]["source"] == "profile-direct"
        assert by_id["why"]["value"] == "Because of the mission."
        assert by_id["why"]["source"] == "llm"

    def test_llm_answer_fields_never_raises(self):
        from tsenta_llm import llm_answer_fields

        assert llm_answer_fields([], _profile()) == []

    def test_apply_job_dry_run_with_llm_answerer(self, monkeypatch):
        """End-to-end dry run through apply_job with the LLM answerer injected."""
        import test_tsenta_apply as app_tests
        try:
            from backend.src.tools.tsenta_apply import apply_job
            from backend.src.tools.tsenta_config import default_config
        except ImportError:
            from tsenta_apply import apply_job
            from tsenta_config import default_config

        chat = FakeChat("Motivated by the product vision.")
        elements = [
            app_tests.el_text_input("first_name", required=True),
            app_tests.el_text_input("email", required=True),
            app_tests.el_text_input("why", required=True),
        ]
        page = app_tests.FakePage(elements)
        result = json.loads(apply_job(
            "https://jobs.lever.co/company/role-123",
            _profile(), default_config(), dry_run=True,
            answerer=make_llm_answerer(_profile(), chat=chat),
            _page_provider=lambda: page,
        ))
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert result["submitted"] is False
        assert chat.calls  # the LLM was consulted
        sources = result["sources"]
        assert sources.get("llm", 0) >= 1
        assert sources.get("profile-direct", 0) >= 2
