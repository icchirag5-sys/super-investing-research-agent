"""Minimal LLM client (standard library only).

Providers
---------
gemini     Google Gemini API (free tier available via Google AI Studio). Key: GEMINI_API_KEY
anthropic  Anthropic Messages API (paid). Key: ANTHROPIC_API_KEY

API keys are read from environment variables only; nothing is hardcoded.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_MODELS = {
    "gemini": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
}
KEY_ENV = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
KEY_HELP = {
    "gemini": "Create a free key at https://aistudio.google.com/apikey",
    "anthropic": "Create a key at https://console.anthropic.com/ (paid account required)",
}


class LLMError(Exception):
    """Any model/credential problem. The message is user-facing."""


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def get_api_key(provider: str) -> str:
    if provider not in KEY_ENV:
        raise LLMError(f"Unknown provider '{provider}'. Choose from: {', '.join(KEY_ENV)}.")
    key = os.environ.get(KEY_ENV[provider], "").strip()
    if not key:
        raise LLMError(
            f"{KEY_ENV[provider]} is not set. {KEY_HELP[provider]}\n"
            f"Then add it to a .env file (copy .env.example) or run: export {KEY_ENV[provider]}=your_key"
        )
    return key


def _post(url: str, headers: dict, payload: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
    last_err = ""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(2 ** (attempt + 1) * 2)           # 4s, 8s, 16s
                last_err = f"HTTP {e.code}"
                continue
            raise LLMError(_explain_http_error(e.code, body)) from e
        except urllib.error.URLError as e:
            raise LLMError(f"Network error reaching the model API: {e.reason}. Check your internet connection.") from e
    raise LLMError(f"Model API kept failing after retries ({last_err}). Wait a minute and try again.")


def _explain_http_error(code: int, body: str) -> str:
    hints = {
        400: "Bad request, or the API key is invalid. Re-check the key value and the model name.",
        401: "Authentication failed. The API key is missing, wrong or revoked.",
        403: "Access denied. The key may lack permission, or the model is not available to your account/region.",
        404: "Model not found. Set GEMINI_MODEL / ANTHROPIC_MODEL (or --model) to a model your key can use.",
        429: "Rate limit or quota reached (common on free tiers). Wait a few minutes, or try a smaller model.",
    }
    return f"Model API returned HTTP {code}. {hints.get(code, 'Unexpected error.')}\nDetails: {body}"


def _gemini(system: str, user: str, model: str, temperature: float, max_tokens: int) -> LLMResult:
    key = get_api_key("gemini")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    out = _post(url, {"x-goog-api-key": key}, payload)
    try:
        cand = out["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError, TypeError) as e:
        reason = (out.get("promptFeedback") or {}).get("blockReason") or json.dumps(out)[:300]
        raise LLMError(f"Gemini returned no text (reason: {reason}).") from e
    if not text.strip():
        raise LLMError(f"Gemini returned empty text (finishReason: {cand.get('finishReason')}).")
    usage = out.get("usageMetadata", {})
    return LLMResult(text, model, "gemini", usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))


def _anthropic(system: str, user: str, model: str, temperature: float, max_tokens: int) -> LLMResult:
    key = get_api_key("anthropic")
    payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
               "system": system, "messages": [{"role": "user", "content": user}]}
    out = _post("https://api.anthropic.com/v1/messages",
                {"x-api-key": key, "anthropic-version": "2023-06-01"}, payload)
    text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise LLMError("Anthropic returned empty text.")
    usage = out.get("usage", {})
    return LLMResult(text, model, "anthropic", usage.get("input_tokens"), usage.get("output_tokens"))


def generate(provider: str, system: str, user: str, model: str | None = None,
             temperature: float = 0.2, max_tokens: int = 8192) -> LLMResult:
    """Call the chosen provider. Raises LLMError with a helpful message on any failure."""
    get_api_key(provider)                      # fail fast, before any network traffic
    model = model or DEFAULT_MODELS[provider]
    fn = _gemini if provider == "gemini" else _anthropic
    return fn(system, user, model, temperature, max_tokens)
