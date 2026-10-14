"""Execution capability registry tests."""

from backend.src.tools.tsenta_capabilities import (
    ats_capability, ats_capabilities, ats_can_prepare, ats_can_unattended_submit,
)
from backend.src.tools.tsenta_ats import ATS_CATALOG


def test_successfactors_is_dry_run_verified_with_account_gate():
    capability = ats_capability("successfactors")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_zohorecruit_is_dry_run_verified():
    capability = ats_capability("zohorecruit")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_ultipro_is_dry_run_verified_with_account_gate():
    capability = ats_capability("ultipro")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_avature_is_dry_run_verified_with_guest_preparation():
    capability = ats_capability("avature")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_phenom_live_dry_run_is_prepare_only():
    capability = ats_capability("phenom")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_hireology_accountless_form_is_dry_run_verified():
    capability = ats_capability("hireology")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_join_email_checkpoint_is_dry_run_verified_and_submit_disabled():
    capability = ats_capability("join")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_dover_public_form_is_dry_run_verified_and_submit_disabled():
    capability = ats_capability("dover")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_gem_public_form_is_dry_run_verified_and_submit_disabled():
    capability = ats_capability("gem")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_polymer_public_form_is_dry_run_verified_and_submit_disabled():
    capability = ats_capability("polymer")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_indeed_is_checkpoint_aware_and_dry_run_verified():
    capability = ats_capability("indeed")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_bullhorn_public_api_is_dry_run_verified_and_submit_guarded():
    capability = ats_capability("bullhorn")
    assert capability["detect"] is True
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False
    assert capability["confirmation"] == "structured-api"
    assert capability["persistentSession"] is False


def test_greenhouse_is_dry_run_verified_but_not_unattended_certified():
    capability = ats_capability("greenhouse")
    assert capability["prepare"] is True
    assert capability["level"] == "dry-run-verified"
    assert capability["unattendedSubmit"] is False
    assert ats_can_prepare("greenhouse") is True
    assert ats_can_unattended_submit("greenhouse") is False


def test_lever_is_dry_run_verified_with_receipt_contract():
    capability = ats_capability("lever")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_workday_is_dry_run_verified_with_persistent_session_and_receipt_contract():
    capability = ats_capability("workday")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_ashby_is_dry_run_verified_with_receipt_contract():
    capability = ats_capability("ashby")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_icims_is_dry_run_verified_with_receipt_contract():
    capability = ats_capability("icims")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_jazzhr_is_dry_run_verified_with_receipt_contract():
    capability = ats_capability("jazzhr")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_workable_is_dry_run_verified_with_receipt_contract():
    capability = ats_capability("workable")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_bamboohr_is_dry_run_verified_with_receipt_contract():
    capability = ats_capability("bamboohr")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_rippling_is_dry_run_verified_with_receipt_contract():
    capability = ats_capability("rippling")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is True
    assert capability["unattendedSubmit"] is False


def test_oraclecloud_is_dry_run_verified_with_consent_gate():
    capability = ats_capability("oraclecloud")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_breezyhr_is_dry_run_verified_without_live_receipt_evidence():
    capability = ats_capability("breezyhr")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_recruitee_is_dry_run_verified_without_live_receipt_evidence():
    capability = ats_capability("recruitee")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_teamtailor_is_dry_run_verified_without_live_receipt_evidence():
    capability = ats_capability("teamtailor")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["persistentSession"] is True
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_dayforce_public_guest_form_is_dry_run_verified():
    capability = ats_capability("dayforce")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False
    assert any("reCAPTCHA" in warning for warning in capability["warnings"])


def test_paylocity_multistep_form_is_dry_run_verified():
    capability = ats_capability("paylocity")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False
    assert any("acknowledgments" in warning for warning in capability["warnings"])


def test_generic_form_atses_are_dry_run_verified_until_host_receipt_is_verified():
    for ats in ("brassring", "adp", "paycom"):
        capability = ats_capability(ats)
        assert capability["level"] == "dry-run-verified"
        assert capability["prepare"] is True
        assert capability["receiptEvidence"] is False
        assert capability["unattendedSubmit"] is False


def test_pinpoint_is_dry_run_verified_without_live_receipt_evidence():
    capability = ats_capability("pinpoint")
    assert capability["level"] == "dry-run-verified"
    assert capability["prepare"] is True
    assert capability["receiptEvidence"] is False
    assert capability["unattendedSubmit"] is False


def test_catalog_has_one_truthful_entry_per_detected_ats():
    catalog = ats_capabilities()
    assert len(catalog) == len(ATS_CATALOG)
    assert len({item["ats"] for item in catalog}) == len(ATS_CATALOG)
