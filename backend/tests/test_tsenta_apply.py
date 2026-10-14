"""M3 unit tests: tsenta_apply (browser-free via FakePage) + live smoke test.

The live test is skipped by default; run with: pytest -m live
"""

import json
import os

import pytest

from backend.src.tools import tsenta_apply
from backend.src.tools.tsenta_apply import (
    answer_fields,
    apply_job,
    collect_fields,
    default_answerer,
)
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_profiles import empty_profile, profile_from_json
from backend.src.tools.tsenta_trace import Trace


def make_profile():
    profile = empty_profile()
    profile["personalInformation"].update({
        "firstName": "Drupadh", "lastName": "Suresh", "email": "raven@example.com",
        "phone": "+15551234567", "address": "New York, NY, USA", "city": "New York",
        "state": "New York", "zipCode": "10001", "country": "United States",
        "linkedinUrl": "https://linkedin.com/in/raven-test",
    })
    profile["workAuthorization"] = {
        "visaType": None, "optStatus": None, "needsSponsorship": False,
        "isAuthorizedToWork": True,
        "workAuthorizations": [{"visaType": None, "optStatus": None, "visaStatus": None,
                                "countryCode": "US", "needsSponsorship": False,
                                "authorizationBasis": "citizen", "isAuthorizedToWork": True}],
        "citizenshipCountries": ["US"],
    }
    profile["resumeFormat"] = "pdf"
    return profile


def field(**kwargs):
    base = {"field_id": "f1", "label": "Field", "kind": "text", "required": True,
            "options": [], "hidden": False}
    base.update(kwargs)
    return base


class FakeElement:
    def __init__(self, tag="input", attrs=None, text="", checked=False, visible=True):
        self.tag_name = tag
        self._attrs = attrs or {}
        self._text = text
        self._checked = checked
        self._visible = visible
        self._box = {"x": 0, "y": 0, "width": 100, "height": 20}
        self._children = []
        self.filled = None
        self.selected = None
        self.clicked = False

    def get_attribute(self, name):
        return self._attrs.get(name)

    def evaluate(self, expression):
        if "closest" in expression or "autofill" in expression:
            return False
        return self.tag_name or ""

    def inner_text(self):
        return self._text

    def is_visible(self):
        return self._visible

    def bounding_box(self):
        return self._box if self._visible else None

    def is_checked(self):
        return self._checked

    def check(self):
        self._checked = True
        self.clicked = True

    def uncheck(self):
        self._checked = False

    def click(self):
        self.clicked = True

    def fill(self, value):
        self.filled = value

    def select_option(self, value=None, label=None):
        self.selected = value

    def set_input_files(self, path):
        self.filled = path

    def query_selector_all(self, selector):
        return list(self._children)


class NearbyQuestionElement(FakeElement):
    """Fake input whose closest question container supplies a heading."""

    def __init__(self, *args, nearby_label="", **kwargs):
        super().__init__(*args, **kwargs)
        self.nearby_label = nearby_label

    def evaluate(self, expression):
        if "const root" in expression or "const question" in expression:
            return self.nearby_label
        return super().evaluate(expression)


class FakeFrame:
    def __init__(self, elements=None, url="about:blank"):
        self.elements = elements or []
        self.url = url
        self._calls = []

    def query_selector_all(self, selector):
        self._calls.append(("query_selector_all", selector))
        return list(self.elements)

    def query_selector(self, selector):
        self._calls.append(("query_selector", selector))
        for element in self.elements:
            tag = element.tag_name
            if "input[type='submit']" in selector and tag == "input" and \
                    (element.get_attribute("type") or "") == "submit":
                return element
            if "button[type='submit']" in selector and tag == "button" and \
                    (element.get_attribute("type") or "") == "submit":
                return element
            if "button" in selector and tag == "button":
                return element
        return None

    def wait_for_selector(self, selector, timeout=None):
        self._calls.append(("wait_for_selector", selector, timeout))

    def wait_for_timeout(self, ms):
        self._calls.append(("wait_for_timeout", ms))


class FakePage(FakeFrame):
    def __init__(self, elements=None, url="about:blank", frames_urls=None):
        super().__init__(elements, url)
        self.frames = [self]
        self.goto_calls = []
        self.closed = False

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = url

    def close(self):
        self.closed = True


def el_text_input(name, label="", required=False, placeholder="", kind="text", visible=True):
    return FakeElement(tag="input", attrs={"name": name, "type": kind, "placeholder": placeholder,
                                           "required": "required" if required else None},
                       visible=visible)


def el_select(name, options, label="", required=False, visible=True):
    select = FakeElement(tag="select", attrs={"name": name,
                                              "required": "required" if required else None},
                         visible=visible)
    select._children = [FakeElement(tag="option", attrs={"value": v}, text=t)
                        for t, v in options]
    return select


def el_radio(name, value, label, visible=True):
    return FakeElement(tag="input", attrs={"name": name, "type": "radio", "value": value,
                                           "aria-label": label}, visible=visible)


def el_checkbox(name, label, checked=False):
    return FakeElement(tag="input", attrs={"name": name, "type": "checkbox",
                                           "aria-label": label}, checked=checked)


def el_file(name, required=False):
    return FakeElement(tag="input", attrs={"name": name, "type": "file",
                                           "required": "required" if required else None})


class WorkdayPage(FakePage):
    """FakePage that simulates Workday selector availability.

    wait_for_selector succeeds when any comma-part of the requested selector
    is in `available` (the elements the page actually has); otherwise it
    raises TimeoutError like Playwright. query_selector returns the configured
    button (if any). An apply iframe appears in page.frames after the apply
    button has been clicked (post_click_frames), or immediately (iframes).
    """

    def __init__(self, elements=None, url="about:blank", available=None,
                 available_after_apply=None, available_after_click=None,
                 iframes=None, post_click_frames=None, button=None):
        super().__init__(elements, url)
        self.available = {a.strip().lower() for a in (available or [])}
        self.available_after_apply = {a.strip().lower() for a in (available_after_apply or [])}
        self.available_after_click = {a.strip().lower() for a in (available_after_click or [])}
        self.iframes = list(iframes or [])
        self.post_click_frames = list(post_click_frames or [])
        self.button = button
        self._stored_frames = None

    @property
    def frames(self):
        if self._stored_frames is not None:
            return self._stored_frames
        frames = [self] + self.iframes
        if self.button is not None and self.button.clicked:
            frames += self.post_click_frames
        return frames

    @frames.setter
    def frames(self, value):
        self._stored_frames = value

    def _current_available(self):
        avail = set(self.available)
        if self.url.rstrip("/").endswith("/apply"):
            avail |= self.available_after_apply
        if self.button is not None and self.button.clicked:
            avail |= self.available_after_click
        return avail

    def wait_for_selector(self, selector, timeout=None):
        self._calls.append(("wait_for_selector", selector, timeout))
        parts = {p.strip().lower() for p in selector.split(",")}
        if parts & self._current_available():
            return True
        raise TimeoutError("selector not found")

    def query_selector(self, selector):
        self._calls.append(("query_selector", selector))
        if self.button is not None:
            return self.button
        return None


class TestWorkdayOpenForm:
    def test_direct_fields_on_posting_page(self):
        page = WorkdayPage(
            url="https://acme.wd1.myworkdayjobs.com/Acme/job/NY/1234",
            available=["form[data-automation-id='apply-form']"])
        tsenta_apply._open_workday_form(page, page.url, 45000)
        assert len(page.goto_calls) == 1  # never navigated to /apply

    def test_apply_wizard_iframe_flow(self):
        iframe = FakeFrame(url="https://acme.wd1.myworkdayjobs.com/wd/cx/acme/apply/1")
        page = WorkdayPage(
            url="https://acme.wd1.myworkdayjobs.com/Acme/job/NY/1234",
            available=["iframe"], iframes=[iframe])
        tsenta_apply._open_workday_form(page, page.url, 45000)
        assert tsenta_apply._form_frame(page) is iframe
        assert len(page.goto_calls) == 1

    def test_apply_suffix_navigation(self):
        original = "https://acme.wd1.myworkdayjobs.com/Acme/job/NY/1234"
        page = WorkdayPage(
            url=original,
            available_after_apply=["form[data-automation-id='apply-form']"])
        tsenta_apply._open_workday_form(page, page.url, 45000)
        urls = [call[0] for call in page.goto_calls]
        assert urls == [original, original + "/apply"]

    def test_apply_button_click_opens_iframe(self):
        button = FakeElement(tag="button", attrs={"data-automation-id": "applyBtn"},
                             text="Apply Now")
        iframe = FakeFrame(url="https://acme.wd1.myworkdayjobs.com/wd/cx/acme/apply/1")
        page = WorkdayPage(
            url="https://acme.wd1.myworkdayjobs.com/Acme/job/NY/1234",
            available=["button[data-automation-id*='apply' i]"],
            available_after_click=["iframe"],
            post_click_frames=[iframe], button=button)
        tsenta_apply._open_workday_form(page, page.url, 45000)
        assert button.clicked is True
        assert tsenta_apply._form_frame(page) is iframe

    def test_no_apply_surface_is_an_explicit_failure(self):
        page = WorkdayPage(url="https://acme.wd1.myworkdayjobs.com/Acme/job/NY/1234")
        with pytest.raises(RuntimeError, match="workday-application-form-not-found"):
            tsenta_apply._open_workday_form(page, page.url, 45000)

    def test_data_automation_id_is_stable_field_identity(self):
        element = FakeElement(attrs={
            "type": "text",
            "data-automation-id": "legalNameSection_firstName",
            "aria-label": "First Name",
            "aria-required": "true",
        })
        fields = collect_fields(FakeFrame([element]), max_passes=1, timeout_ms=1)
        assert fields[0]["field_id"] == "legalNameSection_firstName"
        assert fields[0]["required"] is True

    def test_custom_workday_option_matches_by_label_without_first_option_guess(self):
        control = FakeElement(tag="button", attrs={
            "data-automation-id": "countryPicker",
            "aria-haspopup": "listbox",
        }, text="Select a Country")
        canada = FakeElement(tag="div", attrs={"role": "option"}, text="Canada")
        usa = FakeElement(tag="div", attrs={"role": "option"}, text="United States")
        frame = FakeFrame([control, canada, usa])
        assert tsenta_apply._click_custom_option(
            frame, control, "United States", "United States") is True
        assert usa.clicked is True
        assert canada.clicked is False


class TestWalkerRegistry:
    def test_builtin_profiles_exist(self):
        for ats in ("ashby", "workable", "jazzhr", "bamboohr",
                    "smartrecruiters", "icims", "rippling", "oraclecloud",
                    "jobvite", "breezyhr", "recruitee", "teamtailor",
                    "dayforce", "paylocity"):
            profile = tsenta_apply.ats_walker(ats)
            assert profile.get("submit_selectors")
            assert profile.get("confirm_selectors")

    def test_brassring_has_a_dedicated_walker_profile(self):
        profile = tsenta_apply.ats_walker("brassring")
        assert "button[id*='submit' i]" in profile["submit_selectors"]
        assert "applicationConfirmation" in " ".join(profile["confirm_selectors"])

    def test_dayforce_reviewed_privacy_step_clicks_only_enabled_save(self):
        class EnabledButton(FakeElement):
            def is_enabled(self):
                return True

            def click(self, **_kwargs):
                self.clicked = True

        save = EnabledButton(tag="button", attrs={
            "test-id": "client-privacy-policy-modal-save-button",
        })
        frame = FakeFrame([save])
        setattr(frame, "_nori_scope_selector", "[role='dialog']")

        assert tsenta_apply._advance_form(frame, "dayforce") is True
        assert save.clicked is True
        assert getattr(frame, "_nori_scope_selector") == ""

    def test_register_roundtrip_and_unregister(self):
        tsenta_apply.register_ats_walker(
            "reg_test_ats", submit_selectors=("button[data-reg='mine']",),
            confirm_selectors=("custom confirmation", "css:.custom-confirm"))
        try:
            profile = tsenta_apply.ats_walker("reg_test_ats")
            assert profile["submit_selectors"] == ("button[data-reg='mine']",)
            assert profile["confirm_selectors"] == ("custom confirmation", "css:.custom-confirm")
        finally:
            tsenta_apply.unregister_ats_walker("reg_test_ats")
        assert tsenta_apply.ats_walker("reg_test_ats") == {}

    def test_register_validates_id(self):
        with pytest.raises(TypeError):
            tsenta_apply.register_ats_walker("")

    def test_submit_uses_registered_selector(self):
        tsenta_apply.register_ats_walker(
            "reg_submit_ats", submit_selectors=("button[data-reg='mine']",))
        try:
            frame = FakeFrame([FakeElement(tag="button",
                                           attrs={"data-reg": "mine", "type": "button"})])
            clicked = tsenta_apply._submit(frame, 1000, "reg_submit_ats")
            assert clicked is True
            assert ("query_selector", "button[data-reg='mine']") in frame._calls
        finally:
            tsenta_apply.unregister_ats_walker("reg_submit_ats")

    def test_submit_falls_back_to_generic_when_no_profile(self):
        frame = FakeFrame([FakeElement(tag="button", attrs={"type": "submit"})])
        clicked = tsenta_apply._submit(frame, 1000, "reg_unknown_ats")
        assert clicked is True

    def test_confirm_uses_registered_text_signal(self):
        tsenta_apply.register_ats_walker(
            "reg_confirm_ats", confirm_selectors=("custom confirmation",))
        try:
            page = WorkdayPage(available=["text='custom confirmation'"])
            assert tsenta_apply._confirm_submission(page, 1000, "reg_confirm_ats") is True
        finally:
            tsenta_apply.unregister_ats_walker("reg_confirm_ats")

    def test_confirm_uses_registered_css_signal(self):
        tsenta_apply.register_ats_walker(
            "reg_confirm_css_ats", confirm_selectors=("css:.custom-confirm",))
        try:
            page = WorkdayPage(available=[".custom-confirm"])
            assert tsenta_apply._confirm_submission(page, 1000, "reg_confirm_css_ats") is True
        finally:
            tsenta_apply.unregister_ats_walker("reg_confirm_css_ats")

    def test_generic_thank_you_does_not_confirm_submission(self):
        page = WorkdayPage(available=["text='thank you'"])
        assert tsenta_apply._confirm_submission(page, 1000, "unknown") is False

    def test_open_form_uses_registered_opener(self):
        calls = []

        def opener(page, url, timeout_ms):
            calls.append((url, timeout_ms))
            page.url = url

        tsenta_apply.register_ats_walker("reg_open_ats", open=opener)
        try:
            page = FakePage()
            tsenta_apply._open_form(page, "https://reg.example/jobs/1", "reg_open_ats", 45000)
            assert calls == [("https://reg.example/jobs/1", 45000)]
        finally:
            tsenta_apply.unregister_ats_walker("reg_open_ats")

    def test_open_form_ignores_broken_opener(self):
        def broken(page, url, timeout_ms):
            raise RuntimeError("boom")

        tsenta_apply.register_ats_walker("reg_broken_ats", open=broken)
        try:
            page = FakePage()
            tsenta_apply._open_form(page, "https://x.example/jobs/1", "reg_broken_ats", 45000)
            assert page.goto_calls  # generic fallback ran
        finally:
            tsenta_apply.unregister_ats_walker("reg_broken_ats")


class TestDefaultAnswerer:
    def test_full_name_current_company_and_location_are_profile_direct(self):
        profile = make_profile()
        profile["workExperience"] = [{"company": "Acme Security", "isCurrent": True}]
        cases = [
            (field(field_id="name", label="Full name✱"), "Drupadh Suresh"),
            (field(field_id="org", label="Current company ✱"), "Acme Security"),
            (field(field_id="location", label="Current location"), "New York, New York"),
        ]
        for question, expected in cases:
            answer = default_answerer(question, profile, {}, Trace())
            assert answer["source"] == "profile-direct"
            assert answer["value"] == expected

    def test_paylocity_sms_permission_requires_human_review(self):
        answer = default_answerer(field(
            field_id="info.smsOptedIn", kind="select",
            label="We may use SMS during the hiring process. Do you give us permission to text you?",
            options=[{"label": "Yes", "value": "true"},
                     {"label": "No", "value": "false"}]),
            make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert "Consent" in answer["reason"]

    def test_dayforce_preferred_contact_uses_declared_email_channel(self):
        answer = default_answerer(field(
            field_id="jobPostingApplication_personalInfo_preferredContactMethod",
            label="Preferred Contact Method", kind="select",
            options=[{"label": "Mobile Phone", "value": "mobile"},
                     {"label": "Email", "value": "email"}]),
            make_profile(), {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "email"
        assert answer["display"] == "Email"

    def test_dayforce_history_field_is_profile_direct_not_generic_fallback(self):
        profile = make_profile()
        profile["workExperience"] = [{
            "company": "Example Security", "role": "SOC Analyst",
            "startDate": "Jul 2023", "endDate": "",
        }]
        answer = default_answerer(field(
            field_id="work-history-positiontitle-text-input",
            label="Position Title"), profile, {}, Trace())
        assert answer == {"value": "SOC Analyst", "source": "profile-direct",
                          "display": "SOC Analyst"}

    def test_acknowledgement_wins_over_sponsorship_keyword(self):
        answer = default_answerer(field(
            field_id="multiQuestionAnswer1238536", kind="radio",
            label=("We cannot provide visa sponsorship. Do you acknowledge and "
                   "confirm that you have read and understand this information?"),
            options=[{"label": "Yes, I acknowledge", "value": "Yes"},
                     {"label": "No", "value": "No"}]),
            make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert "attestation" in answer["reason"].lower()

    def test_highest_education_uses_truthful_profile_degree(self):
        profile = make_profile()
        profile["education"] = [{"degree": "Master of Science"}]
        answer = default_answerer(field(
            field_id="education", kind="radio",
            label="What is your highest level of education completed?",
            options=[{"label": "Bachelor's Degree", "value": "BS"},
                     {"label": "Master's Degree", "value": "MS"}]),
            profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "MS"

    def test_missing_mapped_salary_never_gets_prose_fallback(self):
        answer = default_answerer(field(
            field_id="info.minimumDesiredSalary", label="Salary Range"),
            make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert "expectedAnnualSalary" in answer["reason"]

    def test_paylocity_rate_of_pay_without_profile_salary_needs_review(self):
        answer = default_answerer(field(
            field_id="screener-question-2-textarea",
            label="Rate of pay expected (please indicate per hour, week, year):",
            kind="textarea", required=True), make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""
        assert "expectedAnnualSalary" in answer["reason"]

    def test_conditional_followup_is_not_misread_as_address_state(self):
        answer = default_answerer(field(
            field_id="screener-question-9-textarea",
            label='If you answered "yes" to either, state dates and reasons.',
            kind="textarea", required=False), make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""
        assert "Conditional" in answer["reason"]

    def test_missing_available_start_date_never_gets_prose_fallback(self):
        answer = default_answerer(field(
            field_id="info.dateAvailableToStart", label="Available to Start"),
            make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert "start date" in answer["reason"].lower()

    def test_paylocity_parser_upload_is_first_and_not_duplicated(self):
        assert tsenta_apply._file_document_kind({
            "field_id": "btn-forceResume", "label": "Upload Resume",
            "required": False,
        }) == "resume"
        assert tsenta_apply._file_document_kind({
            "field_id": "btn-resume", "label": "Select Resume to Upload",
            "required": False,
        }) == ""

    def test_optional_disability_signature_is_never_auto_filled_as_name(self):
        answer = default_answerer(field(
            field_id="resumator-eeoc_disability_signature-value",
            label="Name", required=False), make_profile(), default_config(), Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_profile_direct_first_name(self):
        answer = default_answerer(field(field_id="first_name", label="First Name"),
                                  make_profile(), {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "Drupadh"

    def test_email_mapping(self):
        answer = default_answerer(field(field_id="email", label="Email"),
                                  make_profile(), {}, Trace())
        assert answer["value"] == "raven@example.com"

    def test_phone_mapping(self):
        answer = default_answerer(field(field_id="phone", label="Phone"),
                                  make_profile(), {}, Trace())
        assert answer["value"] == "+15551234567"

    def test_profile_value_maps_to_native_select_option_value(self):
        answer = default_answerer(field(
            field_id="countryId.value", label="Country", kind="select",
            options=[{"label": "United States", "value": "1"},
                     {"label": "Canada", "value": "2"}]),
            make_profile(), {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "1"
        assert answer["display"] == "United States"

    def test_state_abbreviation_maps_to_full_state_option(self):
        profile = make_profile()
        profile["personalInformation"]["state"] = "IL"
        answer = default_answerer(field(
            field_id="state.value", label="State", kind="select",
            options=[{"label": "California", "value": "5"},
                     {"label": "Illinois", "value": "14"}]),
            profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "14"
        assert answer["display"] == "Illinois"

    def test_country_label_does_not_match_state_inside_united_states(self):
        profile = make_profile()
        profile["personalInformation"]["state"] = "IL"
        answer = default_answerer(field(
            field_id="countryId.value", label="Country United States", kind="select",
            options=[{"label": "United States", "value": "1"},
                     {"label": "Canada", "value": "2"}]),
            profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "1"
        assert answer["display"] == "United States"

    def test_required_portfolio_field_uses_github_when_website_is_blank(self):
        profile = make_profile()
        profile["personalInformation"]["website"] = ""
        profile["personalInformation"]["githubUrl"] = "https://github.com/example"
        answer = default_answerer(field(
            field_id="websiteUrl", label="Website, Blog or Portfolio", required=True),
            profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "https://github.com/example"

    def test_hidden_field_skipped(self):
        answer = default_answerer(field(hidden=True), make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_sponsorship_question_picks_no(self):
        answer = default_answerer(field(
            field_id="sponsorship", label="Will you now or in the future require sponsorship?",
            kind="radio", options=[{"label": "Yes", "value": "yes"},
                                   {"label": "No", "value": "no"}]),
            make_profile(), {}, Trace())
        assert answer["display"] == "No"
        assert answer["value"] == "no"

    def test_without_sponsorship_question_inverts_needs_sponsorship_fact(self):
        question = field(
            field_id="sponsorship", label=(
                "Are you eligible to work in the United States without the aid "
                "of visa sponsorship, now or in the future?"),
            kind="radio", required=True,
            options=[{"label": "YES", "value": "true"},
                     {"label": "NO", "value": "false"}],
        )
        answer = default_answerer(question, make_profile(), {}, Trace())
        assert answer["value"] == "true"
        assert answer["display"] == "YES"

    def test_authorized_question_picks_yes(self):
        answer = default_answerer(field(
            field_id="authorized", label="Are you legally authorized to work in the US?",
            kind="radio", options=[{"label": "Yes", "value": "yes"},
                                   {"label": "No", "value": "no"}]),
            make_profile(), {}, Trace())
        assert answer["display"] == "Yes"

    def test_veteran_question_picks_decline(self):
        answer = default_answerer(field(
            field_id="veteran", label="Veteran Status",
            kind="radio", options=[{"label": "I am not a protected veteran", "value": "not"},
                                   {"label": "I am a veteran", "value": "yes"}]),
            make_profile(), {}, Trace())
        assert answer["display"] == "I am not a protected veteran"

    def test_how_did_you_hear_picks_job_board(self):
        # Job source questions are now auto-answered profile-direct.
        # "Job Board" matches our "job board" needle.
        answer = default_answerer(field(
            field_id="hear", label="How did you hear about us?",
            kind="select", options=[{"label": "Job Board", "value": "jb"},
                                    {"label": "Other", "value": "other"}]),
            make_profile(), {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "jb"

    def test_how_did_you_hear_picks_linkedin(self):
        # When LinkedIn is available it should be picked directly.
        answer = default_answerer(field(
            field_id="hear", label="How did you hear about us?",
            kind="select", options=[{"label": "Indeed", "value": "indeed"},
                                    {"label": "LinkedIn", "value": "linkedin"}]),
            make_profile(), {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "linkedin"

    def test_race_question_declines_not_profile_map(self):
        # Regression: "ethnicity" contains "city" — the EEO race/ethnicity
        # question must be answered with the decline option, NOT the profile
        # city (profile map is greedy substring matching).
        profile = make_profile()
        profile["personalInformation"]["city"] = "New York"
        answer = default_answerer(field(
            field_id="race", label="Race/Ethnicity",
            kind="select", options=[{"label": "Decline to self-identify", "value": "decline"},
                                    {"label": "White", "value": "white"}]),
            profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "decline"
        assert answer["display"] == "Decline to self-identify"

    def test_consent_checkbox_requires_review(self):
        answer = default_answerer(field(field_id="consent", label="I consent to the privacy policy",
                                        kind="checkbox"), make_profile(), {}, Trace())
        assert answer["value"] == ""
        assert answer["source"] == "skip"

    def test_consent_text_kind_requires_review(self):
        answer = default_answerer(field(field_id="privacy", label="Applicant Privacy Notice*",
                                        kind="text", required=True),
                                  make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_authorized_text_kind_answers_yes_not_country(self):
        # Live trace regression: a text-kind authorization question must be
        # answered "Yes", NOT with the profile country ("...the country to
        # which you are applying..." contains "country").
        answer = default_answerer(field(
            field_id="auth_q",
            label="Are you authorized to work lawfully in the country to which you are applying?",
            kind="text", required=True), make_profile(), {}, Trace())
        assert answer["value"] == "Yes"
        assert answer["display"] == "Yes"

    def test_sponsorship_text_kind_answers_no(self):
        answer = default_answerer(field(
            field_id="spon_q", label="Do you now or in the future require sponsorship?",
            kind="text", required=False), make_profile(), {}, Trace())
        assert answer["value"] == "No"

    def test_canada_authorization_is_not_inferred_from_us_profile(self):
        answer = default_answerer(field(
            field_id="auth_ca", label="Are you legally authorized to work in Canada?",
            kind="radio", required=True,
            options=[{"label": "Yes", "value": "yes"},
                     {"label": "No", "value": "no"}]), make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_how_did_you_hear_text_kind_uses_profile_value(self):
        profile = make_profile()
        profile["workPreferences"]["howDidYouHearAboutRole"] = "LinkedIn"
        answer = default_answerer(field(
            field_id="hear_q", label="How did you hear about this job?",
            kind="text", required=True), profile, {}, Trace())
        assert answer["value"] == "LinkedIn"
        assert answer["source"] == "profile-direct"

    def test_optional_transgender_text_skips_not_fallback(self):
        answer = default_answerer(field(
            field_id="trans_q", label="Do you personally identify as transgender?",
            kind="text", required=False), make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_unknown_question_falls_back_verbatim(self):
        answer = default_answerer(field(field_id="q_48372", label="What is your spirit animal?",
                                        kind="text"), make_profile(), {}, Trace())
        assert answer["source"] == "fallback"
        assert "Please refer to my resume" in answer["value"]

    def test_unknown_radio_requires_review(self):
        answer = default_answerer(field(
            field_id="q1", label="Some question", kind="radio",
            options=[{"label": "Alpha", "value": "a"}, {"label": "Beta", "value": "b"}]),
            make_profile(), {}, Trace())
        assert answer["source"] == "skip"
        assert answer["value"] == ""

    def test_answerer_never_raises_on_bad_field(self):
        answer = default_answerer({"no": "keys"}, None, None, Trace())
        assert isinstance(answer, dict)

    def test_notice_period_select_matching(self):
        profile = make_profile()
        profile["workPreferences"]["noticePeriod"] = "30 days"
        profile["workPreferences"]["noticePeriodDays"] = 30
        q = field(
            field_id="notice_period", label="Notice Period", kind="select",
            options=[{"label": "Immediate", "value": "0"},
                     {"label": "15 Days", "value": "15"},
                     {"label": "30 Days", "value": "30"},
                     {"label": "60 Days", "value": "60"}]
        )
        answer = default_answerer(q, profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "30"
        assert answer["display"] == "30 Days"

    def test_notice_period_number_days(self):
        profile = make_profile()
        profile["workPreferences"]["noticePeriod"] = "30 days"
        profile["workPreferences"]["noticePeriodDays"] = 30
        q = field(field_id="notice_days", label="Notice Period in Days", kind="number")
        answer = default_answerer(q, profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "30"

    def test_serving_notice_period_select(self):
        profile = make_profile()
        profile["workPreferences"]["servingNoticePeriod"] = False
        q = field(
            field_id="serving_notice", label="Are you currently serving notice period?", kind="select",
            options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}]
        )
        answer = default_answerer(q, profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "no"

    def test_current_and_expected_ctc(self):
        profile = make_profile()
        profile["workPreferences"]["currentCTC"] = "12 LPA"
        profile["workPreferences"]["expectedCTC"] = "18 LPA"

        # Current CTC text
        q_curr = field(field_id="current_ctc", label="Current CTC (in INR / LPA)")
        ans_curr = default_answerer(q_curr, profile, {}, Trace())
        assert ans_curr["source"] == "profile-direct"
        assert ans_curr["value"] == "12 LPA"

        # Expected CTC number in LPA
        q_exp_lpa = field(field_id="exp_ctc_lpa", label="Expected CTC in LPA", kind="number")
        ans_exp_lpa = default_answerer(q_exp_lpa, profile, {}, Trace())
        assert ans_exp_lpa["value"] == "18"

        # Expected CTC number in INR
        q_exp_inr = field(field_id="exp_ctc_inr", label="Expected CTC in INR (Annual)", kind="number")
        ans_exp_inr = default_answerer(q_exp_inr, profile, {}, Trace())
        assert ans_exp_inr["value"] == "1800000"

        # CTC bracket select
        q_bracket = field(
            field_id="ctc_range", label="Expected CTC Range", kind="select",
            options=[{"label": "10-14 LPA", "value": "1"},
                     {"label": "15-20 LPA", "value": "2"}]
        )
        ans_bracket = default_answerer(q_bracket, profile, {}, Trace())
        assert ans_bracket["value"] == "2"

    def test_preferred_location_matching(self):
        profile = make_profile()
        profile["workPreferences"]["preferredLocations"] = ["Bengaluru", "Hyderabad", "Pune"]
        q = field(
            field_id="pref_loc", label="Preferred Work Location", kind="select",
            options=[{"label": "Mumbai", "value": "mum"},
                     {"label": "Bengaluru", "value": "blr"},
                     {"label": "Noida", "value": "del"}]
        )
        answer = default_answerer(q, profile, {}, Trace())
        assert answer["source"] == "profile-direct"
        assert answer["value"] == "blr"
        assert answer["display"] == "Bengaluru"

    def test_work_from_office_and_shifts(self):
        profile = make_profile()
        q_wfo = field(field_id="wfo", label="Are you willing to work from office in Bengaluru?")
        ans_wfo = default_answerer(q_wfo, profile, {}, Trace())
        assert ans_wfo["value"] == "Yes"

        q_shift = field(field_id="shift", label="Are you comfortable with rotational shifts?")
        ans_shift = default_answerer(q_shift, profile, {}, Trace())
        assert ans_shift["value"] == "Yes"

    def test_india_work_auth_and_citizenship(self):
        profile = make_profile()
        profile["workAuthorization"]["workAuthorizations"].append({
            "countryCode": "IN", "isAuthorizedToWork": True, "needsSponsorship": False
        })
        profile["workAuthorization"]["citizenshipCountries"] = ["IN"]

        q_auth = field(field_id="in_auth", label="Are you legally authorized to work in India?")
        ans_auth = default_answerer(q_auth, profile, {}, Trace())
        assert ans_auth["value"] == "Yes"

        q_cit = field(field_id="in_cit", label="Are you an Indian citizen?")
        ans_cit = default_answerer(q_cit, profile, {}, Trace())
        assert ans_cit["value"] == "Yes"


class TestAnswerFields:
    def test_actions_and_trace_recorded(self):
        trace = Trace()
        fields = [
            field(field_id="first_name", label="First Name"),
            field(field_id="q1", label="Spirit animal", kind="radio",
                  options=[{"label": "Cat", "value": "cat"}]),
            field(field_id="consent", label="I consent", kind="checkbox"),
            field(field_id="hidden_q", label="Hidden", hidden=True),
        ]
        actions = answer_fields(fields, make_profile(), default_config(), trace)
        by_id = {a["field_id"]: a for a in actions}
        assert by_id["first_name"]["action"] == "fill"
        assert by_id["first_name"]["value"] == "Drupadh"
        assert by_id["q1"]["action"] == "none"
        assert by_id["consent"]["action"] == "none"
        assert by_id["hidden_q"]["action"] == "none"
        sources = trace.sources_summary()
        assert sources["profile-direct"] >= 1
        assert sources["skip"] == 3
        assert sources.get("fallback", 0) == 0

    def test_file_upload_action(self):
        trace = Trace()
        fields = [field(field_id="resume", label="Resume", kind="file")]
        actions = answer_fields(fields, make_profile(), default_config(), trace)
        assert actions[0]["action"] == "upload"

    def test_optional_additional_file_does_not_receive_the_resume(self):
        trace = Trace()
        fields = [field(field_id="candidate_file_remote_url",
                        label="Additional files", kind="file", required=False)]
        actions = answer_fields(fields, make_profile(), default_config(), trace)
        assert actions[0]["action"] == "none"
        assert actions[0]["source"] == "skip"
        assert actions[0]["document_kind"] == ""

    def test_international_phone_widget_preserves_country_code(self):
        element = FakeElement(
            attrs={"name": "candidate[phone]", "type": "tel",
                   "placeholder": "+33 6 12 34 56 78"},
        )
        frame = FakeFrame([element])
        actions = answer_fields(
            [field(field_id="candidate[phone]", label="Phone", kind="phone")],
            make_profile(), default_config(), Trace(),
        )
        summary = tsenta_apply._execute_actions(frame, actions, None)
        assert summary["filled"] == 1
        assert element.filled == "+15551234567"

    def test_paylocity_iso_start_date_is_typed_in_mask_format(self):
        class DateElement(FakeElement):
            def __init__(self):
                super().__init__(attrs={"id": "info.dateAvailableToStart",
                                        "type": "date"})
                self.typed = ""

            def press(self, _key):
                return None

            def type(self, value, delay=None):
                self.typed = value

            def input_value(self):
                if not self.typed:
                    return ""
                month, day, year = self.typed.split("/")
                return f"{year}-{month}-{day}"

        element = DateElement()
        action = {"field_id": "info.dateAvailableToStart", "action": "fill",
                  "value": "2026-09-15", "kind": "date", "required": True,
                  "source": "profile-direct", "display": "2026-09-15"}
        summary = tsenta_apply._execute_actions(FakeFrame([element]), [action], None)
        assert element.typed == "09/15/2026"
        assert summary["filled"] == 1
        assert summary["field_failures"] == []

    def test_month_input_accepts_profile_month_name(self):
        class MonthElement(FakeElement):
            def __init__(self):
                super().__init__(attrs={"id": "172-4-0", "type": "month"})

            def input_value(self):
                return self.filled or ""

        element = MonthElement()
        action = {"field_id": "172-4-0", "action": "fill",
                  "value": "Jul 2025", "kind": "month", "required": True,
                  "source": "profile-direct", "display": "Jul 2025"}
        summary = tsenta_apply._execute_actions(FakeFrame([element]), [action], None)
        assert element.filled == "2025-07"
        assert summary["filled"] == 1
        assert summary["field_failures"] == []

    def test_react_radio_rerender_is_verified_with_fresh_name_and_value(self):
        class DetachedRadio(FakeElement):
            def check(self, timeout=None):
                self._checked = True
                raise RuntimeError("node detached after controlled update")

        class FreshRadioFrame(FakeFrame):
            def query_selector(self, selector):
                if "input[type='radio']" in selector and "value='Other'" in selector:
                    return self.elements[1]
                return super().query_selector(selector)

        detached = DetachedRadio(attrs={
            "name": "info.howDidYouHearAboutUs", "type": "radio", "value": "Other",
        })
        fresh = FakeElement(attrs={
            "name": "info.howDidYouHearAboutUs", "type": "radio", "value": "Other",
        }, checked=True)
        assert tsenta_apply._click_radio(
            FreshRadioFrame([detached, fresh]), [detached], "Other") is True

    def test_ashby_system_field_uses_live_locator_after_dom_rerender(self):
        class DetachedInput(FakeElement):
            def fill(self, _value):
                raise RuntimeError("ElementHandle.fill: Element is not attached to the DOM")

        class LiveLocator(FakeElement):
            @property
            def first(self):
                return self

            def count(self):
                return 1

            def input_value(self):
                return self.filled or ""

        class AshbyFrame(FakeFrame):
            def __init__(self, stale, live):
                super().__init__([stale])
                self.live = live
                self.locator_selector = ""

            def locator(self, selector):
                self.locator_selector = selector
                return self.live

        stale = DetachedInput(attrs={"id": "_systemfield_name", "type": "text"})
        live = LiveLocator(attrs={"id": "_systemfield_name", "type": "text"})
        frame = AshbyFrame(stale, live)
        action = {
            "field_id": "_systemfield_name", "action": "fill",
            "value": "Drupadh Suresh", "kind": "text", "required": True,
            "source": "profile-direct", "display": "Drupadh Suresh",
        }

        summary = tsenta_apply._execute_actions(frame, [action], None)

        assert live.filled == "Drupadh Suresh"
        assert stale.filled is None
        assert "input[id='_systemfield_name']" in frame.locator_selector
        assert summary["filled"] == 1
        assert summary["field_failures"] == []
        assert summary["verified_fields"] == ["_systemfield_name"]

    def test_invalid_answerer_output_is_skip(self):
        trace = Trace()
        fields = [field(field_id="q1", label="Q")]
        actions = answer_fields(fields, make_profile(), default_config(), trace,
                                answerer=lambda *a: "not a dict")
        assert actions[0]["action"] == "none"
        assert trace.answers[0]["source"] == "skip"

    def test_missing_numeric_profile_value_is_never_filled_with_text_fallback(self):
        trace = Trace()
        fields = [field(field_id="salary", label="Salary expectation",
                        kind="number", required=True)]
        actions = answer_fields(fields, make_profile(), default_config(), trace)
        assert actions[0]["action"] == "none"
        assert actions[0]["source"] == "skip"
        assert trace.answers[0]["reason"] == "Numeric response is not in the profile"


class TestCollectFields:
    def test_owned_custom_select_only_reads_its_own_listbox_options(self):
        control = FakeElement(attrs={
            "id": "candidate_country",
            "type": "search",
            "role": "combobox",
            "aria-controls": "candidate_country_list",
        })
        owned = FakeElement(tag="div", attrs={
            "id": "candidate_country_list_0", "role": "option",
        }, text="United States")
        unrelated = FakeElement(tag="div", attrs={
            "id": "other_list_0", "role": "option",
        }, text="Unrelated")

        class OwnedListFrame(FakeFrame):
            def query_selector_all(self, selector):
                self._calls.append(("query_selector_all", selector))
                return [owned] if "candidate_country_list" in selector else [unrelated]

        frame = OwnedListFrame()
        options = tsenta_apply._options_for(frame, control, "select")
        assert options == [{"label": "United States", "value": "United States"}]
        assert any(call[0] == "query_selector_all"
                   and "candidate_country_list" in call[1]
                   for call in frame._calls)

    def test_paylocity_screener_textarea_uses_parent_question_copy(self):
        class ScreenerTextarea(FakeElement):
            def evaluate(self, expression):
                if "parentElement?.innerText" in expression:
                    return "What makes you qualified for this position? (required)"
                if "ownerDocument" in expression:
                    return ""
                return super().evaluate(expression)

        element = ScreenerTextarea(tag="textarea", attrs={
            "id": "screener-question-1-textarea",
        })
        assert tsenta_apply._label_for(
            FakeFrame([element]), element, element.get_attribute("id"), ""
        ) == "What makes you qualified for this position? (required)"

    @pytest.mark.parametrize(("suffix", "expected_label"), [
        ("__systemfield_eeoc_gender", "Gender"),
        ("__systemfield_eeoc_race", "Race / ethnicity"),
        ("__systemfield_eeoc_veteran_status", "Veteran status"),
        ("__systemfield_eeoc_disability_status", "Disability status"),
    ])
    def test_ashby_eeo_groups_use_question_labels(self, suffix, expected_label):
        field_id = "question-uuid" + suffix
        elements = [
            FakeElement(attrs={"name": field_id, "type": "radio", "value": "Yes",
                               "aria-label": "Yes"}),
            FakeElement(attrs={"name": field_id, "type": "radio", "value": "Decline",
                               "aria-label": "Decline to self-identify"}),
        ]

        fields = collect_fields(FakeFrame(elements), max_passes=1, timeout_ms=1)

        assert len(fields) == 1
        assert fields[0]["label"] == expected_label
        answer = default_answerer(fields[0], make_profile(), default_config(), Trace())
        assert answer["source"] == "profile-direct"
        assert answer["display"] == "Decline to self-identify"

    def test_brassring_privacy_button_becomes_required_review_checkbox(self):
        element = FakeElement(tag="button", attrs={
            "data-nori-field": "brassring-privacy-consent",
            "aria-label": "Agree to Privacy Policy",
            "aria-required": "true",
        })
        fields = collect_fields(FakeFrame([element]), max_passes=1, timeout_ms=1)
        assert fields[0]["field_id"] == "brassring-privacy-consent"
        assert fields[0]["kind"] == "checkbox"
        assert fields[0]["required"] is True
        answer = default_answerer(fields[0], make_profile(), default_config(), Trace())
        assert answer["source"] == "skip"
        assert "Consent" in answer["reason"]

    def test_dayforce_vendor_test_id_is_stable_and_privacy_is_required(self):
        element = FakeElement(
            attrs={"type": "checkbox",
                   "test-id": "client-privacy-policy-modal-agree-checkbox",
                   "aria-label": "I agree to the Privacy Statement"},
        )
        fields = collect_fields(FakeFrame([element]), max_passes=1, timeout_ms=1)
        assert fields[0]["field_id"] == "client-privacy-policy-modal-agree-checkbox"
        assert fields[0]["kind"] == "checkbox"
        assert fields[0]["required"] is True

    def test_label_star_marks_required_when_html_attribute_is_missing(self):
        element = FakeElement(attrs={
            "type": "text", "name": "resumator-firstname-value",
            "aria-label": "First Name*",
        })
        fields = collect_fields(FakeFrame([element]), max_passes=1, timeout_ms=1)
        assert fields[0]["required"] is True

    def test_collects_visible_fields_only(self):
        elements = [
            el_text_input("first_name", required=True),
            el_text_input("hidden_field", visible=False),
            el_select("country", [("US", "us")]),
        ]
        fields = collect_fields(FakeFrame(elements))
        by_id = {f["field_id"]: f for f in fields}
        assert by_id["first_name"]["required"] is True
        assert by_id["first_name"]["hidden"] is False
        assert by_id["hidden_field"]["hidden"] is True
        assert by_id["country"]["kind"] == "select"
        assert by_id["country"]["options"] == [{"label": "US", "value": "us"}]

    def test_radio_group_same_name_single_field(self):
        elements = [
            el_radio("authorized", "yes", "Yes"),
            el_radio("authorized", "no", "No"),
            el_radio("authorized", "maybe", "Maybe"),
        ]
        fields = collect_fields(FakeFrame(elements))
        radios = [f for f in fields if f["kind"] == "radio"]
        assert len(radios) == 1
        assert radios[0]["field_id"] == "authorized"
        assert [o["label"] for o in radios[0]["options"]] == ["Yes", "No", "Maybe"]

    def test_nearby_question_heading_labels_breezy_textarea(self):
        element = NearbyQuestionElement(
            tag="textarea",
            attrs={"name": "section__question_0", "required": "required"},
            nearby_label="Please provide your physical mailing address *",
        )
        fields = collect_fields(FakeFrame([element]), max_passes=1, timeout_ms=1)
        assert fields[0]["label"] == "Please provide your physical mailing address *"
        assert fields[0]["required"] is True

    def test_nearby_question_heading_labels_breezy_radio_group(self):
        elements = [
            NearbyQuestionElement(
                attrs={"name": "section__question_4", "type": "radio",
                       "value": "yes", "aria-label": "Yes"},
                nearby_label="Are you a U.S. citizen? *",
            ),
            NearbyQuestionElement(
                attrs={"name": "section__question_4", "type": "radio",
                       "value": "no", "aria-label": "No"},
                nearby_label="Are you a U.S. citizen? *",
            ),
        ]
        fields = collect_fields(FakeFrame(elements), max_passes=1, timeout_ms=1)
        assert len(fields) == 1
        assert fields[0]["label"] == "Are you a U.S. citizen? *"
        assert fields[0]["options"] == [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ]

    def test_same_name_checkboxes_become_one_reviewable_choice_group(self):
        elements = [
            NearbyQuestionElement(
                attrs={"name": "candidate.openQuestionAnswers.10.multiContent",
                       "type": "checkbox", "value": "Linkedin",
                       "aria-label": "Linkedin", "required": "required"},
                nearby_label="Where did you hear about us? *",
            ),
            NearbyQuestionElement(
                attrs={"name": "candidate.openQuestionAnswers.10.multiContent",
                       "type": "checkbox", "value": "Careers Page",
                       "aria-label": "Careers Page", "required": "required"},
                nearby_label="Where did you hear about us? *",
            ),
        ]
        frame = FakeFrame(elements)
        fields = collect_fields(frame, max_passes=1, timeout_ms=1)
        assert len(fields) == 1
        assert fields[0]["kind"] == "checkbox_group"
        assert fields[0]["label"] == "Where did you hear about us? *"
        assert fields[0]["options"] == [
            {"label": "Linkedin", "value": "Linkedin"},
            {"label": "Careers Page", "value": "Careers Page"},
        ]

        trace = Trace()
        actions = answer_fields(
            fields, make_profile(), default_config(), trace,
            answerer=lambda *_args: {"value": "Careers Page", "source": "llm",
                                     "display": "Careers Page"},
        )
        summary = tsenta_apply._execute_actions(frame, actions, None)
        assert actions[0]["action"] == "select"
        assert elements[0].is_checked() is False
        assert elements[1].is_checked() is True
        assert summary["selected"] == 1

    def test_recruitee_phone_country_id_is_stable_and_uses_profile_country(self):
        element = FakeElement(
            tag="button",
            attrs={"id": "country-select-input-candidate.phone-undefined",
                   "aria-haspopup": "listbox",
                   "aria-label": "Select country calling code: Spain"},
        )
        fields = collect_fields(FakeFrame([element]), max_passes=1, timeout_ms=1)
        assert fields[0]["field_id"] == "candidate.phone.country"
        assert fields[0]["kind"] == "select"
        answer = default_answerer(fields[0], make_profile(), default_config(), Trace())
        assert answer["value"] == "United States"
        assert answer["source"] == "profile-direct"

    def test_never_raises_on_empty(self):
        assert collect_fields(FakeFrame([])) == []


class TestApplyJobDryRun:
    def test_dry_run_with_resume_uploads_file(self):
        elements = [
            el_text_input("first_name", required=True),
            el_file("resume", required=True),
        ]
        page = FakePage(elements)
        result = json.loads(apply_job("https://jobs.lever.co/company/role-123",
                                      make_profile(), dry_run=True,
                                      resume_path="C:/resume.pdf",
                                      _page_provider=lambda: page))
        assert result["ok"] is True
        assert result["answers_summary"]["uploaded"] == 1
        assert result["answers_summary"]["missing_uploads"] == []
        # the resume element received the file
        resume_el = [e for e in page.query_selector_all("input")
                     if e.get_attribute("name") == "resume"][0]
        assert resume_el.filled == "C:/resume.pdf"

    def test_resume_is_not_substituted_for_cover_letter(self):
        elements = [
            el_file("resume", required=True),
            el_file("cover_letter", required=False),
        ]
        page = FakePage(elements)
        result = json.loads(apply_job(
            "https://jobs.lever.co/company/role-123", make_profile(),
            dry_run=True, resume_path="C:/tailored-resume.pdf",
            _page_provider=lambda: page))
        assert result["answers_summary"]["uploaded"] == 1
        assert result["answers_summary"]["uploaded_documents"][0]["kind"] == "resume"
        by_name = {e.get_attribute("name"): e for e in page.query_selector_all("input")}
        assert by_name["resume"].filled == "C:/tailored-resume.pdf"
        assert by_name["cover_letter"].filled is None

    def test_resume_and_cover_letter_use_distinct_pdf_paths(self):
        elements = [
            el_file("resume", required=True),
            el_file("cover_letter", required=False),
        ]
        page = FakePage(elements)
        result = json.loads(apply_job(
            "https://jobs.lever.co/company/role-123", make_profile(),
            dry_run=True, resume_path="C:/tailored-resume.pdf",
            cover_letter_path="C:/cover-letter.pdf",
            _page_provider=lambda: page))
        uploads = result["answers_summary"]["uploaded_documents"]
        assert result["answers_summary"]["uploaded"] == 2
        assert {item["kind"] for item in uploads} == {"resume", "cover_letter"}
        by_name = {e.get_attribute("name"): e for e in page.query_selector_all("input")}
        assert by_name["resume"].filled == "C:/tailored-resume.pdf"
        assert by_name["cover_letter"].filled == "C:/cover-letter.pdf"

    def test_dry_run_without_resume_flags_required_upload(self):
        elements = [
            el_text_input("first_name", required=True),
            el_file("resume", required=True),
        ]
        page = FakePage(elements)
        result = json.loads(apply_job("https://jobs.lever.co/company/role-123",
                                      make_profile(), dry_run=True,
                                      _page_provider=lambda: page))
        assert result["ok"] is True  # dry-run still succeeds
        assert result["answers_summary"]["missing_uploads"] == ["resume"]

    def test_submit_without_resume_guard_blocks_submission(self):
        elements = [
            el_text_input("first_name", required=True),
            el_file("resume", required=True),
        ]
        page = FakePage(elements)
        result = json.loads(apply_job("https://jobs.lever.co/company/role-123",
                                      make_profile(), dry_run=False, confirmed=True,
                                      _page_provider=lambda: page))
        assert result["ok"] is False
        assert result["submitted"] is False
        assert result["error"] == "resume-missing"
        assert result["trace"]["meta"]["outcome"] == "failed"

    def test_submit_without_resume_guard_never_clicks_submit(self):
        submit = FakeElement(tag="button", attrs={"type": "submit"}, visible=True)
        elements = [
            el_text_input("first_name", required=True),
            el_file("resume", required=True),
            submit,
        ]
        page = FakePage(elements)
        result = json.loads(apply_job("https://jobs.lever.co/company/role-123",
                                      make_profile(), dry_run=False, confirmed=True,
                                      _page_provider=lambda: page))
        assert result["ok"] is False
        assert submit.clicked is False  # guard tripped BEFORE _submit

    def test_dry_run_full_flow_never_submits(self):
        elements = [
            el_text_input("first_name", required=True),
            el_text_input("email"),
            el_radio("sponsorship", "no", "No"),
            el_radio("sponsorship", "yes", "Yes"),
            el_file("resume"),
        ]
        page = FakePage(elements)

        def provider():
            return page

        result = json.loads(apply_job("https://jobs.lever.co/company/role-123",
                                      make_profile(), dry_run=True,
                                      resume_path="C:/resume.pdf",
                                      _page_provider=provider))
        assert result["ok"] is True
        assert result["ats"] == "lever"
        assert result["dry_run"] is True
        assert result["submitted"] is False
        assert result["sources"]["profile-direct"] >= 2
        assert result["trace"]["meta"]["outcome"] == "dry-run"

    def test_submit_without_confirmation_forced_to_dry_run(self):
        page = FakePage([el_text_input("first_name")])
        result = json.loads(apply_job("https://jobs.lever.co/company/role-123",
                                      make_profile(), dry_run=False, confirmed=False,
                                      _page_provider=lambda: page))
        assert result["dry_run"] is True
        assert result["submitted"] is False

    def test_unknown_ats_returns_error(self):
        page = FakePage([])
        result = json.loads(apply_job("https://www.google.com", make_profile(),
                                      _page_provider=lambda: page))
        assert result["ok"] is False
        assert result["error"] == "ats-not-detected"

    def test_known_feed_hint_enables_a_branded_career_domain(self):
        page = FakePage([el_text_input("firstName", required=True)])
        result = json.loads(apply_job(
            "https://careers.example.test/jobs/42", make_profile(),
            dry_run=True, ats_hint="paycom", _page_provider=lambda: page))
        assert result["ok"] is True
        assert result["ats"] == "paycom"
        assert result["submitted"] is False

    def test_unknown_feed_hint_cannot_bypass_detection(self):
        result = json.loads(apply_job(
            "https://careers.example.test/jobs/42", make_profile(),
            ats_hint="invented-system", _page_provider=lambda: FakePage([])))
        assert result["error"] == "ats-not-detected"

    def test_result_is_always_valid_json(self):
        result = apply_job("https://jobs.lever.co/company/role-123", None,
                           _page_provider=lambda: FakePage([]))
        assert isinstance(json.loads(result), dict)


class TestSubmit:
    def test_submit_clicks_and_confirms(self):
        submit = FakeElement(tag="button", attrs={"type": "submit"}, visible=True)
        frame = FakeFrame([submit])

        class PageWithConfirm(FakeFrame):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.confirm_seen = False

            def wait_for_selector(self, selector, timeout=None):
                if "thank you" in selector.lower() or "submitted" in selector.lower():
                    self.confirm_seen = True
                    return True
                return None

        page = PageWithConfirm([submit])
        page.frames = [page]
        submitted = tsenta_apply._submit(page, 5000)
        assert submitted is True
        assert tsenta_apply._confirm_submission(page, 5000) is True

    def test_no_submit_control_returns_false(self):
        assert tsenta_apply._submit(FakeFrame([]), 5000) is False


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveGreenhouse:
    def test_boards_api_and_dry_run_walk(self):
        """Live: fetch an open Greenhouse job, walk its form in dry-run."""
        import urllib.request

        with urllib.request.urlopen(
            "https://boards-api.greenhouse.io/v1/boards/mozilla/jobs", timeout=30
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        jobs = data.get("jobs", [])
        assert jobs, "no open jobs on the mozilla board"
        job = jobs[0]
        url = f"https://boards.greenhouse.io/mozilla/jobs/{job['id']}"

        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ok"] is True
        assert result["ats"] == "greenhouse"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveWorkday:
    def test_boards_api_and_dry_run_walk(self):
        """Live: open a Workday posting and walk its apply wizard in dry-run.

        Workday boards are client-side SPAs, so a posting URL is found by
        launching the browser on the board home and reading the first job
        link. If every known board is unreachable (Workday-wide outage), the
        test skips instead of failing.
        """
        import time
        import urllib.error
        import urllib.request

        from playwright.sync_api import sync_playwright

        boards = [
            "https://paypal.wd1.myworkdayjobs.com/en-US/jobs",
            "https://workday.wd5.myworkdayjobs.com/Workday/",
            "https://usbank.wd1.myworkdayjobs.com/US_Bank_Careers",
            "https://collegeboard.wd1.myworkdayjobs.com/Careers",
            "https://mpc.wd1.myworkdayjobs.com/MPCCareers",
            "https://mymvw.wd5.myworkdayjobs.com/mvw/",
            "https://kla.wd1.myworkdayjobs.com/en-US/Search",
        ]
        reachable = []
        for board in boards:
            try:
                req = urllib.request.Request(board,
                                             headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=20)
                if resp.status == 200:
                    reachable.append(board)
            except Exception:
                continue
        if not reachable:
            pytest.skip("all workday career boards unreachable (outage)")

        posting_urls = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                for board in reachable:
                    try:
                        page.goto(board, wait_until="domcontentloaded", timeout=45000)
                        link = page.wait_for_selector(
                            "a[href*='/job/'], a[data-automation-id='jobPostingLink']",
                            timeout=20000)
                        href = link.get_attribute("href") or ""
                        if href.startswith("/"):
                            href = board.rstrip("/") + href
                        if href.startswith("http"):
                            posting_urls.append(href)
                    except Exception:
                        continue
            finally:
                browser.close()
        if not posting_urls:
            pytest.skip("no job posting link found on reachable workday boards")

        # Try each board's first posting until the wizard actually walks
        # (Cloudflare-protected tenants block some postings' apply flows).
        walked = None
        for candidate in posting_urls:
            result = json.loads(apply_job(candidate, make_profile(), dry_run=True))
            if result.get("trace", {}).get("answers"):
                walked = result
                break
        if walked is None:
            pytest.skip("workday apply wizard blocked by bot protection "
                        "on all reachable boards")
        result = walked
        assert result["ok"] is True
        assert result["ats"] == "workday"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveOtherATS:
    def test_ashby_dry_run_walk(self):
        """Live: find an open posting on an Ashby board and walk its apply
        form in dry-run. Skips when no board renders job links.
        """
        from playwright.sync_api import sync_playwright

        boards = [
            "https://jobs.ashbyhq.com/notion",
            "https://jobs.ashbyhq.com/openai",
            "https://jobs.ashbyhq.com/linear",
        ]
        posting_url = None
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(30000)
            try:
                for board in boards:
                    try:
                        page.goto(board, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(5000)
                        hrefs = page.eval_on_selector_all(
                            "a",
                            "els => els.map(e => e.href).filter(h => h && "
                            "h.includes('jobs.ashbyhq.com/') && h !== " +
                            json.dumps(board) + " && !h.endsWith('/'))")
                        if hrefs:
                            posting_url = hrefs[0]
                            break
                    except Exception:
                        continue
            finally:
                browser.close()
        if not posting_url:
            pytest.skip("no ashby board rendered job links")

        result = json.loads(apply_job(posting_url, make_profile(), dry_run=True))
        assert result["ok"] is True
        assert result["ats"] == "ashby"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveLever:
    def test_boards_api_and_dry_run_walk(self):
        """Live: fetch an open Lever posting, walk its /apply form in dry-run."""
        import urllib.request

        # "leverdemo" is Lever's always-populated public demo board.
        with urllib.request.urlopen(
            "https://api.lever.co/v0/postings/leverdemo?mode=json", timeout=30
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        jobs = data.get("data", []) if isinstance(data, dict) else (data or [])
        assert jobs, "no open postings on the lever demo board"
        job = jobs[0]
        url = f"https://jobs.lever.co/leverdemo/{job['id']}/apply"

        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ok"] is True, result
        assert result["ats"] == "lever"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveICIMS:
    """Live iCIMS dry-run walk against a real public posting."""

    def test_icims_dry_run_walk(self):
        """Live: navigate an iCIMS posting and walk the form in dry-run."""
        from playwright.sync_api import sync_playwright

        posting_url = None
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto("https://careers-peraton.icims.com/jobs/search",
                          wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                for frame in page.frames:
                    links = frame.query_selector_all(
                        "a.iCIMS_Anchor[href*='/jobs/'][href*='/job']")
                    if links:
                        posting_url = links[0].get_attribute("href")
                        break
            finally:
                browser.close()
        if not posting_url:
            pytest.skip("no current iCIMS posting found on public board")

        result = json.loads(apply_job(posting_url, make_profile(), dry_run=True))
        assert result["ok"] is True, result
        assert result["ats"] == "icims"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveSmartRecruiters:
    """Live SmartRecruiters dry-run walk against a real public posting."""

    def test_smartrecruiters_dry_run_walk(self):
        """Live: resolve a current OneClick form or report its human challenge."""
        import urllib.request

        with urllib.request.urlopen(
            "https://api.smartrecruiters.com/v1/companies/"
            "JackLinksProteinSnacks/postings?limit=5", timeout=30,
        ) as response:
            jobs = json.loads(response.read().decode("utf-8")).get("content", [])
        if not jobs:
            pytest.skip("no current SmartRecruiters postings found")
        url = ("https://jobs.smartrecruiters.com/JackLinksProteinSnacks/"
               + str(jobs[0]["id"]))
        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ats"] == "smartrecruiters"
        assert result["submitted"] is False
        if result["ok"]:
            assert result["trace"]["meta"]["outcome"] == "dry-run"
            assert len(result["trace"]["answers"]) > 0
        else:
            assert result["error"] == "smartrecruiters-human-challenge-required"


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveJazzHR:
    """Live JazzHR dry-run walk against a real public posting."""

    def test_jazzhr_dry_run_walk(self):
        """Live: navigate a JazzHR posting and walk the form in dry-run."""
        from playwright.sync_api import sync_playwright

        url = None
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto("https://phoenixcybersecurity.applytojob.com/",
                          wait_until="domcontentloaded", timeout=45000)
                links = page.query_selector_all(
                    "a[href*='phoenixcybersecurity.applytojob.com/apply/']")
                for link in links:
                    href = link.get_attribute("href") or ""
                    if len([part for part in href.split("/") if part]) >= 4:
                        url = href
                        break
            finally:
                browser.close()
        if not url:
            pytest.skip("no current JazzHR posting found on public board")
        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ok"] is True, result
        assert result["ats"] == "jazzhr"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveWorkable:
    """Live Workable dry-run walk against a current public posting."""

    def test_workable_dry_run_walk(self):
        """Live: discover a Workable posting and walk its form without submit."""
        from playwright.sync_api import sync_playwright

        url = None
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto("https://apply.workable.com/appgate/",
                          wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                links = page.query_selector_all("a[href*='/appgate/j/']")
                for link in links:
                    href = link.get_attribute("href") or ""
                    if "/appgate/j/" in href and "/apply/" not in href:
                        from urllib.parse import urljoin
                        url = urljoin("https://apply.workable.com/appgate/", href)
                        break
            finally:
                browser.close()
        if not url:
            pytest.skip("no current Workable posting found on public board")
        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ok"] is True, result
        assert result["ats"] == "workable"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveBambooHR:
    """Live BambooHR dry-run walk against a current public posting."""

    def test_bamboohr_dry_run_walk(self):
        """Live: discover an R2 BambooHR posting and walk its application modal."""
        import urllib.request

        request = urllib.request.Request(
            "https://r2.bamboohr.com/careers/list",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            jobs = json.loads(response.read().decode("utf-8")).get("result", [])
        if not jobs:
            pytest.skip("no current BambooHR posting found on public board")
        url = "https://r2.bamboohr.com/careers/" + str(jobs[0]["id"])
        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ok"] is True, result
        assert result["ats"] == "bamboohr"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveRippling:
    """Live Rippling dry-run walk against a current public posting."""

    def test_rippling_dry_run_walk(self):
        """Walk a public Rippling application form without submitting."""
        url = ("https://ats.rippling.com/rhodiangroup/jobs/"
               "0353172b-714f-4129-b669-f5007a704fc1")
        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ok"] is True, result
        assert result["ats"] == "rippling"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert len(result["trace"]["answers"]) > 0


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="live browser test: set LIVE=1")
class TestLiveOracleCloud:
    """Live Oracle Candidate Experience preflight without consent or submit."""

    def test_oraclecloud_preflight_stops_at_consent(self):
        """Fill the email-first step and leave legal consent for review."""
        url = ("https://egug.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
               "en/sites/CX/job/26013352")
        result = json.loads(apply_job(url, make_profile(), dry_run=True))
        assert result["ok"] is True, result
        assert result["ats"] == "oraclecloud"
        assert result["submitted"] is False
        assert result["trace"]["meta"]["outcome"] == "dry-run"
        assert "legal-disclaimer-checkbox" in result["error"]


class TestStealth:
    """Unit tests for anti-bot stealth and challenge detection."""

    def test_apply_stealth(self):
        """_apply_stealth patches init script and viewport (no-op test)."""
        page = FakePage()
        tsenta_apply._apply_stealth(page)
        assert True  # no exception raised

    def test_is_bot_challenged_no_challenge(self):
        """Clean page returns False."""
        class CleanPage:
            def content(self):
                return "<html><body>Welcome</body></html>"
            class Context:
                def cookies(self):
                    return []
            context = Context()
        assert tsenta_apply._is_bot_challenged(CleanPage()) is False

    def test_is_bot_challenged_cloudflare_turnstile(self):
        """Page with cf-turnstile returns True."""
        class ChallengedPage:
            def content(self):
                return '<html><div class="cf-turnstile"></div></html>'
            class Context:
                def cookies(self):
                    return []
            context = Context()
        assert tsenta_apply._is_bot_challenged(ChallengedPage()) is True

    def test_is_bot_challenged_just_a_moment(self):
        """Page with 'just a moment' signal returns True."""
        class ChallengedPage:
            def content(self):
                return '<html><body>Checking your browser before accessing...</body></html>'
            class Context:
                def cookies(self):
                    return []
            context = Context()
        assert tsenta_apply._is_bot_challenged(ChallengedPage()) is True

    def test_cf_bot_management_cookie_alone_is_not_a_challenge(self):
        """A normal __cf_bm cookie does not mean the page is blocked."""
        class ChallengedPage:
            def content(self):
                return "<html><body>OK</body></html>"
            class Context:
                def cookies(self):
                    return [{"name": "__cf_bm", "value": "abc123"}]
            context = Context()
        assert tsenta_apply._is_bot_challenged(ChallengedPage()) is False

    def test_is_bot_challenged_hcaptcha(self):
        """Page with h-captcha returns True."""
        class ChallengedPage:
            def content(self):
                return '<html><div class="h-captcha"></div></html>'
            class Context:
                def cookies(self):
                    return []
            context = Context()
        assert tsenta_apply._is_bot_challenged(ChallengedPage()) is True

    def test_inline_hcaptcha_on_application_form_is_a_review_blocker(self):
        class ApplicationPage:
            def content(self):
                return '<form action="/apply"><input type="email"><div class="h-captcha"></div></form>'
            def query_selector(self, selector):
                if "input[type='email']" in selector or ".h-captcha" in selector:
                    return object()
                return None
            class Context:
                def cookies(self):
                    return []
            context = Context()
        page = ApplicationPage()
        assert tsenta_apply._is_bot_challenged(page) is False
        assert tsenta_apply._application_captcha_present(page) is True

    def test_captcha_library_text_without_widget_is_not_a_review_blocker(self):
        class ApplicationPage:
            def content(self):
                return ('<script>const recaptcha = "loaded when needed";</script>'
                        '<form><input name="firstname"><input type="email"></form>')
            def query_selector(self, selector):
                if "input[type='email']" in selector:
                    return object()
                return None
            frames = []
        assert tsenta_apply._application_captcha_present(ApplicationPage()) is False

    def test_hidden_captcha_enclave_is_not_an_active_challenge(self):
        class HiddenWidget:
            def is_visible(self):
                return False
        class HiddenFrame:
            url = "https://captcha.example/hcaptcha-enclave.html"
            def frame_element(self):
                return HiddenWidget()
        class ApplicationPage:
            def query_selector(self, selector):
                if "input[type='email']" in selector:
                    return object()
                if "iframe[src*='hcaptcha'" in selector:
                    return HiddenWidget()
                return None
            frames = [HiddenFrame()]
        assert tsenta_apply._application_captcha_present(ApplicationPage()) is False

    def test_challenge_library_name_inside_real_application_is_not_full_page_block(self):
        class ApplicationPage:
            def content(self):
                return ('<script src="/challenge-platform.js"></script>'
                        '<form><input name="firstname"><input type="email"></form>')
            def query_selector(self, selector):
                return object()
            class Context:
                def cookies(self):
                    return []
            context = Context()
            frames = []
        assert tsenta_apply._is_bot_challenged(ApplicationPage()) is False

    def test_dayforce_compact_firstname_id_marks_real_application_surface(self):
        class DayforceApplicationPage:
            def content(self):
                return ('<script src="/challenge-platform.js"></script>'
                        '<input test-id="personal-info-firstname-text-input">')
            def query_selector(self, selector):
                if "test-id*='firstname'" in selector:
                    return object()
                return None
            class Context:
                def cookies(self):
                    return []
            context = Context()
            frames = []
        assert tsenta_apply._is_bot_challenged(DayforceApplicationPage()) is False

    def test_human_delay_waits(self):
        """_human_delay waits at least min_ms (no-op mock)."""
        page = FakePage()
        tsenta_apply._human_delay(page, min_ms=1, max_ms=5)
        assert True  # no exception raised

    def test_open_form_raises_on_challenge(self):
        """_open_form raises bot-challenge-detected when page is challenged."""

        class ChallengePage(FakeFrame):
            def __init__(self):
                FakeFrame.__init__(self)
                self._challenged = True
                self.goto_calls = 0
                self.closed = False

            def goto(self, url, **kwargs):
                self.goto_calls += 1
                self.url = url

            def content(self):
                return '<html><div class="cf-turnstile"></div></html>'

            def wait_for_selector(self, *a, **kw):
                pass

            class Context:
                def cookies(self):
                    return []

            context = Context()

            @property
            def frames(self):
                return [self]

        page = ChallengePage()
        import pytest as _pytest
        with _pytest.raises(Exception) as exc:
            tsenta_apply._open_form(page, "https://example.com/jobs/123", "unknown", 45000)
        assert "bot-challenge" in str(exc.value) or "bot-challenge" in str(type(exc.value))

    def test_apply_job_stealth_param_passthrough(self):
        """apply_job accepts stealth=False and still works (dry-run)."""
        result = json.loads(tsenta_apply.apply_job(
            "https://example.com/jobs/123",
            make_profile(), dry_run=True, stealth=False))
        assert result["ok"] is False  # unknown ATS
        assert result["ats"] == "unknown"

    def test_default_answerer_recalls_from_persistent_memory(self, tmp_path):
        """Custom reviewed questions stored in persistent memory are recalled immediately."""
        from backend.src.tools.tsenta_memory import remember_answer
        mem_file = str(tmp_path / "test_memory.json")
        remember_answer(
            label="What is your favorite cloud infrastructure tool?",
            value="Terraform",
            kind="text",
            path=mem_file,
        )
        import os
        os.environ["TSENTA_MEMORY_PATH"] = mem_file
        try:
            f = field(field_id="custom_q1", label="What is your favorite cloud infrastructure tool?", kind="text")
            trace = Trace()
            ans = default_answerer(f, make_profile(), default_config(), trace)
            assert ans["source"] == "user-memory"
            assert ans["value"] == "Terraform"
        finally:
            os.environ.pop("TSENTA_MEMORY_PATH", None)

    def test_default_answerer_alternate_legal_name(self):
        """Alternate legal name questions return None with profile-direct source."""
        f = field(field_id="q_alt_name", label="Legal Name (if different than above)", kind="text")
        trace = Trace()
        ans = default_answerer(f, make_profile(), default_config(), trace)
        assert ans["source"] == "profile-direct"
        assert ans["value"] == "None"

    def test_default_answerer_compound_location(self):
        """Compound questions requesting city, state, and country format as full location."""
        p = make_profile()
        p["personalInformation"]["city"] = "Austin"
        p["personalInformation"]["state"] = "TX"
        p["personalInformation"]["country"] = "United States"
        f = field(field_id="q_loc", label="Please indicate your current city, state, and country", kind="text")
        trace = Trace()
        ans = default_answerer(f, p, default_config(), trace)
        assert ans["source"] == "profile-direct"
        assert ans["value"] == "Austin, TX, United States"

    def test_default_answerer_relocation_hub(self):
        """Hub relocation questions pick affirmative relocation choice."""
        options = [
            {"label": "I currently live in this job's location.", "value": "1"},
            {"label": "I am willing to relocate to this job's location.", "value": "2"},
            {"label": "I do not live and not willing to relocate to this job's location.", "value": "3"}
        ]
        f = field(field_id="q_reloc", label="Are you currently located in one of the hub locations or willing to relocate?", kind="select", options=options)
        trace = Trace()
        ans = default_answerer(f, make_profile(), default_config(), trace)
        assert ans["source"] == "profile-direct"
        assert ans["value"] == "2"
        assert ans["display"] == "I am willing to relocate to this job's location."
