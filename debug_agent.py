"""Bounded agent loop: validate -> retrieve -> (model asks for tools, one per turn) -> final -> check -> score.

The model never executes anything itself. Each turn it makes one function call naming a tool from
agent_tools.ToolBox, or the final answer; this module runs the tool and feeds the result back.
"""

import json
import time
from dataclasses import dataclass, field

from agent_tools import ToolBox
from guardrails import NO_CONTEXT_MESSAGE, check_output, confidence_note, validate_input
from llm_client import LLMError
from prompts import AGENT_SYSTEM_PROMPT, build_agent_prompt
from scoring import DebugScore, compute_debug_score, empty_score, evidence_is_valid

MAX_STEPS = 6
MAX_OBSERVATION_CHARS = 12_000
MAX_EVIDENCE = 5
MAX_NOTE_CHARS = 1000

LLM_ERROR_SUFFIX = "The closest matching documentation is shown instead."
UNFINISHED_MESSAGE = "The analyzer could not finish its analysis. Please try again or rephrase the report."


@dataclass
class AnalysisResult:
    status: str  # ok | rejected | no_context | refused | llm_error | unfinished
    message: str | None = None  # user-facing text when status is not "ok"
    answer: dict | None = None
    score: DebugScore = field(default_factory=empty_score)
    confidence_note: str | None = None
    input_note: str | None = None
    chunks: list = field(default_factory=list)
    tool_log: list = field(default_factory=list)
    steps: int = 0
    latency_ms: int = 0


def _shorten(result: dict) -> dict:
    text = json.dumps(result)
    return result if len(text) <= MAX_OBSERVATION_CHARS else {"truncated": text[:MAX_OBSERVATION_CHARS]}


def _clean_evidence(raw) -> list[dict]:
    """Keep the model's code_evidence entries in a fixed shape. Malformed entries are kept (as
    invalid ones) so they cannot be dropped to improve the score."""
    if not isinstance(raw, list):
        return []
    cleaned = []
    for entry in raw[:MAX_EVIDENCE]:
        if isinstance(entry, dict):
            cleaned.append({"file": str(entry.get("file"))[:200],
                            "start_line": entry.get("start_line"), "end_line": entry.get("end_line")})
        else:
            cleaned.append({"file": str(entry)[:200], "start_line": None, "end_line": None})
    return cleaned


def _note(value) -> str:
    return value.strip()[:MAX_NOTE_CHARS] if isinstance(value, str) else ""


def analyze(report, retriever, llm, toolbox: ToolBox | None = None, max_steps: int = MAX_STEPS) -> AnalysisResult:
    """Analyze one bug report. llm needs generate_action(system_instruction, prompt, final_only) -> dict."""
    started = time.monotonic()

    def finish(**fields) -> AnalysisResult:
        fields["latency_ms"] = round((time.monotonic() - started) * 1000)
        return AnalysisResult(**fields)

    ok, cleaned, message = validate_input(report)
    if not ok:
        return finish(status="rejected", message=message)
    input_note = message

    chunks = retriever.search(cleaned)
    if not chunks:
        return finish(status="no_context", message=NO_CONTEXT_MESSAGE, input_note=input_note)

    toolbox = toolbox or ToolBox()
    observations: list[dict] = []
    final = None
    steps = 0
    for step in range(1, max_steps + 1):
        steps = step
        prompt = build_agent_prompt(cleaned, chunks, observations, max_steps - step + 1)
        try:
            turn = llm.generate_action(AGENT_SYSTEM_PROMPT, prompt, final_only=(step == max_steps))
        except LLMError as exc:
            return finish(status="llm_error", message=f"{exc} {LLM_ERROR_SUFFIX}", chunks=chunks,
                          tool_log=toolbox.log, steps=steps, input_note=input_note)
        action = turn.get("action")
        if action == "final":
            final = turn.get("answer")
            break
        if step == max_steps:  # the last turn must be a final answer
            break
        if isinstance(action, str):
            args = turn.get("args", {})
            result = toolbox.call(action, args)
        else:
            args, result = None, {"error": "Missing action. Respond with a tool call or a final answer."}
        observations.append({"step": step, "action": action, "args": args, "result": _shorten(result)})

    if final is None:
        return finish(status="unfinished", message=UNFINISHED_MESSAGE, chunks=chunks,
                      tool_log=toolbox.log, steps=steps, input_note=input_note)

    check = check_output(final, chunks)
    if not check.ok:
        return finish(status="refused", message=check.message, chunks=chunks,
                      tool_log=toolbox.log, steps=steps, input_note=input_note)

    answer = check.result
    evidence = _clean_evidence(final.get("code_evidence"))
    answer["code_evidence"] = [
        {**e, "verified": evidence_is_valid(e, toolbox.files_read, toolbox.ranges_read)} for e in evidence
    ]
    answer["self_critique"] = _note(final.get("self_critique"))
    answer["code_feedback"] = _note(final.get("code_feedback"))

    claimed = list(dict.fromkeys(c for c in final["cited_rules"] if isinstance(c, str)))
    score = compute_debug_score(chunks, claimed, answer["cited_rules"], answer["verdict"], evidence,
                                toolbox.log, toolbox.files_read, toolbox.ranges_read)
    return finish(status="ok", answer=answer, score=score, confidence_note=confidence_note(score.band),
                  input_note=input_note, chunks=chunks, tool_log=toolbox.log, steps=steps)
