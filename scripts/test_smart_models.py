import os
import json
import urllib.request

def test_provider(name, base_url, api_key, models):
    print(f"\n=== Testing {name} ({base_url}) ===")
    if not api_key:
        print("No API key found.")
        return
    for model in models:
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Respond with exactly: SMARTEST MODEL READY"}],
            "max_tokens": 20
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"].strip()
                print(f"  [PASS] {model}: \"{content}\"")
        except Exception as e:
            print(f"  [FAIL] {model}: {e}")

# 1. Test OpenAI Direct
test_provider("OpenAI Direct", "https://api.openai.com/v1", os.environ.get("OPENAI_API_KEY"), ["gpt-4o", "gpt-4o-mini", "o1-mini", "gpt-4-turbo"])

# 2. Test Yunwu
test_provider("Yunwu AI", "https://yunwu.ai/v1", os.environ.get("YUNWU_API_KEY"), ["claude-3-5-sonnet-20241022", "claude-3-5-sonnet", "deepseek-chat", "deepseek-r1", "gpt-4o", "gemini-1.5-pro"])

# 3. Test Apilio
test_provider("Apilio", os.environ.get("APILIO_BASE_URL", "https://api.apilio.ai/v1"), os.environ.get("APILIO_API_KEY"), ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet"])
