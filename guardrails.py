"""Input and output guardrails for the bug analyzer."""

import re
from dataclasses import dataclass

MIN_INPUT_CHARS = 10
MAX_INPUT_CHARS = 2000
MAX_FIELD_CHARS = 1500
MIN_ALPHA_RATIO = 0.4
MIN_WORDS = 3

VERDICTS = ("bug", "known_fixed_bug", "correct_behavior", "not_covered")
REQUIRED_FIELDS = ("verdict", "summary", "root_cause", "suggested_fix", "cited_rules")
TEXT_FIELDS = ("summary", "root_cause", "suggested_fix")

NO_CONTEXT_MESSAGE = (
    "I don't have enough information in the game's spec or bug history to diagnose this. "
    "Try describing what you did, what you expected, and what the game actually did."
)
LOW_CONFIDENCE_NOTE = (
    "Low confidence: treat this diagnosis as a lead to check, not a conclusion."
)

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|prompts?|rules)",
        r"disregard\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier|your)\s+(?:instructions|prompts?|rules)",
        r"forget\s+(?:all\s+|everything\s+)?(?:previous|prior|above|your)\s+(?:instructions|prompts?|rules)",
        r"you\s+are\s+now\s+(?:a|an|in)\b",
        r"(?:reveal|print|show|repeat|leak)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)",
        r"\bsystem\s+prompt\b",
        r"gemini_api_key|api[_\s-]?key",
    )
]
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANK_RUNS = re.compile(r"\n{3,}")


def validate_input(raw: str | None) -> tuple[bool, str, str | None]:
    """Check a bug report before it goes anywhere near retrieval or the LLM.

    Returns (ok, cleaned_text, message). When ok is False the message says why. When ok is
    True the message is None, or a note if the text was truncated. This is only a coarse
    filter: reports that are well-formed but off-topic pass here and are handled by the
    retriever returning no context.
    """
    if not isinstance(raw, str) or not raw.strip():
        return False, "", "Describe the bug you saw: what you did, what you expected, what happened."

    text = _BLANK_RUNS.sub("\n\n", _CONTROL_CHARS.sub("", raw)).strip()

    if len(text) < MIN_INPUT_CHARS:
        return False, text, f"That is too short to analyze. Please write at least {MIN_INPUT_CHARS} characters."

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return False, "", "That looks like an instruction to the AI or a request for secrets, not a bug report."

    visible = [ch for ch in text if not ch.isspace()]
    alpha_ratio = sum(ch.isalpha() for ch in visible) / len(visible)
    words = re.findall(r"[A-Za-z]{2,}", text)
    if alpha_ratio < MIN_ALPHA_RATIO or len(words) < MIN_WORDS or len({w.lower() for w in words}) < 2:
        return False, "", "That does not look like a bug description. Please describe the problem in words."

    note = None
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
        note = f"Your report was longer than {MAX_INPUT_CHARS} characters, so it was truncated."
    return True, text, note


@dataclass(frozen=True)
class OutputCheck:
    ok: bool
    result: dict | None
    message: str | None
    reason: str | None


def _refuse(message: str, reason: str) -> OutputCheck:
    return OutputCheck(False, None, message, reason)


def check_output(result, chunks) -> OutputCheck:
    """Validate the model's structured answer against what was actually retrieved.

    With no retrieved chunks the model is never trusted: the answer is refused. Otherwise the
    answer must have the required fields, a known verdict, and every cited rule must be a
    chunk that was retrieved (invented citations are dropped). Unless the verdict is
    "not_covered", at least one valid citation must remain. Long text is truncated.
    """
    if not chunks:
        return _refuse(NO_CONTEXT_MESSAGE, "no_context")
    if not isinstance(result, dict):
        return _refuse("The analyzer returned an unusable answer. Please try again.", "malformed")
    if any(f not in result for f in REQUIRED_FIELDS):
        return _refuse("The analyzer returned an incomplete answer. Please try again.", "malformed")
    if result["verdict"] not in VERDICTS:
        return _refuse("The analyzer returned an unusable answer. Please try again.", "bad_verdict")
    if not all(isinstance(result[f], str) and result[f].strip() for f in TEXT_FIELDS):
        return _refuse("The analyzer returned an incomplete answer. Please try again.", "malformed")
    if not isinstance(result["cited_rules"], list):
        return _refuse("The analyzer returned an unusable answer. Please try again.", "malformed")

    retrieved_ids = {c.chunk_id for c in chunks}
    cited = [c for c in dict.fromkeys(r for r in result["cited_rules"] if isinstance(r, str)) if c in retrieved_ids]
    if not cited and result["verdict"] != "not_covered":
        return _refuse(NO_CONTEXT_MESSAGE, "no_valid_citation")

    cleaned = dict(result)
    cleaned["cited_rules"] = cited
    for field in TEXT_FIELDS:
        cleaned[field] = cleaned[field].strip()[:MAX_FIELD_CHARS]
    return OutputCheck(True, cleaned, None, None)


def confidence_note(band: str | None) -> str | None:
    """Caveat shown with the answer when the debug score band is Low."""
    return LOW_CONFIDENCE_NOTE if band == "Low" else None
