"""Original batch writer call, with portable endpoint and credential settings."""
import json, urllib.request, urllib.error

def call_llm(port, system_prompt, user_prompt, temperature, max_tokens, timeout,
             profile=None):
    # MGL_LLM_PROFILES_V03 (TASK N Phase 2B): route on the writer profile's
    # kind. The default profile is the local qwen38 writer, so the default
    # path stays byte-identical (localhost + sk-local). An openai_api profile
    # rides its completions_url with a real cabinet key in the header — never
    # argv. Phase 2C adds the --llm selector; until then the default never
    # moves.
    settings, key = profile
    url = settings["writer_url"].rstrip("/") + "/chat/completions"
    auth = "Bearer " + (key or "sk-local")
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if settings.get("writer_model"):
        payload["model"] = settings["writer_model"]

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": auth,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return True, content, None
    except urllib.error.HTTPError as e:
        return False, None, f"Writer service rejected request (HTTP {e.code})"
    except Exception as e:
        return False, None, type(e).__name__
