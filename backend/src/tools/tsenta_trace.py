"""tsenta_trace — per-question execution trace recorder (M2).

Python port of the recovered trace JSON shape from GET /applications/{id}/trace
(verified against trace_jefferies.json, 37 answers, Oracle Cloud application):

    meta:     {ats, outcome, startedAt (ms epoch), durationMs}
    answers:  [{fieldId, label, kind, source, value, required, display,
                options?: [{label, value}], reason?}]
    timeline: [{phase: <19 recovered phases>, at: ms}]
    derivedMissingFields: [fieldId, ...] (present in the recovered trace)

Answer sources (recovered semantics plus Nori review edits):
    profile-direct | llm | user-override | skip (reason: "conditional-hidden: parent question
    <id> answer=\"<val|null>\" !== trigger <id>") | fallback (verbatim text +
    reason "answerer fallback override")

Public methods return strings/dicts and never raise.
"""

from __future__ import annotations

import json
import time

# Verbatim recovered fallback text and reason.
FALLBACK_TEXT = "Please refer to my resume and the rest of this application for relevant details on this point."
FALLBACK_REASON = "answerer fallback override"

ANSWER_SOURCES = ("profile-direct", "llm", "user-override", "skip", "fallback")

# Field kinds observed in the recovered trace plus Nori's browser-native
# extensions. Keeping checkbox and numeric semantics prevents the review UI
# from presenting legal consent as free text or salary as prose.
FIELD_KINDS = (
    "text", "textarea", "email", "phone", "number", "single_select",
    "select", "radio", "checkbox", "checkbox_group", "file",
)

# The 19 timeline phases (order preserved from the recovered trace).
TRACE_PHASES = (
    "fetch:start", "fetch:done", "parse:done", "verify:start", "verify:done",
    "answer:start", "answer:done", "draft:start", "draft:done",
    "candidate:start", "candidate:done", "resume:start", "resume:done",
    "profile-items:start", "profile-items:done", "submit:start",
    "submit:outcome", "confirm:start", "confirm:done",
)


def conditional_skip_reason(parent_question_id: str, parent_answer, trigger: str) -> str:
    """Build the recovered conditional-hidden skip reason string.

    Args:
        parent_question_id: id of the parent (triggering) question.
        parent_answer: the parent's answered value, or None when unanswered.
        trigger: the trigger value that would have shown this field.

    Returns:
        str: e.g. 'conditional-hidden: parent question 300000281694968
        answer="300000281694976" !== trigger 300000281694970' (answer=null
        when the parent was not answered). Never raises.
    """
    if parent_answer is None:
        answer = "null"
    else:
        answer = '"' + str(parent_answer).replace('"', '\\"') + '"'
    return f"conditional-hidden: parent question {parent_question_id} answer={answer} !== trigger {trigger}"


def _now_ms() -> int:
    return int(time.time() * 1000)


class Trace:
    """Per-application execution trace recorder (recovered shape)."""

    def __init__(self, ats: str = "", outcome: str = "pending", started_at_ms: int | None = None):
        """Start a new trace.

        Args:
            ats: ATS id (e.g. "greenhouse", "oraclecloud-api").
            outcome: initial outcome ("pending" until finish()).
            started_at_ms: epoch ms; defaults to now.
        """
        self.meta = {
            "ats": ats,
            "outcome": outcome,
            "startedAt": int(started_at_ms) if started_at_ms is not None else _now_ms(),
            "durationMs": 0,
        }
        self.answers = []
        self.timeline = []
        self.derivedMissingFields = []
        self.mark("fetch:start")

    def mark(self, phase: str, at_ms: int | None = None) -> dict:
        """Record a timeline phase timestamp.

        Args:
            phase: one of TRACE_PHASES (custom phases are accepted too).
            at_ms: epoch ms; defaults to now.

        Returns:
            dict: the recorded {phase, at} entry. Never raises.
        """
        entry = {"phase": phase, "at": int(at_ms) if at_ms is not None else _now_ms()}
        self.timeline.append(entry)
        return entry

    def finish(self, outcome: str = "submitted") -> dict:
        """Close the trace: set outcome + durationMs (startedAt-based).

        Args:
            outcome: e.g. "submitted" | "failed" | "cancelled" | "skipped".

        Returns:
            dict: the final meta. Never raises.
        """
        self.meta["outcome"] = outcome
        self.meta["durationMs"] = max(0, _now_ms() - int(self.meta.get("startedAt", 0)))
        return dict(self.meta)

    def record_answer(self, field_id: str, label: str, kind: str, value, source: str,
                      required: bool, display: str | None = None,
                      options: list | None = None, reason: str | None = None) -> dict | None:
        """Record one form-question answer (recovered answer-entry shape).

        Args:
            field_id: field id (e.g. "basicInformation.firstName" or
                "questionnaire.300000742207382.300000281694968").
            label: question label.
            kind: one of FIELD_KINDS (text|email|phone|single_select|radio|file).
            value: answered value (option value for radio/single_select,
                text content otherwise, "" for skip, fallback text for fallback).
            source: one of ANSWER_SOURCES
                (profile-direct|llm|user-override|skip|fallback).
            required: whether the form marked the field required.
            display: human-readable rendering (for radio/single_select this is
                the chosen option's label). Defaults to "" for skip/fallback and
                str(value) otherwise — matching the recovered trace.
            options: [{label, value}, ...] for choice fields.
            reason: skip/fallback reason (e.g. conditional_skip_reason()).

        Returns:
            dict: the recorded answer entry, or None when the source is not in
            ANSWER_SOURCES (invalid input is never recorded; never raises).
        """
        if source not in ANSWER_SOURCES:
            return None
        if display is None:
            if source in ("skip", "fallback"):
                display = ""
            elif value is None:
                display = ""
            else:
                display = str(value)
        answer = {
            "fieldId": field_id,
            "label": label,
            "kind": kind if kind in FIELD_KINDS else "text",
            "source": source,
            "value": "" if value is None else value,
            "required": bool(required),
            "display": display,
        }
        if options:
            answer["options"] = options
        if reason is not None:
            answer["reason"] = reason
        self.answers.append(answer)
        return answer

    def answer_profile_direct(self, field_id: str, label: str, kind: str, value,
                              required: bool = True, options: list | None = None,
                              display: str | None = None) -> dict | None:
        """Record a profile-mapped answer (source=profile-direct)."""
        return self.record_answer(field_id, label, kind, value, "profile-direct",
                                  required, display=display, options=options)

    def answer_llm(self, field_id: str, label: str, kind: str, value,
                   required: bool = True, options: list | None = None,
                   display: str | None = None) -> dict | None:
        """Record an LLM-generated answer (source=llm).

        When value matches an option value, display defaults to that option's
        label (recovered semantics: value=option value, display=option label).
        """
        if display is None and options:
            for option in options:
                if isinstance(option, dict) and option.get("value") == value:
                    display = option.get("label")
                    break
        return self.record_answer(field_id, label, kind, value, "llm", required,
                                  display=display, options=options)

    def answer_skip(self, field_id: str, label: str, kind: str, parent_question_id: str,
                    parent_answer, trigger: str, required: bool = True,
                    options: list | None = None) -> dict | None:
        """Record a conditional-hidden skip (source=skip, reason auto-built)."""
        return self.record_answer(field_id, label, kind, "", "skip", required,
                                  display="", options=options,
                                  reason=conditional_skip_reason(parent_question_id, parent_answer, trigger))

    def answer_fallback(self, field_id: str, label: str, kind: str,
                        required: bool = True) -> dict | None:
        """Record the verbatim fallback answer (source=fallback)."""
        return self.record_answer(field_id, label, kind, FALLBACK_TEXT, "fallback",
                                  required, display=FALLBACK_TEXT, reason=FALLBACK_REASON)

    def add_derived_missing(self, field_id: str) -> None:
        """Record a field the form marked required but the profile lacks."""
        if field_id not in self.derivedMissingFields:
            self.derivedMissingFields.append(field_id)

    def sources_summary(self) -> dict:
        """Count answers per source (like the recovered histogram).

        Returns:
            dict: {source: count} for every ANSWER_SOURCES value. Never raises.
        """
        summary = {source: 0 for source in ANSWER_SOURCES}
        for answer in self.answers:
            source = answer.get("source")
            if source in summary:
                summary[source] += 1
        return summary

    def to_dict(self) -> dict:
        """Serialize the trace to the recovered API shape.

        Returns:
            dict: {meta, answers, timeline, derivedMissingFields}. Never raises.
        """
        return {
            "meta": dict(self.meta),
            "answers": list(self.answers),
            "timeline": list(self.timeline),
            "derivedMissingFields": list(self.derivedMissingFields),
        }

    def to_json(self) -> str:
        """Serialize the trace to compact JSON.

        Returns:
            str: compact JSON of to_dict(); "{}" on failure. Never raises.
        """
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return "{}"

    @classmethod
    def from_dict(cls, data: dict):
        """Rebuild a Trace from a serialized dict.

        Args:
            data: dict in to_dict() shape (or any subset).

        Returns:
            Trace with meta/answers/timeline restored; missing fields
            defaulted. Never raises.
        """
        meta = data.get("meta") if isinstance(data, dict) else None
        if isinstance(meta, dict) and "startedAt" in meta:
            trace = cls(ats=meta.get("ats", ""), outcome=meta.get("outcome", "pending"),
                        started_at_ms=meta.get("startedAt"))
            trace.meta["durationMs"] = meta.get("durationMs", 0)
        else:
            trace = cls()
        if isinstance(data, dict):
            if isinstance(data.get("answers"), list):
                trace.answers = [a for a in data["answers"] if isinstance(a, dict)]
            if isinstance(data.get("timeline"), list):
                trace.timeline = [t for t in data["timeline"] if isinstance(t, dict)]
            if isinstance(data.get("derivedMissingFields"), list):
                trace.derivedMissingFields = list(data["derivedMissingFields"])
        return trace

    @classmethod
    def from_json(cls, text: str):
        """Rebuild a Trace from a JSON string (empty/None -> fresh trace)."""
        if not text:
            return cls()
        try:
            data = json.loads(text)
        except Exception:
            return cls()
        return cls.from_dict(data if isinstance(data, dict) else {})
