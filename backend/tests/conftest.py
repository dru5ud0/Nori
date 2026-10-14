"""Offline tests must not use the developer's saved provider or paid credentials."""
import pytest


@pytest.fixture(autouse=True)
def isolate_personal_ai_settings(monkeypatch, request):
    if request.node.get_closest_marker('live'):
        return
    from backend.src.tools import nori_ai_settings
    monkeypatch.setattr(nori_ai_settings, '_load_provider', lambda: {})
    monkeypatch.delenv('YUNWU_API_KEY', raising=False)
