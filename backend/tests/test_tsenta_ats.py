"""M0 unit tests: tsenta_ats detection engine port.

Covers: all 34 ATS fingerprints with realistic hostnames, first-match-wins
ordering, negatives, candidate extraction (redirect chains, nested/double
encoding), depth-4 recursive detection, status normalization.
"""

import pytest

from backend.src.tools.tsenta_ats import (
    ATS_CATALOG,
    SUPPORTED_ATS,
    ats_detect,
    ats_detect_chain,
    ats_display_name,
    ats_normalize_hint,
    ats_extract_candidates,
    status_normalize,
)

ALL_34 = {
    "greenhouse", "lever", "workday", "ashby", "workable", "rippling",
    "bamboohr", "breezyhr", "jazzhr", "jobvite", "paylocity",
    "smartrecruiters", "icims", "brassring", "oraclecloud", "recruitee",
    "pinpoint", "teamtailor", "polymer", "dayforce", "successfactors", "join",
    "hireology", "naukri", "indeed", "avature", "phenom",
    "ultipro", "zohorecruit", "adp", "paycom", "dover", "gem", "bullhorn",
}


class TestSignatureCount:
    def test_catalog_has_all_34(self):
        missing = ALL_34 - set(ATS_CATALOG)
        assert not missing, f"catalog missing: {missing}"

    def test_supported_ats_matches_runtime_27(self):
        expected_supported = {
            "greenhouse", "lever", "workday", "naukri", "indeed", "ashby",
            "icims", "brassring", "workable", "rippling", "bamboohr",
            "breezyhr", "jazzhr", "jobvite", "paylocity", "oraclecloud",
            "smartrecruiters", "recruitee", "pinpoint", "teamtailor",
            "polymer", "phenom", "dayforce", "successfactors", "join",
            "hireology", "paycom",
        }
        assert SUPPORTED_ATS == expected_supported

    def test_feed_hint_aliases_are_known_only(self):
        assert ats_normalize_hint("adprecruiting") == "adp"
        assert ats_normalize_hint("icims2") == "icims"
        assert ats_normalize_hint("paycom") == "paycom"
        assert ats_normalize_hint("made-up-system") == "unknown"


class TestPositives:
    @pytest.mark.parametrize(
        "url,expected",
        [
            # greenhouse: hostname contains
            ("https://boards.greenhouse.io/twitch/jobs/123", "greenhouse"),
            ("https://job-boards.greenhouse.io/company/jobs/123", "greenhouse"),
            ("https://boards.greenhouse.io/embed/job_app?token=abc", "greenhouse"),
            # greenhouse: query params
            ("https://careers.example.com/jobs?gh_jid=435678", "greenhouse"),
            ("https://careers.example.com/apply?gh_src=linkedin&gh_jid=1", "greenhouse"),
            ("https://careers.example.com/?greenhouse_jid=123", "greenhouse"),
            # lever
            ("https://jobs.lever.co/company/senior-engineer", "lever"),
            ("https://jobs.lever.co/company", "lever"),
            # workday
            ("https://company.wd1.myworkdayjobs.com/Job/Company/123", "workday"),
            ("https://company.wd2.myworkdayjobs-impl.com/apply/1", "workday"),
            ("https://careers.myworkdaysite.com/company/job/1", "workday"),
            # ashby
            ("https://jobs.ashbyhq.com/company/abc-123", "ashby"),
            # workable
            ("https://apply.workable.com/company/jobs/123", "workable"),
            # rippling
            ("https://company.rippling-ats.com/jobs/123", "rippling"),
            ("https://ats.rippling.com/company/jobs/123", "rippling"),
            ("https://jobs.ats.rippling.com/company", "rippling"),
            # bamboohr
            ("https://company.bamboohr.com/careers/123", "bamboohr"),
            # breezyhr
            ("https://company.breezy.hr/p/123", "breezyhr"),
            # jazzhr
            ("https://company.applytojob.com/apply/abc", "jazzhr"),
            # jobvite
            ("https://jobs.jobvite.com/company/jobs/123", "jobvite"),
            ("https://careers.company.jobvite.com/jobs/456", "jobvite"),
            # paylocity
            ("https://recruiting.paylocity.com/Recruiting/Jobs/All/company", "paylocity"),
            # smartrecruiters
            ("https://jobs.smartrecruiters.com/Company/743999", "smartrecruiters"),
            # icims
            ("https://jobs.icims.com/jobs/123?pr=abc", "icims"),
            ("https://careers.company.jibeapply.com/jobs/456", "icims"),
            ("https://icims.com/jobs/789", "icims"),
            # brassring
            ("https://careers.company.brassring.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=1&siteid=2&jobid=123", "brassring"),
            ("https://careers.company.brassring.com/TGnewUI/Search/home/HomeWithPreLoad#jobdetails=123", "brassring"),
            ("https://jobs.ubs.com/TGnewUI/search/home/?jobid=456", "brassring"),
            # oraclecloud
            ("https://company.fa.us2.oraclecloud.com/hcmUI/candidateExperience/en/sites/CX_1/job/123", "oraclecloud"),
            ("https://company.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1", "oraclecloud"),
            ("https://company.taleo.net/careersection/123/jobdetail.ftl?job=456", "oraclecloud"),
            ("https://company.fa.us2.oraclecloud.com/sites/cx_17041/job/123", "oraclecloud"),
            # recruitee
            ("https://company.recruitee.com/o/senior-engineer", "recruitee"),
            # pinpoint
            ("https://jobs.pinpointhq.com/company/123", "pinpoint"),
            # teamtailor
            ("https://careers.company.teamtailor.com/jobs/123", "teamtailor"),
            # polymer
            ("https://jobs.polymer.co/company/123", "polymer"),
            # dayforce
            ("https://company.dayforcehcm.com/CandidatePortal/company", "dayforce"),
            # successfactors
            ("https://company.successfactors.com/careers?company=1", "successfactors"),
            ("https://company.successfactors.eu/careers", "successfactors"),
            ("https://company.sapsf.com/careers", "successfactors"),
            ("https://jobs.hr.cloud.sap/company", "successfactors"),
            ("https://company.ns2cloud.com/careers", "successfactors"),
            # join
            ("https://join.com/companies/company/jobs/123", "join"),
            ("https://www.join.com/companies/company", "join"),
            # hireology
            ("https://careers.hireology.com/company/123", "hireology"),
            # naukri
            ("https://www.naukri.com/job/software-engineer-123", "naukri"),
            ("https://naukri.com/job/456", "naukri"),
            # indeed
            ("https://www.indeed.com/viewjob?jk=abc123", "indeed"),
            ("https://indeed.com/jobs?q=x", "indeed"),
            # avature
            ("https://careers.company.avature.net/signin", "avature"),
            # phenom
            ("https://company.phenompeople.com/jobs/123", "phenom"),
            ("https://careers.phenom.com/jobs/123", "phenom"),
            ("https://careers.company.com/careers?jobseqno=123", "phenom"),
            ("https://careers.company.com/en/us/job/software-engineer", "phenom"),
            ("https://careers.company.com/xx/xx/apply", "phenom"),
            # ultipro / UKG
            ("https://recruiting2.ultipro.com/COM123/company/jobs/123", "ultipro"),
            ("https://recruiting.ultipro.com/company/jobs/123", "ultipro"),
            ("https://company.ultipro.ca/careers/123", "ultipro"),
            ("https://company.rec.pro.ukg.net/company/jobs/123", "ultipro"),
            # zoho recruit
            ("https://company.zohorecruit.com/jobs/123", "zohorecruit"),
            ("https://company.zohorecruit.in/jobs/123", "zohorecruit"),
            # adp
            ("https://workforcenow.adp.com/jobs/123", "adp"),
            ("https://myjobs.adp.com/acme/cx/job-details?reqId=500123", "adp"),
            # paycom
            ("https://www.paycomonline.net/v4/ats/web.php/jobs/ViewJobDetails?job=42&clientkey=ABC", "paycom"),
            # dover
            ("https://app.dover.com/apply/company/123", "dover"),
            # gem
            ("https://jobs.gem.com/company/123", "gem"),
            # bullhorn
            ("https://company.bullhornstaffing.com/jobs/123", "bullhorn"),
        ],
    )
    def test_detect_positive(self, url, expected):
        result = ats_detect(url)
        assert result["ats_id"] == expected, f"{url} -> {result}"

    def test_all_34_reachable(self):
        hit = set()
        for url, expected in TestPositives.test_detect_positive.pytestmark[0].args[1]:
            hit.add(expected)
        assert hit == ALL_34, f"uncovered: {ALL_34 - hit}"


class TestConfidence:
    def test_known_has_positive_confidence(self):
        for url in [
            "https://boards.greenhouse.io/company/jobs/1",
            "https://jobs.lever.co/company/1",
            "https://company.wd1.myworkdayjobs.com/Job/1",
        ]:
            result = ats_detect(url)
            assert 0.0 < result["confidence"] <= 1.0

    def test_unknown_zero_confidence(self):
        assert ats_detect("https://www.google.com")["confidence"] == 0.0

    def test_rule_never_empty_for_matches(self):
        result = ats_detect("https://jobs.ashbyhq.com/company/1")
        assert isinstance(result["rule"], str) and result["rule"]


class TestOrderingFirstMatchWins:
    def test_greenhouse_param_beats_lever_host(self):
        # gh_jid param is checked before lever host: greenhouse wins
        result = ats_detect("https://jobs.lever.co/company/1?gh_jid=42")
        assert result["ats_id"] == "greenhouse"

    def test_greenhouse_hostname_contains_wins(self):
        assert ats_detect("https://boards.greenhouse.io/jobs.lever.co")["ats_id"] == "greenhouse"


class TestNegatives:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.google.com",
            "https://github.com/company/careers",
            "https://careers.example.com/jobs/123",
            "https://workday.com/company",                     # bare workday.com is not workday
            "https://lever.com/company",                       # lever.com is not lever.co
            "https://www.ashby.com/company",                   # ashby.com is not ashbyhq.com
            "https://recruitee.com/company",                   # bare recruitee.com needs subdomain
            "https://careers.company.brassring.com/TGnewUI/Search/home/",  # missing jobid
            "https://www.paylocity.com/products",              # no /recruiting path
            "https://company.fa.oraclecloud.com/foo/bar",      # no candidateexperience
            "https://join.com/about/company",                  # join needs /companies/
            "https://www.indeed.com-cdn.example.com/",         # not indeed host
            "https://example.com/en/us/about",                 # phenom regex needs job/... or apply
            "https://www.reddit.com",                          # plain negative
            "https://example.com",                             # bare domain
            "not a url",                                       # malformed
            "",                                                # empty
            None,                                              # None
        ],
    )
    def test_detect_negative(self, url):
        result = ats_detect(url)
        assert result["ats_id"] == "unknown", f"{url!r} -> {result}"
        assert result["confidence"] == 0.0

    def test_recruitee_subdomain_required(self):
        assert ats_detect("https://recruitee.com/o/1")["ats_id"] == "unknown"

    def test_ultipro_needs_proper_host(self):
        assert ats_detect("https://ultipro.com/company/jobs")["ats_id"] == "unknown"

    def test_zohorecruit_host_requires_dot(self):
        assert ats_detect("https://zohorecruit.com/jobs")["ats_id"] == "unknown"

    def test_adp_needs_workforcenow_host(self):
        assert ats_detect("https://adp.com/jobs")["ats_id"] == "unknown"

    def test_dover_needs_apply_path(self):
        assert ats_detect("https://app.dover.com/company/123")["ats_id"] == "unknown"

    def test_gem_needs_proper_host(self):
        assert ats_detect("https://gem.com/company/jobs")["ats_id"] == "unknown"

    def test_bullhorn_needs_subdomain(self):
        assert ats_detect("https://bullhornstaffing.com/jobs")["ats_id"] == "unknown"


class TestCandidateExtraction:
    def test_single_encoded_query_param(self):
        candidates = ats_extract_candidates(
            "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fboards.greenhouse.io%2Fcompany%2Fjobs%2F123"
        )
        assert "https://boards.greenhouse.io/company/jobs/123" in candidates

    def test_double_encoded_query_param(self):
        candidates = ats_extract_candidates(
            "https://tracker.example.com/r?u=https%253A%252F%252Fjobs.lever.co%252Fcompany%252Frole"
        )
        assert "https://jobs.lever.co/company/role" in candidates

    def test_raw_url_in_query_value(self):
        candidates = ats_extract_candidates(
            "https://example.com/go?next=https://company.applytojob.com/apply/xyz"
        )
        assert "https://company.applytojob.com/apply/xyz" in candidates

    def test_url_embedded_in_search_string(self):
        candidates = ats_extract_candidates(
            "https://www.indeed.com/apply?redirect=%22https://company.rippling-ats.com/jobs/1%22"
        )
        assert "https://company.rippling-ats.com/jobs/1" in candidates

    def test_clean_url_yields_no_foreign_candidates(self):
        candidates = ats_extract_candidates("https://jobs.ashbyhq.com/company/1")
        assert "https://jobs.ashbyhq.com/company/1" in candidates

    def test_malformed_returns_empty(self):
        assert ats_extract_candidates("") == []
        assert ats_extract_candidates("not a url") == []


class TestChainDetection:
    def test_linkedin_safety_go_detects_greenhouse(self):
        # Faithful to the recovered engine: the decoded haystack of the safety/go
        # URL itself contains "greenhouse.io", so even single-level detect fires.
        url = "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fboards.greenhouse.io%2Fcompany%2Fjobs%2F123"
        assert ats_detect(url)["ats_id"] == "greenhouse"
        assert ats_detect_chain(url)["ats_id"] == "greenhouse"

    def test_double_encoded_chain_to_workday(self):
        result = ats_detect_chain(
            "https://tracker.example.com/click?target=https%253A%252F%252Fcompany.wd1.myworkdayjobs.com%252FJob%252F1"
        )
        assert result["ats_id"] == "workday"

    def test_direct_url_no_recursion_needed(self):
        result = ats_detect_chain("https://jobs.lever.co/company/1")
        assert result["ats_id"] == "lever"

    def test_unknown_without_candidates(self):
        assert ats_detect_chain("https://www.google.com")["ats_id"] == "unknown"

    def test_depth_limit_exhausted_returns_unknown(self):
        # Chain of wrappers with no ATS anywhere: never resolves
        url = "https://a.example.com/go?u=https%3A%2F%2Fb.example.com%2Fgo%3Fu%3Dhttps%253A%252F%252Fc.example.com"
        result = ats_detect_chain(url)
        assert result["ats_id"] == "unknown"

    def test_chain_cracks_redirect_wrapper_to_avature(self):
        # Avature has no decoded-haystack rule (hostname only), so this needs
        # real recursion: wrapper -> avature URL (within the 4-URL budget).
        url = "https://redirect.example.com/?to=https%3A%2F%2Fcareers.company.avature.net"
        result = ats_detect_chain(url)
        assert result["ats_id"] == "avature"
        assert "via" in result["rule"]

    def test_chain_depth_budget_is_four_urls_total(self):
        # Recovered engine examines at most 4 URLs (original + 3 candidates).
        # A 4-hop chain exceeds the budget -> unknown, faithful to the JS.
        url = (
            "https://a.example.com/1?u=https%3A%2F%2Fb.example.com%2F2%3Fu%3D"
            "https%253A%252F%252Fc.example.com%252F3%253Fu%253D"
            "https%25253A%25252F%25252Fcareers.company.avature.net"
        )
        result = ats_detect_chain(url)
        assert result["ats_id"] == "unknown"

    def test_none_and_empty(self):
        assert ats_detect_chain(None)["ats_id"] == "unknown"
        assert ats_detect_chain("")["ats_id"] == "unknown"


class TestStatusNormalize:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("OPTIMIZING_RESUME", "queued"),
            ("PENDING", "queued"),
            ("CREATED", "queued"),
            ("PENDING_REVIEW", "review"),
            ("REVIEW_REQUIRED", "review"),
            ("RUNNING", "running"),
            ("IN_PROGRESS", "running"),
            ("COMPLETED", "applied"),
            ("SUBMITTED", "applied"),
            ("FAILED", "failed"),
            ("SKIPPED", "failed"),
            ("PAUSED", "paused"),
            ("Running", "running"),
            ("unknown-status", "queued"),
            ("", "queued"),
            (None, "queued"),
        ],
    )
    def test_status_mapping(self, status, expected):
        assert status_normalize(status) == expected


class TestDisplayName:
    def test_display_names(self):
        assert ats_display_name("greenhouse") == "Greenhouse"
        assert ats_display_name("oraclecloud") == "Oracle Recruiting"
        assert ats_display_name("successfactors") == "SAP SuccessFactors"

    def test_unknown_id(self):
        assert ats_display_name("definitely-not-an-ats") == "Definitely-not-an-ats"

    def test_every_ats_has_catalog_entry(self):
        for ats_id in ALL_34:
            assert ats_id in ATS_CATALOG, ats_id
            assert ATS_CATALOG[ats_id]["name"], ats_id


class TestRegisteredSignatures:
    def setup_method(self):
        from backend.src.tools import tsenta_ats as mod

        self._mod = mod
        for ats_id in mod.registered_ats():
            mod.unregister_ats_signature(ats_id)

    def teardown_method(self):
        for ats_id in self._mod.registered_ats():
            self._mod.unregister_ats_signature(ats_id)

    def test_register_pattern_signature_detects(self):
        ok = self._mod.register_ats_signature(
            "myats", name="MyATS", url_patterns=["myats.example.com"])
        assert ok is True
        result = self._mod.ats_detect("https://myats.example.com/role/42")
        assert result["ats_id"] == "myats"
        assert result["confidence"] > 0.5
        assert "registered" in result["rule"]

    def test_register_predicate_signature_detects(self):
        self._mod.register_ats_signature(
            "parity-check",
            predicate=lambda parts: "parity" in parts["path"])
        result = self._mod.ats_detect("https://careers.acme.com/parity/1")
        assert result["ats_id"] == "parity-check"

    def test_custom_never_shadows_builtin(self):
        # Registered rules run AFTER the 27 built-ins: a greenhouse URL must
        # still resolve to greenhouse even if a custom pattern also matches.
        self._mod.register_ats_signature(
            "fakegh", url_patterns=["greenhouse.io"])
        result = self._mod.ats_detect("https://boards.greenhouse.io/mozilla/jobs/1")
        assert result["ats_id"] == "greenhouse"

    def test_unregister_stops_detection(self):
        self._mod.register_ats_signature("tempats", url_patterns=["tempats.com"])
        assert self._mod.unregister_ats_signature("tempats") is True
        assert self._mod.unregister_ats_signature("tempats") is False
        result = self._mod.ats_detect("https://tempats.com/role/1")
        assert result["ats_id"] == "unknown"

    def test_register_validates_input(self):
        assert self._mod.register_ats_signature("") is False
        assert self._mod.register_ats_signature("   ") is False
        assert self._mod.register_ats_signature("nopattern") is False

    def test_registered_has_catalog_and_supported_entries(self):
        self._mod.register_ats_signature("brandnew", name="Brand New",
                                         url_patterns=["brandnew.hr"])
        assert self._mod.ats_display_name("brandnew") == "Brand New"
        assert "brandnew" in self._mod.SUPPORTED_ATS
