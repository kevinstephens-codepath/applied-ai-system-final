"""Thin wrapper around the Gemini API (google-genai). Reads settings from the environment."""

import json
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tool_schemas import FINAL_TOOL_NAME, TOOL_NAMES, TOOL_SCHEMAS

DEFAULT_MODEL = "gemini-3.5-flash-lite"
TIMEOUT_MS = 30_000
TEMPERATURE = 0.2
RETRIES = 1  # extra attempts after a failed call (API error or unparseable reply)
RETRY_DELAY_S = 1.0
RETRY_NUDGE = (
    "\n\nYour previous reply could not be used. Reply with ONLY one JSON object, as plain text: "
    "either a tool call or a final answer. Do not use function-call syntax."
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMError(Exception):
    """The model could not be reached or returned something unusable.

    The message is safe to show to users. retryable is False for failures a retry cannot fix.
    """

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


QUOTA_MESSAGE = "The Gemini quota or rate limit was reached. Wait a while and try again."
AUTH_MESSAGE = "Gemini rejected the API key or model name. Check GEMINI_API_KEY and GEMINI_MODEL in .env."


def load_settings() -> tuple[str | None, str]:
    """Return (api_key, model) from the environment, loading .env if present."""
    load_dotenv()
    return os.environ.get("GEMINI_API_KEY") or None, os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, client=None,
                 retries: int = RETRIES, retry_delay_s: float = RETRY_DELAY_S):
        env_key, env_model = load_settings()
        self.model = model or env_model
        self._retries, self._retry_delay_s = retries, retry_delay_s
        if client is None:
            key = api_key or env_key
            if not key:
                raise LLMError("GEMINI_API_KEY is not set. Copy example.env to .env and add your key.")
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        self._client = client

    def generate_json(self, system_instruction: str, prompt: str) -> dict:
        """Send one prompt and parse the reply as a JSON object, retrying transient failures."""
        extra = {"response_mime_type": "application/json", "tool_config": _tool_config("NONE")}
        return self._run(system_instruction, prompt, extra, lambda r: parse_json_object(r.text, _finish_reason(r)))

    def generate_action(self, system_instruction: str, prompt: str, final_only: bool = False) -> dict:
        """Ask the model to pick one tool (or give its final answer) with native function calling.

        Returns {"action": name, "args": {...}} or {"action": "final", "answer": {...}}. Exactly one
        function call is forced each turn, which avoids replies that are empty or not a single object.
        """
        allowed = [FINAL_TOOL_NAME] if final_only else TOOL_NAMES
        extra = {
            "tools": [types.Tool(function_declarations=[types.FunctionDeclaration(**t) for t in TOOL_SCHEMAS])],
            "tool_config": _tool_config("ANY", allowed),
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        return self._run(system_instruction, prompt, extra, parse_action)

    def _run(self, system_instruction: str, prompt: str, extra_config: dict, parse) -> dict:
        for attempt in range(self._retries + 1):
            # A retry after a bad reply says what went wrong instead of repeating the same prompt.
            attempt_prompt = prompt if attempt == 0 else prompt + RETRY_NUDGE
            try:
                return self._once(system_instruction, attempt_prompt, extra_config, parse)
            except LLMError as exc:
                if not exc.retryable or attempt == self._retries:
                    raise
                time.sleep(self._retry_delay_s)

    def _once(self, system_instruction: str, prompt: str, extra_config: dict, parse) -> dict:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction, temperature=TEMPERATURE, **extra_config
        )
        try:
            response = self._client.models.generate_content(model=self.model, contents=prompt, config=config)
            result = parse(response)
        except LLMError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                raise LLMError(QUOTA_MESSAGE, retryable=False) from exc
            if code in (400, 401, 403, 404):
                raise LLMError(AUTH_MESSAGE, retryable=False) from exc
            raise LLMError(f"Gemini request failed ({type(exc).__name__}).") from exc
        return result


def _tool_config(mode: str, allowed: list[str] | None = None) -> types.ToolConfig:
    return types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
        mode=types.FunctionCallingConfigMode[mode], allowed_function_names=allowed))


def _plain(value):
    """Convert SDK containers to plain Python; whole-number floats (how function-call arguments
    arrive for integers) become ints so the tools' strict integer checks accept them."""
    if isinstance(value, dict) or hasattr(value, "items"):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def parse_action(response) -> dict:
    calls = getattr(response, "function_calls", None)
    if not calls:
        reason = _finish_reason(response)
        detail = f" (finish reason: {reason})" if reason and reason != "STOP" else ""
        raise LLMError(f"The model did not choose an action{detail}.")
    call = calls[0]  # one action per turn; later calls are asked for again on a later turn
    args = _plain(call.args or {})
    if call.name == FINAL_TOOL_NAME:
        return {"action": "final", "answer": args}
    return {"action": call.name, "args": args}


def _finish_reason(response) -> str | None:
    """Name of the first candidate's finish reason (e.g. STOP, MALFORMED_FUNCTION_CALL), if present."""
    candidates = getattr(response, "candidates", None)
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return getattr(reason, "name", None) or (str(reason) if reason else None)


def parse_json_object(text: str | None, finish_reason: str | None = None) -> dict:
    if not text or not text.strip():
        detail = f" (finish reason: {finish_reason})" if finish_reason and finish_reason != "STOP" else ""
        raise LLMError(f"The model returned an empty response{detail}.")
    try:
        data = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError as exc:
        raise LLMError("The model did not return valid JSON.") from exc
    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        # The model batched several actions into an array. The protocol is one action per turn,
        # so keep the first; it will ask for the rest on a later turn.
        data = data[0]
    if not isinstance(data, dict):
        raise LLMError("The model did not return a JSON object.")
    return data
