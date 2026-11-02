import json

from analysis_log import MAX_LOGGED_REPORT_CHARS, build_record, log_analysis
from debug_agent import AnalysisResult
from rag_retriever import Chunk
from scoring import DebugScore


def ok_result():
    return AnalysisResult(
        status="ok",
        answer={"verdict": "known_fixed_bug", "summary": "s", "root_cause": "r", "suggested_fix": "f",
                "cited_rules": ["B-10"], "code_evidence": [], "self_critique": "", "code_feedback": ""},
        score=DebugScore(82, "High", {"retrieval": 20.0, "citation": 20.0}),
        chunks=[Chunk("## B-10\ntext", "KNOWN_BUGS.md", "B-10", "B-10", "B-10", 0.4)],
        tool_log=[{"tool": "read_file", "args": {"path": "logic_utils.py"}, "ok": True, "error": None}],
        steps=3, latency_ms=1234,
    )


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_record_has_the_fields_the_plan_calls_for():
    record = build_record("score went negative", ok_result())
    assert record["report"] == "score went negative"
    assert record["status"] == "ok"
    assert record["retrieved"] == [{"id": "B-10", "source": "KNOWN_BUGS.md", "score": 0.4}]
    assert record["tool_calls"] == [{"tool": "read_file", "args": {"path": "logic_utils.py"}, "ok": True, "error": None}]
    assert (record["debug_score"], record["band"]) == (82, "High")
    assert record["verdict"] == "known_fixed_bug"
    assert record["cited_rules"] == ["B-10"]
    assert record["latency_ms"] == 1234
    assert record["timestamp"].endswith("+00:00")


def test_appends_one_json_line_per_request_and_creates_directory(tmp_path):
    path = tmp_path / "nested" / "analyzer.jsonl"
    assert log_analysis("first report", ok_result(), path) is True
    assert log_analysis("second report", AnalysisResult(status="no_context", message="nope"), path) is True
    records = read_lines(path)
    assert [r["report"] for r in records] == ["first report", "second report"]
    assert records[1]["status"] == "no_context"
    assert records[1]["answer"] is None and records[1]["verdict"] is None
    assert records[1]["debug_score"] == 0


def test_report_with_newlines_and_unicode_stays_on_one_line(tmp_path):
    path = tmp_path / "a.jsonl"
    log_analysis("line one\nline two 🎮", ok_result(), path)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert read_lines(path)[0]["report"] == "line one\nline two 🎮"


def test_long_report_truncated(tmp_path):
    path = tmp_path / "a.jsonl"
    log_analysis("x" * 10_000, ok_result(), path)
    assert len(read_lines(path)[0]["report"]) == MAX_LOGGED_REPORT_CHARS


def test_non_string_report_does_not_crash(tmp_path):
    path = tmp_path / "a.jsonl"
    assert log_analysis(None, AnalysisResult(status="rejected", message="empty"), path) is True
    assert read_lines(path)[0]["report"] == "None"


def test_unwritable_log_returns_false_instead_of_raising(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    assert log_analysis("report", ok_result(), blocker / "analyzer.jsonl") is False


def test_api_key_is_never_in_the_record(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    path = tmp_path / "a.jsonl"
    log_analysis("report", ok_result(), path)
    assert "super-secret-value" not in path.read_text(encoding="utf-8")
