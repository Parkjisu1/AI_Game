import os, requests
mk = os.environ.get("LITELLM_MASTER_KEY", "")
if not mk:
    print("ERROR: LITELLM_MASTER_KEY not set")
    raise SystemExit(1)
for model in ["gpt-4o-mini", "sub-coder-agent", "validator-agent"]:
    try:
        r = requests.post(
            "http://localhost:4000/v1/chat/completions",
            headers={"Authorization": f"Bearer {mk}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "reply one word: OK"}],
                "max_tokens": 5,
            },
            timeout=20,
        )
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {}).get(
            "content", f"ERROR {r.status_code}: {str(data)[:200]}"
        )
        print(f"  {model:20} → {msg}")
    except Exception as e:
        print(f"  {model:20} → EXCEPTION: {e}")
