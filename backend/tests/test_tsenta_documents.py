"""M7 unit tests: tsenta_documents (honest resume summary + cover letter)."""

import json

from backend.src.tools import tsenta_documents as docs
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_profiles import empty_profile, profile_from_json


def _profile():
    profile = empty_profile()
    profile["personalInformation"].update({
        "firstName": "Drupadh", "lastName": "Suresh",
        "email": "raven@example.com", "phone": "+15551234567",
        "city": "New York", "title": "Staff Engineer",
        "summary": "Eight years of backend platform work.",
        "linkedinUrl": "https://linkedin.com/in/raven-test",
    })
    profile["skillCategories"] = [{"name": "Backend", "skills": ["Python", "PostgreSQL"]}]
    profile["workExperience"] = [{
        "title": "Staff Engineer", "company": "Acme Corp",
        "startDate": "2020-01-01", "endDate": "2024-06-01",
        "bullets": ["Led the platform migration.", "Cut p99 latency 40%."],
    }]
    profile["education"] = [{"school": "State U", "degree": "B.S. Computer Science"}]
    profile["projects"] = [{"name": "TsentaClone", "description": "ATS automation"}]
    profile["certifications"] = [{"name": "AWS Solutions Architect"}]
    return profile


class TestResumeDocument:
    def test_honest_sections_verbatim(self):
        result = docs.resume_summary_document(_profile())
        assert result["status"] == "COMPLETED"
        assert result["optimizationMode"] == "honest"
        assert result["useOptimizedResume"] is False
        text = result["resumeText"]
        assert "Drupadh Suresh" in text
        assert "Eight years of backend platform work." in text
        assert "Python, PostgreSQL" in text
        assert "Staff Engineer" in text and "Acme Corp" in text
        assert "Led the platform migration." in text
        assert "State U" in text and "B.S. Computer Science" in text
        assert "TsentaClone" in text
        assert "AWS Solutions Architect" in text

    def test_honest_never_invents_when_profile_empty(self):
        result = docs.resume_summary_document(empty_profile())
        assert result["resumeText"] == ""
        assert result["status"] == "COMPLETED"

    def test_never_raises_on_bad_input(self):
        for bad in (None, "nope", 42, [1, 2]):
            result = docs.resume_summary_document(bad)
            assert isinstance(result, dict)
            assert result["status"] == "COMPLETED"

    def test_mode_from_config(self):
        config = default_config()
        config["optimizationMode"] = "aggressive"
        result = docs.resume_summary_document(_profile(), config)
        assert result["optimizationMode"] == "aggressive"
        assert result["useOptimizedResume"] is True

    def test_aggressive_reorders_bullets_by_job_keywords(self):
        profile = _profile()
        profile["workExperience"][0]["bullets"] = [
            "Led the platform migration.",
            "Cut p99 latency by 40%.",
            "Built event pipelines in Go.",
        ]
        config = default_config()
        config["optimizationMode"] = "aggressive"
        context = {"company": "Acme", "title": "Eng",
                   "description": "We need a Go engineer for event pipelines."}
        result = docs.resume_summary_document(
            profile, config, context, llm_cfg={"api_key": ""})
        text = result["resumeText"]
        # Keyword-matching bullet ("event pipelines in Go") must come first.
        assert text.index("- Built event pipelines in Go.") < text.index(
            "- Led the platform migration.")
        meta = result["resumeMetadata"]
        assert meta["matchPercentage"] > 0
        assert "go" in meta["matchedKeywords"] or "pipelines" in meta["matchedKeywords"]
        assert result["useOptimizedResume"] is True

    def test_aggressive_without_description_stays_verbatim(self):
        config = default_config()
        config["optimizationMode"] = "aggressive"
        result = docs.resume_summary_document(_profile(), config)
        assert result["resumeMetadata"] is None
        assert "Led the platform migration." in result["resumeText"]

    def test_aggressive_llm_rewrite_used(self):
        chat = FakeChat("""Drupadh Suresh
Staff Engineer

SUMMARY
Optimized resume summary emphasizing every listed fact without inventing anything new whatsoever. Eight years of backend platform work across Python and PostgreSQL systems. Experienced in leading platform migrations, improving performance, and delivering reliable services. Brings measurable engineering outcomes, practical database experience, and a consistent record of working within the supplied professional facts while communicating technical priorities clearly to stakeholders and delivery teams.

SKILLS
Python, PostgreSQL

EXPERIENCE
Staff Engineer | Acme Corp | 2020-01-01 - 2024-06-01
- Led the platform migration while preserving all supplied facts.

EDUCATION
B.S. Computer Science | State U
""")
        config = default_config()
        config["optimizationMode"] = "aggressive"
        result = docs.resume_summary_document(
            _profile(), config,
            {"description": "Python PostgreSQL platform engineering"}, chat=chat)
        assert "Optimized resume summary" in result["resumeText"]
        assert chat.calls
        prompt = chat.calls[0][-1]["content"]
        assert "invent" in prompt.lower()

    def test_aggressive_no_llm_falls_back_to_reordered_text(self):
        config = default_config()
        config["optimizationMode"] = "aggressive"
        result = docs.resume_summary_document(_profile(), config, llm_cfg={"api_key": ""})
        assert result["status"] == "COMPLETED"
        assert result["resumeText"]

    def test_live_profile_schema_aliases_keep_roles_bullets_and_university(self):
        profile = _profile()
        profile["workExperience"] = [{
            "role": "Security Analyst", "company": "Example Bank",
            "startDate": "2024-01", "responsibilities": [
                "Remediated critical vulnerabilities within SLA."
            ],
        }]
        profile["education"] = [{"university": "DePaul University",
                                  "degree": "M.S. Cybersecurity"}]
        result = docs.resume_summary_document(profile)
        assert "Security Analyst | Example Bank | Jan 2024 – Present" in result["resumeText"]
        assert "Remediated critical vulnerabilities within SLA." in result["resumeText"]
        assert "M.S. Cybersecurity | DePaul University" in result["resumeText"]

    def test_honest_mode_tailors_when_optimized_resume_and_jd_are_present(self):
        config = default_config()
        context = {"description": "Python PostgreSQL platform engineering"}
        result = docs.resume_summary_document(
            _profile(), config, context, llm_cfg={"api_key": ""})
        assert result["optimizationMode"] == "honest"
        assert result["useOptimizedResume"] is True
        assert result["resumeMetadata"]["matchPercentage"] > 0

    def test_reasoning_model_empty_content_retries_once(self, monkeypatch):
        base = docs.resume_summary_document(_profile())["resumeText"]
        complete = """Drupadh Suresh
Staff Engineer
raven@example.com

SUMMARY
Eight years of backend platform work focused on supplied facts and measurable outcomes. Experienced with Python, PostgreSQL, platform migrations, performance improvements, and reliable service delivery. Led engineering work while communicating technical priorities clearly and preserving every supplied fact. Brings practical database experience and a consistent record of measurable improvements across backend systems, migrations, and day-to-day platform operations for technical stakeholders.

SKILLS
Python, PostgreSQL

EXPERIENCE
Staff Engineer | Acme Corp | 2020-01-01 - 2024-06-01
- Led the platform migration and cut p99 latency by 40 percent using supplied facts.

EDUCATION
B.S. Computer Science | State U
"""
        responses = iter(["", complete])
        calls = []

        def fake_completion(messages, config):
            calls.append(config["max_tokens"])
            return next(responses)

        monkeypatch.setattr(docs, "chat_completion", fake_completion)
        result = docs._llm_rewrite_resume(
            base, _profile(), ["python", "platform"], {"api_key": "configured"}, None)
        assert "reliable service delivery" in result
        assert calls == [4000, 6000]


class FakeChat:
    def __init__(self, content="A polished honest rewrite of the letter that stays "
                               "strictly within the listed facts and reads professionally."):
        self.content = content
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return self.content


class TestCoverLetterDocument:
    def test_off_mode_returns_empty_shape(self):
        config = default_config()
        config["coverLetterMode"] = "off"
        result = docs.cover_letter_document(_profile(), config)
        assert result["useCoverLetter"] is False
        assert result["coverLetterMode"] == "off"
        assert result["coverLetterText"] is None

    def test_honest_template_uses_facts_only(self):
        config = default_config()
        config["coverLetterMode"] = "honest"
        result = docs.cover_letter_document(
            _profile(), config, {"company": "Acme Corp", "title": "Staff Engineer"})
        assert result["status"] == "COMPLETED"
        assert result["useCoverLetter"] is True
        text = result["coverLetterText"]
        assert "Acme Corp" in text and "Staff Engineer" in text
        assert "Drupadh" in text
        assert "Acme Corp" in result["coverLetterHtml"]
        assert "<br>" in result["coverLetterHtml"]

    def test_profile_cover_letter_template_preserves_authored_text_and_substitutes_job(self):
        profile = _profile()
        profile["coverLetterText"] = (
            "Dear Hiring Team,\\n\\nI am applying for {{role}} at {{company}}. "
            "My background in secure platform engineering is a strong fit for this work."
        )
        config = default_config()
        config["coverLetterMode"] = "honest"
        result = docs.cover_letter_document(
            profile, config, {"company": "Northwind", "title": "Security Engineer"})
        assert "Security Engineer at Northwind" in result["coverLetterText"]
        assert "{{role}}" not in result["coverLetterText"]

    def test_no_job_context_still_succeeds(self):
        result = docs.cover_letter_document(_profile(), default_config())
        assert result["useCoverLetter"] is True
        assert "Dear Hiring Team" in result["coverLetterText"]

    def test_auto_approve_false_keeps_text_but_unattached(self):
        config = default_config()
        config["autoApproveCoverLetter"] = False
        result = docs.cover_letter_document(_profile(), config)
        assert result["useCoverLetter"] is False
        assert result["coverLetterText"]

    def test_never_raises_on_bad_input(self):
        for bad in (None, "nope", []):
            result = docs.cover_letter_document(bad, default_config())
            assert isinstance(result, dict)
            assert result["status"] == "COMPLETED"

    def test_llm_rephrase_replaces_text(self):
        chat = FakeChat()
        config = default_config()
        config["coverLetterMode"] = "honest"
        result = docs.cover_letter_document(_profile(), config, chat=chat)
        assert "polished honest rewrite" in result["coverLetterText"]
        assert chat.calls  # the model was asked
        # the prompt forbids invention
        prompt = chat.calls[0][-1]["content"]
        assert "invent" in prompt.lower()

    def test_generated_mode_uses_llm_with_job_context(self):
        chat = FakeChat("Dear Hiring Team, I am writing regarding the Platform "
                        "Engineer role at Acme Corp and I have eight years of "
                        "backend platform work with Python and PostgreSQL. "
                        "Sincerely, Drupadh Suresh")
        config = default_config()
        config["coverLetterMode"] = "generated"
        result = docs.cover_letter_document(
            _profile(), config, {"company": "Acme Corp", "title": "Platform Engineer"},
            chat=chat)
        assert result["coverLetterMode"] == "generated"
        assert result["useCoverLetter"] is True
        assert "Acme Corp" in result["coverLetterText"]
        assert chat.calls
        prompt = chat.calls[0][-1]["content"]
        assert "invent" in prompt.lower()
        assert "Acme Corp" in prompt and "Platform Engineer" in prompt

    def test_generated_mode_no_llm_falls_back_to_template(self):
        config = default_config()
        config["coverLetterMode"] = "generated"
        result = docs.cover_letter_document(
            _profile(), config, {"company": "Acme Corp", "title": "Staff Engineer"},
            llm_cfg={"api_key": ""})
        assert result["coverLetterMode"] == "generated"
        assert "Dear Hiring Team" in result["coverLetterText"]
        assert "Acme Corp" in result["coverLetterText"]

    def test_generated_mode_model_refusal_falls_back_to_template(self):
        chat = FakeChat("Sorry, I cannot do that.")
        config = default_config()
        config["coverLetterMode"] = "generated"
        result = docs.cover_letter_document(_profile(), config, chat=chat)
        assert "Dear Hiring Team" in result["coverLetterText"]
        assert "Sorry, I cannot" not in result["coverLetterText"]


class TestDocumentsForApplication:
    def test_both_documents_returned(self):
        config = default_config()
        result = docs.documents_for_application(_profile(), config,
                                                {"company": "Acme", "title": "Eng"})
        assert set(result) == {"resume", "coverLetter"}
        assert result["resume"]["status"] == "COMPLETED"
        assert result["coverLetter"]["status"] == "COMPLETED"
        assert result["coverLetter"]["useCoverLetter"] is True
        assert result["resume"]["useOptimizedResume"] is False

    def test_auto_approve_resume_false_detaches(self):
        config = default_config()
        config["autoApproveResume"] = False
        result = docs.documents_for_application(_profile(), config)
        assert result["resume"]["useOptimizedResume"] is False

    def test_never_raises(self):
        for bad in (None, 42, {"x": 1}):
            assert isinstance(docs.documents_for_application(bad), dict)
        assert json.dumps(docs.documents_for_application(_profile()))

    def test_description_flows_to_resume_optimization(self):
        config = default_config()
        config["optimizationMode"] = "aggressive"
        profile = _profile()
        profile["workExperience"][0]["bullets"] = [
            "Led the platform migration.",
            "Built event pipelines in Go.",
        ]
        result = docs.documents_for_application(
            profile, config,
            {"company": "Acme", "title": "Eng",
             "description": "We need a Go engineer for event pipelines."},
            llm_cfg={"api_key": ""})
        text = result["resume"]["resumeText"]
        assert text.index("- Built event pipelines in Go.") < text.index(
            "- Led the platform migration.")
        assert result["resume"]["useOptimizedResume"] is True

    def test_cover_letter_quality_requires_targeting_and_useful_length(self):
        config = default_config()
        config["coverLetterMode"] = "generated"
        result = docs.documents_for_application(
            _profile(), config,
            {"company": "Target Corp", "title": "Security Engineer"},
            chat=lambda _messages: (
                "Dear Hiring Team,\n\nI am applying for a generic opening. "
                "My background is relevant.\n\nSincerely,\nDrupadh Suresh"))
        issues = result["coverLetter"]["qualityIssues"]
        assert "Cover letter is too brief for a job-specific review" in issues
        assert "Target company is missing from the cover letter" in issues
        assert "Target role is missing from the cover letter" in issues

    def test_targeted_cover_letter_passes_context_quality_checks(self):
        config = default_config()
        config["coverLetterMode"] = "generated"
        body = (
            "Dear Hiring Team,\n\nI am applying for the Security Engineer role at Target Corp. "
            "Eight years of backend platform work and hands-on Python and PostgreSQL experience "
            "align with the role. At Acme Corp, I led the platform migration and cut p99 latency "
            "40%, demonstrating careful delivery and measurable impact. My work building dependable "
            "services has required clear technical communication, practical troubleshooting, and "
            "consistent ownership. I would bring that same evidence-based approach to Target Corp "
            "while supporting its security engineering priorities. I welcome the opportunity to "
            "discuss the team and how my supplied experience can contribute.\n\nSincerely,\nDrupadh Suresh")
        result = docs.documents_for_application(
            _profile(), config,
            {"company": "Target Corp", "title": "Security Engineer"},
            chat=lambda _messages: body)
        assert result["coverLetter"]["qualityIssues"] == []

    def test_resume_role_metric_cannot_be_borrowed_from_another_employer(self):
        profile = _profile()
        profile["workExperience"].append({
            "title": "Engineer",
            "company": "Beta Labs",
            "startDate": "2018-01",
            "endDate": "2019-01",
            "bullets": ["Reduced incident volume by 20%."],
        })
        text = docs.resume_summary_document(profile)["resumeText"]
        unsafe = text.replace("Cut p99 latency 40%.", "Cut p99 latency 20%.")

        issues = docs._employer_scoped_fact_issues(unsafe, profile, "resume")

        assert any("Acme Corp" in issue and "20" in issue for issue in issues)

    def test_generated_letter_with_cross_employer_metric_uses_safe_fallback(self):
        profile = _profile()
        profile["workExperience"].append({
            "title": "Engineer",
            "company": "Beta Labs",
            "startDate": "2018-01",
            "endDate": "2019-01",
            "bullets": ["Reduced incident volume by 20%."],
        })
        unsafe = (
            "Dear Hiring Team,\n\nI am applying for the Security Engineer role at Target Corp. "
            "At Acme Corp, I reduced incident volume by 20% while leading platform work. "
            "My eight years of backend engineering experience also includes Python and PostgreSQL, "
            "reliable service delivery, practical troubleshooting, stakeholder communication, "
            "and measurable performance improvements. These supplied experiences align with the "
            "position's security, ownership, and operational priorities. I would welcome the chance "
            "to discuss how this background can support the team and its goals.\n\n"
            "Sincerely,\nDrupadh Suresh")
        config = default_config()
        config["coverLetterMode"] = "generated"

        result = docs.documents_for_application(
            profile, config,
            {"company": "Target Corp", "title": "Security Engineer"},
            chat=lambda _messages: unsafe)

        letter = result["coverLetter"]
        assert letter["coverLetterMetadata"]["safetyFallback"] is True
        assert "At Acme Corp, I reduced incident volume by 20%" not in letter["coverLetterText"]
        assert any("Acme Corp" in issue for issue in
                   letter["coverLetterMetadata"]["rejectedIssues"])
        assert letter["qualityIssues"] == []

    def test_target_title_number_is_not_treated_as_candidate_claim(self):
        config = default_config()
        config["coverLetterMode"] = "generated"
        body = (
            "Dear Hiring Team,\n\nI am applying for the Security Analyst 2 role at Target Corp. "
            "My eight years of backend platform work includes Python, PostgreSQL, reliable "
            "service delivery, practical troubleshooting, technical ownership, and stakeholder "
            "communication. At Acme Corp, I led the platform migration and cut p99 latency 40%. "
            "That factual experience aligns with the team's operational priorities and need for "
            "careful engineering judgment. I would welcome the opportunity to discuss how my "
            "background can contribute to Target Corp and its security program.\n\n"
            "Sincerely,\nDrupadh Suresh")

        result = docs.documents_for_application(
            _profile(), config,
            {"company": "Target Corp", "title": "Security Analyst 2"},
            chat=lambda _messages: body)

        assert not any("absent from profile: 2" in issue for issue in
                       result["coverLetter"]["qualityIssues"])

    def test_target_role_words_can_appear_naturally_across_the_letter(self):
        config = default_config()
        config["coverLetterMode"] = "generated"
        body = (
            "Dear Target Corp Hiring Team,\n\nI am applying to contribute as an engineer on your team. "
            "My eight years of backend platform work includes Python, PostgreSQL, dependable "
            "delivery, practical troubleshooting, technical ownership, and stakeholder "
            "communication. At Acme Corp, I led the platform migration and cut p99 latency "
            "40%. That factual experience would support Target Corp's cybersecurity priorities "
            "through careful engineering judgment and measurable execution. I welcome the "
            "opportunity to discuss how my supplied background can contribute to the team.\n\n"
            "Sincerely,\nDrupadh Suresh")

        result = docs.documents_for_application(
            _profile(), config,
            {"company": "Target Corp", "title": "Cybersecurity Engineer"},
            chat=lambda _messages: body)

        assert "Target role is missing from the cover letter" not in (
            result["coverLetter"]["qualityIssues"])

    def test_employer_brand_name_satisfies_company_targeting(self):
        config = default_config()
        config["coverLetterMode"] = "generated"
        body = (
            "Dear Hiring Team,\n\nI am applying for the Cybersecurity Engineer role. "
            "My eight years of backend platform work includes Python, PostgreSQL, dependable "
            "delivery, practical troubleshooting, technical ownership, and stakeholder "
            "communication. At Acme Corp, I led the platform migration and cut p99 latency "
            "40%. That factual experience would support Apollo's cybersecurity priorities "
            "through careful engineering judgment and measurable execution. I welcome the "
            "opportunity to discuss how my supplied background can contribute to the team.\n\n"
            "Sincerely,\nDrupadh Suresh")

        result = docs.documents_for_application(
            _profile(), config,
            {"company": "Apollo Information Systems", "title": "Cybersecurity Engineer"},
            chat=lambda _messages: body)

        assert "Target company is missing from the cover letter" not in (
            result["coverLetter"]["qualityIssues"])


class TestJobContextAndArtifacts:
    def test_fetch_job_context_from_greenhouse_title_fallback(self, monkeypatch):
        markup = b"""<html><head><meta property='og:title' content='Job Application for Security Advisor at Example Corp'></head><body><h1>Security Advisor</h1><p>Vulnerability management and NIST CSF.</p></body></html>"""

        class Headers:
            @staticmethod
            def get_content_charset():
                return "utf-8"

        class Response:
            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            @staticmethod
            def read(_limit):
                return markup

        monkeypatch.setattr(docs.urllib.request, "urlopen", lambda *_a, **_k: Response())
        context = docs.fetch_job_context("https://example.test/job")
        assert context["title"] == "Security Advisor"
        assert context["company"] == "Example Corp"
        assert "Vulnerability management" in context["description"]

    def test_materialize_documents_records_verified_pdf_metadata(self, tmp_path):
        documents = docs.documents_for_application(
            _profile(), default_config(),
            {"description": "Python PostgreSQL platform engineering"},
            llm_cfg={"api_key": ""})

        def renderer(text, path, title, kind):
            payload = b"%PDF-1.4\n" + b"x" * 1500
            with open(path, "wb") as handle:
                handle.write(payload)
            return {"ok": True, "path": path, "fileName": path.split("\\")[-1].split("/")[-1],
                    "byteSize": len(payload), "sha256": "abc", "error": ""}

        result = docs.materialize_documents(documents, "app_test", str(tmp_path), renderer)
        assert result["resume"]["pdfGenerated"] is True
        assert result["resume"]["attachmentReady"] is True
        assert result["resume"]["fileName"] == "Drupadh_Suresh_Targeted_Role_Resume.pdf"
        assert result["coverLetter"]["pdfGenerated"] is True
