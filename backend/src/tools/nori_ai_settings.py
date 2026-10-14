"""Local AI-provider settings; credentials are encrypted with Windows DPAPI."""
import json
from urllib.parse import urlsplit
from backend.src.tools.nori_gmail import WindowsDPAPISecretStore


def _load_provider() -> dict:
    try:
        return json.loads(WindowsDPAPISecretStore().get('nori.ai.provider') or '{}')
    except Exception:
        return {}


def save_ai_provider(base_url: str, model: str, api_key: str = '', transport: str = 'api') -> str:
    """Save an HTTPS chat provider and optional replacement key.

    Args:
        base_url: trusted provider's HTTPS API root (normally ending /v1).
        model: exact supported model id.
        api_key: replacement credential; blank preserves the saved key only
            when the provider hostname is unchanged.
        transport: api or chatgpt (managed Codex sign-in, no API key).

    Returns:
        str: token-free JSON {ok, error}. Never raises.
    """
    try:
        if transport == 'chatgpt':
            WindowsDPAPISecretStore().set('nori.ai.provider', json.dumps({
                'transport': 'chatgpt', 'model': model.strip(), 'api_key': '', 'base_url': ''}))
            return json.dumps({'ok': True, 'error': ''})
        parsed = urlsplit(base_url.strip())
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use the provider’s HTTPS API root, without credentials or query parameters.')
        if not model.strip():
            raise ValueError('Enter the provider’s model ID.')
        previous = _load_provider()
        key = api_key.strip()
        if not key and urlsplit(previous.get('base_url', '')).hostname == parsed.hostname:
            key = previous.get('api_key', '')
        if not key:
            raise ValueError('Enter an API key for this provider. Environment keys are never copied to a different provider.')
        WindowsDPAPISecretStore().set('nori.ai.provider', json.dumps({
            'transport': 'api', 'base_url': base_url.strip().rstrip('/'), 'model': model.strip(), 'api_key': key}))
        return json.dumps({'ok': True, 'error': ''})
    except Exception as exc:
        return json.dumps({'ok': False, 'error': str(exc).replace(api_key, '[redacted]') if api_key else str(exc)})
