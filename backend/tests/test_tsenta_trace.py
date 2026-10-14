"""M2 unit tests: tsenta_trace."""

import json
import time

import pytest

from backend.src.tools.tsenta_trace import (
    ANSWER_SOURCES,
    FALLBACK_REASON,
    FALLBACK_TEXT,
    FIELD_KINDS,
    TRACE_PHASES,
    Trace,
    conditional_skip_reason,
)


class TestConditionalSkipReason:
    def test_with_answer_value(self):
        reason = conditional_skip_reason("300000281694968", "300000281694976", "300000281694970")
        assert reason == ('conditional-hidden: parent question 300000281694968 '
                          'answer="300000281694976" !== trigger 300000281694970')

    def test_with_null_answer(self):
        reason = conditional_skip_reason("300000281694977", None, "300000281694983")
        assert reason == ('conditional-hidden: parent question 300000281694977 '
                          'answer=null !== trigger 300000281694983')

    def test_quotes_escaped(self):
        reason = conditional_skip_reason("1", 'say "hi"', "2")
        assert 'answer="say \\"hi\\""' in reason


class TestTraceLifecycle:
    def test_new_trace_shape(self):
        trace = Trace(ats="greenhouse")
        assert trace.meta["ats"] == "greenhouse"
        assert trace.meta["outcome"] == "pending"
        assert trace.meta["durationMs"] == 0
        assert trace.meta["startedAt"] > 1_600_000_000_000
        assert trace.timeline == [{"phase": "fetch:start", "at": trace.meta["startedAt"]}]
        assert trace.answers == []
        assert trace.derivedMissingFields == []

    def test_finish_sets_outcome_and_duration(self):
        trace = Trace(started_at_ms=1000)
        time.sleep(0.01)
        meta = trace.finish("submitted")
        assert meta["outcome"] == "submitted"
        assert meta["durationMs"] > 0

    def test_mark_accepts_all_recovered_phases(self):
        trace = Trace()
        for phase in TRACE_PHASES:
            trace.mark(phase)
        assert [t["phase"] for t in trace.timeline] == ["fetch:start", *TRACE_PHASES]

    def test_mark_custom_phase_accepted(self):
        trace = Trace()
        entry = trace.mark("custom:phase")
        assert entry == {"phase": "custom:phase", "at": entry["at"]}


class TestAnswerRecording:
    def test_profile_direct(self):
        trace = Trace()
        answer = trace.answer_profile_direct("basicInformation.firstName", "First Name",
                                             "text", "Drupadh", required=True)
        assert answer == {
            "fieldId": "basicInformation.firstName",
            "label": "First Name",
            "kind": "text",
            "source": "profile-direct",
            "value": "Drupadh",
            "required": True,
            "display": "Drupadh",
        }

    def test_llm_with_options_sets_display_from_label(self):
        trace = Trace()
        options = [{"label": "Other", "value": "300000281694976"},
                   {"label": "Job Board", "value": "300000281694972"}]
        answer = trace.answer_llm("q1", "How did you hear about us?", "radio",
                                  "300000281694976", options=options)
        assert answer["value"] == "300000281694976"
        assert answer["display"] == "Other"
        assert answer["options"] == options

    def test_llm_explicit_display_wins(self):
        trace = Trace()
        answer = trace.answer_llm("q1", "Q", "radio", "v1", display="Explicit")
        assert answer["display"] == "Explicit"

    def test_llm_null_value(self):
        trace = Trace()
        answer = trace.answer_llm("q1", "Q", "text", None)
        assert answer["value"] == "" and answer["display"] == ""

    def test_skip_records_reason_and_empty_value(self):
        trace = Trace()
        answer = trace.answer_skip("q.child", "Name of the Other Source", "text",
                                   "300000281694968", "300000281694976", "300000281694970")
        assert answer["source"] == "skip"
        assert answer["value"] == ""
        assert answer["display"] == ""
        assert answer["reason"].startswith("conditional-hidden: parent question 300000281694968")

    def test_fallback_verbatim(self):
        trace = Trace()
        answer = trace.answer_fallback("q1", "Q", "text")
        assert answer["source"] == "fallback"
        assert answer["value"] == FALLBACK_TEXT
        assert answer["display"] == FALLBACK_TEXT
        assert answer["reason"] == FALLBACK_REASON

    def test_invalid_source_returns_none_and_not_recorded(self):
        trace = Trace()
        answer = trace.record_answer("q1", "Q", "text", "v", "hacker", True)
        assert answer is None
        assert trace.answers == []

    def test_invalid_kind_coerced_to_text(self):
        trace = Trace()
        answer = trace.record_answer("q1", "Q", "weird", "v", "profile-direct", True)
        assert answer["kind"] == "text"

    def test_nori_choice_and_consent_kinds_remain_editable(self):
        trace = Trace()
        choice = trace.record_answer("source", "Where did you hear about us?",
                                     "checkbox_group", "careers", "llm", True)
        consent = trace.record_answer("privacy", "Accept privacy policy",
                                      "checkbox", "", "skip", True)
        assert choice["kind"] == "checkbox_group"
        assert consent["kind"] == "checkbox"

    def test_options_only_when_provided(self):
        trace = Trace()
        answer = trace.answer_profile_direct("q1", "Q", "text", "v")
        assert "options" not in answer


class TestDerivedMissing:
    def test_add_and_dedupe(self):
        trace = Trace()
        trace.add_derived_missing("q1")
        trace.add_derived_missing("q1")
        assert trace.derivedMissingFields == ["q1"]


class TestSerialization:
    def test_to_dict_shape_matches_recovered_trace(self):
        trace = Trace(ats="oraclecloud-api", outcome="submitted")
        trace.answer_profile_direct("basicInformation.firstName", "First Name", "text", "Drupadh")
        data = trace.to_dict()
        assert list(data) == ["meta", "answers", "timeline", "derivedMissingFields"]
        assert list(data["meta"]) == ["ats", "outcome", "startedAt", "durationMs"]
        assert data["answers"][0]["source"] == "profile-direct"

    def test_to_json_round_trip(self):
        trace = Trace(ats="lever")
        trace.answer_llm("q1", "Q", "radio", "v1", options=[{"label": "A", "value": "v1"}])
        trace.answer_skip("q2", "Q2", "text", "parent", None, "trig")
        trace.mark("parse:done")
        restored = Trace.from_json(trace.to_json())
        assert restored.to_dict() == trace.to_dict()
        assert restored.meta["ats"] == "lever"

    def test_from_json_malformed(self):
        trace = Trace.from_json("not json")
        assert trace.answers == []
        assert trace.meta["ats"] == ""

    def test_from_json_none(self):
        assert Trace.from_json(None).timeline == [{"phase": "fetch:start",
                                                   "at": Trace.from_json(None).meta["startedAt"]}]

    def test_from_dict_partial(self):
        trace = Trace.from_dict({"answers": [{"fieldId": "x", "label": "X", "kind": "text",
                                              "source": "llm", "value": "v", "required": True,
                                              "display": "V"}]})
        assert trace.answers[0]["fieldId"] == "x"


class TestSourcesSummary:
    def test_histogram_matches_recovered_distribution(self):
        trace = Trace()
        for _ in range(19):
            trace.answer_profile_direct("f", "F", "text", "v")
        for _ in range(7):
            trace.answer_llm("f", "F", "text", "v")
        for _ in range(10):
            trace.answer_skip("f", "F", "text", "p", None, "t")
        for _ in range(1):
            trace.answer_fallback("f", "F", "text")
        assert trace.sources_summary() == {
            "profile-direct": 19, "llm": 7, "user-override": 0,
            "skip": 10, "fallback": 1,
        }

    def test_all_sources_present(self):
        assert set(ANSWER_SOURCES) == {"profile-direct", "llm", "user-override", "skip", "fallback"}
        assert set(FIELD_KINDS) == {
            "text", "textarea", "email", "phone", "number", "single_select",
            "select", "radio", "checkbox", "checkbox_group", "file",
        }

    def test_empty_trace(self):
        summary = Trace().sources_summary()
        assert summary == {"profile-direct": 0, "llm": 0, "user-override": 0,
                           "skip": 0, "fallback": 0}
