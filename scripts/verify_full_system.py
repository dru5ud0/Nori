import sys
import os
import json
import time

# Add paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend", "src"))
sys.path.insert(0, os.path.join(ROOT, "backend", "src", "tools"))

def test_imports():
    print("[1/6] Testing Core Engine Imports...")
    from backend.src.tools.tsenta_ats import ats_detect, ats_display_name, ats_extract_candidates
    from backend.src.tools.tsenta_capabilities import ats_capabilities, ats_can_prepare
    from backend.src.tools.tsenta_profiles import empty_profile, profile_from_json, validate_profile
    from backend.src.tools.tsenta_config import default_config
    from backend.src.tools.tsenta_trace import Trace
    from backend.src.tools.tsenta_apply import collect_fields, answer_fields
    from backend.src.tools.tsenta_pipeline import list_jobs, jobs_summary, create_job
    from backend.src.tools.tsenta_documents import cover_letter_document, resume_summary_document
    from backend.src.tools.tsenta_feed import fetch_feed
    print("  -> All core modules imported successfully.")
    return True

def test_ats_detection():
    print("[2/6] Testing ATS Detection Engine across 10 sample platforms...")
    from backend.src.tools.tsenta_ats import ats_detect, ats_display_name
    test_urls = [
        ("https://boards.greenhouse.io/datadog/jobs/12345", "greenhouse"),
        ("https://jobs.lever.co/netflix/67890", "lever"),
        ("https://mycompany.wd5.myworkdayjobs.com/Careers/job/123", "workday"),
        ("https://jobs.ashbyhq.com/vanta/abc-123", "ashby"),
        ("https://jobs.smartrecruiters.com/Acme/456", "smartrecruiters"),
        ("https://jobs.bamboohr.com/company/jobs/view.php?id=789", "bamboohr"),
        ("https://apply.workable.com/acme/j/DEF123/", "workable"),
        ("https://jobs.jobvite.com/acme/job/o123", "jobvite"),
        ("https://acme.breezy.hr/p/ghi456", "breezyhr"),
        ("https://careers.phenompeople.com/job/123", "phenom")
    ]
    all_matched = True
    for url, expected_ats in test_urls:
        det = ats_detect(url)
        name = ats_display_name(det["ats_id"])
        matched = (det["ats_id"] == expected_ats)
        if not matched:
            all_matched = False
            print(f"  FAILED: {url} -> got {det['ats_id']}, expected {expected_ats}")
        else:
            print(f"  PASSED: {expected_ats} detected (rule={det['rule']}, conf={det['confidence']})")
    assert all_matched, "Some ATS detections failed"
    return True

def test_profile_and_validation():
    print("[3/6] Testing Profile & Schema Validation...")
    from backend.src.tools.tsenta_profiles import profile_from_json, validate_profile, safe_eeo_profile
    
    # Load profile.example.json
    example_path = os.path.join(ROOT, "loot", "state", "profile.example.json")
    with open(example_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    profile = profile_from_json(data)
    missing = validate_profile(profile)
    print(f"  -> Validated example profile: {len(missing)} missing fields identified.")
    
    safe = safe_eeo_profile(profile)
    assert safe is not None
    print("  -> EEO safe defaults applied successfully.")
    return True

def test_webapp_api():
    print("[4/6] Testing FastAPI Webapp API Endpoints...")
    from fastapi.testclient import TestClient
    from webapp.server import app

    client = TestClient(app)

    # 1. Bootstrap
    res = client.get("/api/dashboard/bootstrap")
    assert res.status_code == 200, f"Bootstrap returned {res.status_code}"
    body = res.json()
    assert "profile" in body and "counts" in body
    print("  -> /api/dashboard/bootstrap: 200 OK")

    # 2. ATS list
    res = client.get("/api/atses")
    assert res.status_code == 200
    data = res.json()
    atses = data if isinstance(data, list) else data.get("atses", [])
    assert len(atses) >= 30, f"Expected 30+ ATSes, got {len(atses)}"
    print(f"  -> /api/atses: 200 OK ({len(atses)} supported ATS engines verified)")

    # 3. Settings
    res = client.get("/api/settings")
    assert res.status_code == 200
    print("  -> /api/settings: 200 OK")

    # 4. Root HTML (SPA)
    res = client.get("/")
    assert res.status_code == 200
    assert "<!doctype html>" in res.text.lower()
    print("  -> / (Single Page App index.html): 200 OK")
    return True

def test_cli():
    print("[5/6] Testing CLI Command Dispatch...")
    import subprocess
    cmd = [sys.executable, "-m", "backend.src.tools.tsenta_cli", "summary"]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, f"CLI summary failed: {p.stderr}"
    print(f"  -> tsenta-cli summary: OK\n     {p.stdout.strip()}")
    return True

def test_document_generator():
    print("[6/6] Testing Document Generator...")
    from backend.src.tools.tsenta_documents import cover_letter_document
    from backend.src.tools.tsenta_profiles import empty_profile
    p = empty_profile()
    p["personalInformation"]["firstName"] = "Alex"
    p["personalInformation"]["lastName"] = "Taylor"
    job = {"company": "Acme Corp", "title": "Security Analyst"}
    doc = cover_letter_document(p, job)
    content = doc.get("coverLetterText", "")
    assert "Alex Taylor" in content
    print(f"  -> Deterministic cover letter generation: OK (length={len(content)} chars)")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("NORI AI / TSENTA-CLONE END-TO-END VERIFICATION")
    print("=" * 60)
    test_imports()
    test_ats_detection()
    test_profile_and_validation()
    test_webapp_api()
    test_cli()
    test_document_generator()
    print("=" * 60)
    print("ALL 6 END-TO-END SUBSYSTEMS VERIFIED HEALTHY & WORKING!")
    print("=" * 60)
