"""Append-only JSONL log of every bug-analyzer request."""

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_PATH = Path(__file__).parent / "logs" / "analyzer.jsonl"
MAX_LOGGED_REPORT_CHARS = 2000


def build_record(report, result) -> dict:
    """One JSON-serializable record for an AnalysisResult. Contains no credentials by construction:
    only the report text, retrieval hits, tool calls, the answer, and the score."""
    answer = result.answer or {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "report": (report if isinstance(report, str) else repr(report))[:MAX_LOGGED_REPORT_CHARS],
        "status": result.status,
        "message": result.message,
        "input_note": result.input_note,
        "retrieved": [{"id": c.chunk_id, "source": c.source, "score": c.score} for c in result.chunks],
        "tool_calls": [{"tool": e["tool"], "args": e["args"], "ok": e["ok"], "error": e["error"]}
                       for e in result.tool_log],
        "steps": result.steps,
        "verdict": answer.get("verdict"),
        "cited_rules": answer.get("cited_rules"),
        "answer": result.answer,
        "debug_score": result.score.total,
        "band": result.score.band,
        "components": result.score.components,
        "confidence_note": result.confidence_note,
        "latency_ms": result.latency_ms,
    }


def log_analysis(report, result, path: Path | str = DEFAULT_LOG_PATH) -> bool:
    """Append one record. Returns False instead of raising if the log cannot be written."""
    try:
        record = build_record(report, result)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except (OSError, TypeError, ValueError):
        return False
