"""Shared MiniMax chat-completion client with defensive response parsing.

Every caller previously did `r.json()["choices"][0]["message"]["content"]`.
When the API returns an error payload (rate limit, exhausted token plan,
auth failure, upstream 5xx) that raises KeyError: 'choices', which surfaces
as a bare "ERROR 'choices'" in the reports and hides the real cause.

This module returns (text, error) so callers can log what actually went
wrong instead of a dictionary key.
"""

import os

import requests

API_URL = os.environ.get(
    "MINIMAX_CHAT_URL", "https://api.minimax.io/v1/chat/completions"
)
MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")


def _first_error(payload):
    """Pull a human-readable message out of a MiniMax/OpenAI error body."""
    if not isinstance(payload, dict):
        return f"non-JSON response: {str(payload)[:200]}"
    base = payload.get("base_resp")
    if isinstance(base, dict):
        msg = base.get("status_msg") or base.get("msg")
        code = base.get("status_code")
        if msg:
            return f"API status {code}: {msg}"
    err = payload.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("msg") or json_dumps(err)
        return f"API error {err.get('code', '?')}: {msg}"
    if err:
        return f"API error: {err}"
    if "message" in payload:
        return f"API message: {payload['message']}"
    if "choices" in payload:
        return "empty choices array (model returned no candidates)"
    return f"unexpected payload keys: {sorted(payload.keys())}"


def json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)[:200]


def chat(prompt, system="", max_tokens=2048, temperature=0.2, timeout=45):
    """Call the chat endpoint. Returns (content_text, error_string)."""
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        return "", "MINIMAX_API_KEY not set"

    try:
        r = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": MODEL,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {
                        "role": "system",
                        "content": system
                        or "你是策略 sub-agent。直接輸出 GRADE/CONFIDENCE/REASON + suggested_params。",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=timeout,
        )
    except Exception as e:  # network / DNS / timeout
        return "", f"request failed: {type(e).__name__}: {e}"

    if r.status_code != 200:
        return "", f"HTTP {r.status_code}: {r.text[:300]}"

    try:
        payload = r.json()
    except Exception as e:
        return "", f"bad JSON ({type(e).__name__}): {r.text[:200]}"

    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        return "", _first_error(payload)

    try:
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        return "", f"malformed choices entry ({type(e).__name__}: {e})"

    if not content or not content.strip():
        return "", "empty completion content"
    return content.strip(), ""
