"""Tests for tsenta_vault credential store."""
import json
import pytest

from backend.src.tools.tsenta_vault import (
    get_default_password,
    get_employer_account,
    save_employer_account,
)


def test_default_password_fallback():
    pw = get_default_password()
    assert isinstance(pw, str)
    assert len(pw) >= 8


def test_save_and_get_employer_account(tmp_path):
    vault_file = str(tmp_path / "accounts.json")
    saved = save_employer_account(
        ats="workday",
        domain="keybank.myworkdayjobs.com",
        email="alex.taylor.career@gmail.com",
        password="TestSecretPassword123!",
        vault_path=vault_file
    )
    assert saved is True

    record = get_employer_account(
        ats="workday",
        domain="keybank.myworkdayjobs.com",
        vault_path=vault_file
    )
    assert record is not None
    assert record["email"] == "alex.taylor.career@gmail.com"
    assert record["password"] == "TestSecretPassword123!"

    # Case insensitivity
    record_upper = get_employer_account(
        ats="WORKDAY",
        domain="KEYBANK.MYWORKDAYJOBS.COM",
        vault_path=vault_file
    )
    assert record_upper is not None
    assert record_upper["password"] == "TestSecretPassword123!"

    # Non-existent
    missing = get_employer_account(
        ats="adp",
        domain="unknown.adp.com",
        vault_path=vault_file
    )
    assert missing is None
