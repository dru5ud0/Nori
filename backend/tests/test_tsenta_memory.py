"""Unit tests for tsenta_memory (Persistent Candidate Answer Memory Engine)."""

import os
import tempfile
from backend.src.tools.tsenta_memory import (
    normalize_question,
    load_memory,
    save_memory,
    seed_default_memory,
    remember_answer,
    remember_all_answers,
    recall_answer,
)


def test_normalize_question():
    q = "Do you currently reside in one of the following states: Arizona, California, Illinois*?"
    norm = normalize_question(q)
    assert "arizona" in norm
    assert "illinois" in norm
    assert "*" not in norm
    assert "?" not in norm


def test_seed_and_recall_signature():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {
            "personalInformation": {
                "firstName": "Drupadh",
                "lastName": "Suresh",
                "state": "IL",
            },
            "workAuthorization": {
                "needsSponsorship": False,
            }
        }
        seed_default_memory(profile, mem_path)
        
        # Test signature
        field = {"label": "Electronic Signature*", "kind": "text"}
        ans = recall_answer(field, profile, mem_path)
        assert ans is not None
        assert ans["value"] == "Drupadh Suresh"
        assert ans["source"] == "user-memory"


def test_seed_and_recall_referral_guard():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {
            "personalInformation": {
                "firstName": "Drupadh",
                "lastName": "Suresh",
            }
        }
        seed_default_memory(profile, mem_path)
        
        # Test employee referral: must NEVER be candidate's name
        field = {"label": "If Referred by an Agero Employee, please indicate their first and last name.", "kind": "text"}
        ans = recall_answer(field, profile, mem_path)
        assert ans is not None
        assert ans["value"] == "None"
        assert ans["value"] != "Suresh"


def test_seed_and_recall_state_residence():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {
            "personalInformation": {
                "firstName": "Drupadh",
                "lastName": "Suresh",
                "state": "IL",
            }
        }
        seed_default_memory(profile, mem_path)
        
        # Test state residence prompt where IL / Illinois is in the list
        field = {
            "label": "Do you currently reside in one of the following states: Arizona, California, Florida, Illinois, New York*?",
            "kind": "select",
            "options": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}]
        }
        ans = recall_answer(field, profile, mem_path)
        assert ans is not None
        assert ans["value"] == "Yes"


def test_seed_and_recall_sponsorship_options():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {
            "personalInformation": {
                "firstName": "Drupadh",
                "lastName": "Suresh",
            },
            "workAuthorization": {
                "needsSponsorship": False,
            }
        }
        seed_default_memory(profile, mem_path)
        
        # Test full-sentence options
        field = {
            "label": "Will you now or in the future require sponsorship for employment VISA status?",
            "kind": "select",
            "options": [
                {"value": "I am legally authorized to work in this country for any employer.", "label": "I am legally authorized to work in this country for any employer."},
                {"value": "I require sponsorship now or in the future.", "label": "I require sponsorship now or in the future."}
            ]
        }
        ans = recall_answer(field, profile, mem_path)
        assert ans is not None
        assert ans["value"] == "I am legally authorized to work in this country for any employer."


def test_remember_answer_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {"personalInformation": {"firstName": "Drupadh", "lastName": "Suresh"}}
        
        # Remember custom question
        success = remember_answer("What is your favorite cloud security tool?", "Prisma Cloud", "text", path=mem_path)
        assert success is True
        
        # Recall it
        field = {"label": "What is your favorite cloud security tool?", "kind": "text"}
        ans = recall_answer(field, profile, mem_path)
        assert ans is not None
        assert ans["value"] == "Prisma Cloud"
        assert ans["source"] == "user-memory"


def test_seed_and_recall_india_preferences():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {
            "personalInformation": {
                "firstName": "Drupadh",
                "lastName": "Suresh",
            },
            "workPreferences": {
                "noticePeriod": "30 days",
                "noticePeriodDays": 30,
                "servingNoticePeriod": False,
                "currentCTC": "12 LPA",
                "expectedCTC": "18 LPA",
                "preferredLocations": ["Bengaluru", "Hyderabad", "Pune"],
            }
        }
        seed_default_memory(profile, mem_path)

        # 1. Notice Period
        f_np = {"label": "What is your notice period (in days)?", "kind": "text"}
        ans_np = recall_answer(f_np, profile, mem_path)
        assert ans_np is not None
        assert "30" in ans_np["value"]

        # 2. Serving Notice Period
        f_serving = {
            "label": "Are you currently serving notice period?",
            "kind": "select",
            "options": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}]
        }
        ans_serving = recall_answer(f_serving, profile, mem_path)
        assert ans_serving is not None
        assert ans_serving["value"] == "No"

        # 3. Current CTC
        f_cctc = {"label": "Current CTC", "kind": "text"}
        ans_cctc = recall_answer(f_cctc, profile, mem_path)
        assert ans_cctc is not None
        assert "12" in ans_cctc["value"]

        # 4. Expected CTC
        f_ectc = {"label": "Expected CTC", "kind": "text"}
        ans_ectc = recall_answer(f_ectc, profile, mem_path)
        assert ans_ectc is not None
        assert "18" in ans_ectc["value"]

        # 5. Preferred Location
        f_loc = {
            "label": "Preferred Location",
            "kind": "select",
            "options": [
                {"value": "hyd", "label": "Hyderabad"},
                {"value": "blr", "label": "Bengaluru"}
            ]
        }
        ans_loc = recall_answer(f_loc, profile, mem_path)
        assert ans_loc is not None
        assert ans_loc["value"] == "blr"


def test_seed_and_recall_education_and_experience():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {
            "personalInformation": {"firstName": "Drupadh", "lastName": "Suresh"},
            "education": [{
                "degree": "M.S. Cybersecurity",
                "major": "Cybersecurity",
                "university": "DePaul University",
                "endDate": "2025-06"
            }],
            "workExperience": [{
                "role": "Cybersecurity Analyst",
                "company": "PNC Financial Services"
            }]
        }
        seed_default_memory(profile, mem_path)

        # Education
        f_edu = {
            "label": "Highest level of education completed",
            "kind": "select",
            "options": [
                {"value": "bachelors", "label": "Bachelor's Degree"},
                {"value": "masters", "label": "Master's Degree"}
            ]
        }
        ans_edu = recall_answer(f_edu, profile, mem_path)
        assert ans_edu is not None
        assert ans_edu["value"] == "masters"

        # Field of study
        f_major = {"label": "Field of study / Major", "kind": "text"}
        ans_major = recall_answer(f_major, profile, mem_path)
        assert ans_major is not None
        assert ans_major["value"] == "Cybersecurity"

        # Current employer
        f_emp = {"label": "Name of current employer", "kind": "text"}
        ans_emp = recall_answer(f_emp, profile, mem_path)
        assert ans_emp is not None
        assert ans_emp["value"] == "PNC Financial Services"

        # Total experience
        f_exp = {"label": "Total years of work experience", "kind": "text"}
        ans_exp = recall_answer(f_exp, profile, mem_path)
        assert ans_exp is not None
        assert "5" in ans_exp["value"]

        # Criminal history
        f_crim = {
            "label": "Have you ever been convicted of a felony?",
            "kind": "select",
            "options": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}]
        }
        ans_crim = recall_answer(f_crim, profile, mem_path)
        assert ans_crim is not None
        assert ans_crim["value"] == "No"


def test_remember_all_answers():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "answers_memory.json")
        profile = {"personalInformation": {"firstName": "Drupadh", "lastName": "Suresh"}}
        trace_answers = [
            {"label": "Favorite language", "value": "Python", "source": "llm", "kind": "text"},
            {"label": "Willing to travel", "value": "Yes", "source": "user-override", "kind": "select"},
            {"label": "Random skipped", "value": "", "source": "skip", "kind": "text"},
            {"label": "Fallback text", "value": "Please refer to my resume", "source": "fallback", "kind": "text"},
        ]
        saved = remember_all_answers(trace_answers, path=mem_path)
        assert saved == 2

        # Verify recalled
        f_lang = {"label": "Favorite language", "kind": "text"}
        ans_lang = recall_answer(f_lang, profile, mem_path)
        assert ans_lang is not None
        assert ans_lang["value"] == "Python"
        assert ans_lang["source"] == "user-memory"

