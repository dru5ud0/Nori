"""Check the configured provider without printing credentials or personal data."""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.src.tools.tsenta_llm import llm_config


def main():
    cfg = llm_config()
    token = cfg.get('api_key') or ''
    body = json.dumps({'model': cfg['model'], 'messages': [{'role': 'user', 'content': 'Reply with OK.'}], 'max_tokens': 1000}).encode()
    request = urllib.request.Request(cfg['base_url'] + '/chat/completions', data=body,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode())
        choice = (result.get('choices') or [{}])[0]
        print(json.dumps({'ok': bool((choice.get('message') or {}).get('content')),
            'model': cfg['model'], 'finishReason': choice.get('finish_reason'),
            'answer': (choice.get('message') or {}).get('content', '')[:100]}))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors='replace').replace(token, '[redacted]')
        print(json.dumps({'ok': False, 'httpStatus': exc.code, 'detail': detail[:500]}))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc).replace(token, '[redacted]')}))


if __name__ == '__main__':
    main()
