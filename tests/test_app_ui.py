from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import analyzer_ui
from debug_agent import AnalysisResult
from llm_client import LLMError
from rag_retriever import Chunk
from scoring import DebugScore

APP = str(Path(__file__).parent.parent / "app.py")


def ok_result(band="High", total=88):
    return AnalysisResult(
        status="ok",
        answer={"verdict": "known_fixed_bug", "summary": "Decimals used to be truncated.",
                "root_cause": "Old code truncated floats.", "suggested_fix": "No change needed",
                "cited_rules": ["B-06"],
                "code_evidence": [{"file": "logic_utils.py", "start_line": 13, "end_line": 27, "verified": True},
                                  {"file": "app.py", "start_line": 1, "end_line": 9, "verified": False}],
                "self_critique": "Did not run the UI.", "code_feedback": "Add a test for ranges."},
        score=DebugScore(total, band, {"retrieval": 20.0, "citation": 20.0}),
        confidence_note="Low confidence: treat this diagnosis as a lead to check, not a conclusion." if band == "Low" else None,
        chunks=[Chunk("## B-06: Decimal\nbody", "KNOWN_BUGS.md", "B-06", "B-06", "B-06", 0.5)],
        tool_log=[{"tool": "read_file", "args": {"path": "logic_utils.py"}, "ok": True, "error": None},
                  {"tool": "read_file", "args": {"path": ".env"}, "ok": False, "error": "Access to environment files is not allowed."}],
        steps=3, latency_ms=900,
    )


@pytest.fixture
def at():
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception
    return app


def click(app, label):
    next(b for b in app.button if label in b.label).click()
    return app.run()


def go_to_analyzer(app):
    app.sidebar.radio[0].set_value("Bug Analyzer")
    return app.run()


# --- the game still works and is the default ---

def test_game_is_default_mode(at):
    assert at.sidebar.radio[0].value == "Play the game"
    assert "Make a guess" in [s.value for s in at.subheader]
    assert not at.text_area


def test_game_still_rejects_bad_input_without_using_an_attempt(at):
    at.text_input[0].set_value("abc").run()
    click(at, "Submit")
    assert at.error[0].value == "That is not a number."
    assert "Attempts left: 8" in at.info[0].value


def test_game_state_survives_switching_modes(at):
    at.text_input[0].set_value("50").run()
    click(at, "Submit")
    assert "Attempts left: 7" in at.info[0].value
    go_to_analyzer(at)
    at.sidebar.radio[0].set_value("Play the game").run()
    assert "Attempts left: 7" in at.info[0].value


def test_difficulty_survives_switching_modes(at):
    at.sidebar.selectbox[0].set_value("Hard").run()
    go_to_analyzer(at)
    assert at.sidebar.selectbox[0].value == "Hard"
    at.sidebar.radio[0].set_value("Play the game").run()
    assert at.sidebar.selectbox[0].value == "Hard"
    assert "Attempts left: 5" in at.info[0].value


def test_analyzer_reachable_after_game_is_over(at):
    at.session_state["status"] = "lost"
    at.run()
    assert at.error  # game-over gate (st.stop) is active
    go_to_analyzer(at)
    assert at.text_area and not at.exception


# --- analyzer page ---

def test_analyzer_page_shows_input_and_hides_game(at):
    go_to_analyzer(at)
    assert at.text_area[0].label == "Bug report"
    assert "Make a guess" not in [s.value for s in at.subheader]
    assert not at.button or all("Submit" not in b.label for b in at.button)


def test_analyze_renders_answer_score_sources_and_evidence(at, monkeypatch):
    seen = []
    monkeypatch.setattr(analyzer_ui, "run_analysis", lambda report: seen.append(report) or ok_result())
    go_to_analyzer(at)
    at.text_area[0].set_value("45.7 counted as a win").run()
    click(at, "Analyze")
    assert seen == ["45.7 counted as a win"]
    assert any("Known bug" in s.value for s in at.subheader)
    assert at.metric[0].value == "88 / 100"
    assert not at.warning  # High band: no caveat
    markdown = " ".join(m.value for m in at.markdown)
    assert "Self-critique" in markdown and "Feedback on the code" in markdown
    assert "Sources cited" in markdown
    text = " ".join(m.value for m in at.markdown)
    assert "logic_utils.py" in text and "✅" in text and "not verified" in text
    assert "refused: Access to environment files" in text


def test_low_band_shows_caveat(at, monkeypatch):
    monkeypatch.setattr(analyzer_ui, "run_analysis", lambda report: ok_result("Low", 31))
    go_to_analyzer(at)
    click(at, "Analyze")
    assert any("Low confidence" in w.value for w in at.warning)


@pytest.mark.parametrize("status, kind", [("rejected", "warning"), ("no_context", "warning"),
                                          ("refused", "warning"), ("llm_error", "error"),
                                          ("unfinished", "error")])
def test_non_ok_statuses_show_message(at, monkeypatch, status, kind):
    chunks = [Chunk("## B-06\nbody", "KNOWN_BUGS.md", "B-06", "B-06", "B-06", 0.1)] if status == "llm_error" else []
    result = AnalysisResult(status=status, message=f"message for {status}", chunks=chunks)
    monkeypatch.setattr(analyzer_ui, "run_analysis", lambda report: result)
    go_to_analyzer(at)
    click(at, "Analyze")
    shown = getattr(at, kind)
    assert any(f"message for {status}" in e.value for e in shown)
    assert not at.metric
    if chunks:
        assert "Closest matching documentation" in " ".join(m.value for m in at.markdown)


def test_result_stays_visible_across_reruns(at, monkeypatch):
    monkeypatch.setattr(analyzer_ui, "run_analysis", lambda report: ok_result())
    go_to_analyzer(at)
    click(at, "Analyze")
    at.run()
    assert at.metric[0].value == "88 / 100"


def test_example_selector_fills_report(at):
    go_to_analyzer(at)
    at.selectbox(key="analyzer_example").set_value("Score went negative").run()
    assert "score went negative" in at.text_area[0].value.lower()


# --- run_analysis wiring ---

def test_run_analysis_without_key_reports_error_and_does_not_log(monkeypatch):
    def no_key():
        raise LLMError("GEMINI_API_KEY is not set.")
    logged = []
    monkeypatch.setattr(analyzer_ui, "GeminiClient", no_key)
    monkeypatch.setattr(analyzer_ui, "log_analysis", lambda *a, **k: logged.append(a))
    result = analyzer_ui.run_analysis("some report")
    assert result.status == "llm_error" and "GEMINI_API_KEY" in result.message
    assert logged == []


def test_run_analysis_logs_every_analysis(monkeypatch):
    logged = []
    sentinel = AnalysisResult(status="no_context", message="m")
    monkeypatch.setattr(analyzer_ui, "GeminiClient", lambda: object())
    monkeypatch.setattr(analyzer_ui.debug_agent, "analyze", lambda report, retriever, llm: sentinel)
    monkeypatch.setattr(analyzer_ui, "log_analysis", lambda report, result: logged.append((report, result)))
    assert analyzer_ui.run_analysis("some report") is sentinel
    assert logged == [("some report", sentinel)]
