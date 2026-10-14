import os
import json
import urllib.request

base_url = "https://api.apilio.ai/v1"
api_key = os.environ.get("APILIO_API_KEY")

models = [
    "gpt-4o",
    "gpt-4o-2024-08-06",
    "chatgpt-4o-latest",
    "gpt-4-turbo",
    "o1-mini",
    "o1-preview",
    "claude-3-7-sonnet",
    "claude-3-5-sonnet",
    "claude-3-5-sonnet-20241022",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-v3",
    "deepseek-r1"
]

print("Testing Apilio frontier models...")
for m in models:
    url = f"{base_url}/chat/completions"
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 10
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode())
            txt = res["choices"][0]["message"]["content"].strip()
            print(f"  [PASS] {m}: {txt}")
    except Exception as e:
        print(f"  [FAIL] {m}: {str(e)[:45]}")
