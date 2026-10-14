"""tsenta_vault — Tsenta-style candidate credential vault for employer accounts."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_VAULT_LOCK = threading.Lock()
_DEFAULT_VAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'loot', 'state', 'employer_accounts.json')
_SETTINGS_PATH = os.path.join(os.path.dirname(_DEFAULT_VAULT_PATH), 'settings.json')


ALIAS_DOMAINS = {}


def get_default_password() -> str:
    """Return the default candidate application password."""
    env_pw = os.environ.get('NORI_DEFAULT_PASSWORD', '')
    if env_pw:
        return env_pw
    try:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                pw = settings.get('defaultApplicationPassword', '')
                if pw:
                    return pw
    except Exception:
        pass

    return 'NoriApply2026!Secure'


def get_employer_account(ats: str, domain: str, vault_path: str | None = None) -> dict | None:
    """Look up stored candidate account credentials for an employer portal."""
    path = vault_path or _DEFAULT_VAULT_PATH
    try:
        if not os.path.exists(path):
            return None
        with _VAULT_LOCK, open(path, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
            key = f"{ats.lower()}:{domain.lower()}"
            return accounts.get(key)
    except Exception:
        return None


def save_employer_account(ats: str, domain: str, email: str, password: str, vault_path: str | None = None) -> bool:
    """Record a created candidate account for an employer portal."""
    path = vault_path or _DEFAULT_VAULT_PATH
    try:
        with _VAULT_LOCK:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            accounts = {}
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        accounts = json.load(f)
                except Exception:
                    accounts = {}
            key = f'{ats.lower()}:{domain.lower()}'
            accounts[key] = {
                'ats': ats.lower(),
                'domain': domain.lower(),
                'email': email,
                'password': password,
                'updatedAt': int(__import__('time').time() * 1000)
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(accounts, f, indent=2)
            return True
    except Exception:
        return False
