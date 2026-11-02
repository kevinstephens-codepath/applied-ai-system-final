"""Streamlit UI for the Bug Analyzer. The game itself lives in app.py."""

import streamlit as st

import debug_agent
from analysis_log import log_analysis
from llm_client import GeminiClient, LLMError
from rag_retriever import Retriever

EXAMPLES = {
    "Choose an example...": "",
    "Decimal counted as a win": "When I typed 45.7 and the secret was 45, the game said I won. Why does a decimal count as a correct guess?",
    "Score went negative": "My score went negative after several wrong guesses on Hard.",
    "New Game does nothing": "After I lose on Easy mode the New Game button does nothing and I cannot start another round.",
    "Message flashes then vanishes": "After I submit a guess the hint flashes for a split second and then disappears.",
    "Hint points the wrong way": "The game says Go LOWER when my guess is below the secret number.",
    "Out of scope": "Can I play against a friend on the leaderboard?",
}
VERDICT_LABELS = {
    "bug": "🐞 Bug",
    "known_fixed_bug": "🩹 Known bug, already fixed",
    "correct_behavior": "✅ Correct behavior",
    "not_covered": "❔ Not covered by the spec",
}
BAND_ICONS = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}


@st.cache_resource
def get_retriever() -> Retriever:
    return Retriever()


def run_analysis(report: str):
    """Analyze one report with the real retriever and Gemini, and log it."""
    try:
        llm = GeminiClient()
    except LLMError as exc:
        # Not logged as an analysis: nothing was analyzed.
        return debug_agent.AnalysisResult(status="llm_error", message=str(exc))
    result = debug_agent.analyze(report, get_retriever(), llm)
    log_analysis(report, result)
    return result


def _show_chunks(chunks, title: str):
    st.markdown(f"**{title}**")
    for c in chunks:
        with st.expander(f"{c.chunk_id}  ·  {c.source}  ·  match {c.score:.2f}"):
            st.text(c.text)


def render_result(result):
    if result.input_note:
        st.info(result.input_note)

    if result.status != "ok":
        (st.error if result.status in ("llm_error", "unfinished") else st.warning)(result.message)
        if result.chunks:
            _show_chunks(result.chunks, "Closest matching documentation")
        return

    answer = result.answer
    score = result.score
    st.subheader(VERDICT_LABELS.get(answer["verdict"], answer["verdict"]))
    st.write(answer["summary"])
    st.markdown(f"**Why:** {answer['root_cause']}")
    st.markdown(f"**Suggested fix:** {answer['suggested_fix']}")

    st.metric(f"Debug score {BAND_ICONS[score.band]}", f"{score.total} / 100", score.band, delta_color="off")
    st.progress(score.total / 100)
    if result.confidence_note:
        st.warning(result.confidence_note)
    with st.expander("How the score was calculated"):
        for name, points in score.components.items():
            st.write(f"- {name.replace('_', ' ').title()}: {points}")

    if answer["cited_rules"]:
        cited = [c for c in result.chunks if c.chunk_id in answer["cited_rules"]]
        _show_chunks(cited, "Sources cited")
    if answer["code_evidence"]:
        st.markdown("**Code the analyzer looked at**")
        for e in answer["code_evidence"]:
            mark = "✅" if e["verified"] else "⚠️ not verified"
            st.write(f"- `{e['file']}` lines {e['start_line']}-{e['end_line']} {mark}")
    if answer["self_critique"]:
        st.markdown(f"**Self-critique:** {answer['self_critique']}")
    if answer["code_feedback"]:
        st.markdown(f"**Feedback on the code:** {answer['code_feedback']}")
    with st.expander(f"Tool calls ({len(result.tool_log)}) · {result.steps} model turns · {result.latency_ms} ms"):
        for e in result.tool_log:
            st.write(f"- `{e['tool']}` {e['args']} → {'ok' if e['ok'] else 'refused: ' + str(e['error'])}")


def _load_example():
    st.session_state.analyzer_report = EXAMPLES[st.session_state.analyzer_example]


def render_bug_analyzer():
    st.subheader("🔍 Bug Analyzer")
    st.caption(
        "Describe a problem with the game. The analyzer searches the game's spec and bug history, "
        "inspects the code, runs checks, and explains what it found with a confidence score."
    )
    st.selectbox("Examples", list(EXAMPLES), key="analyzer_example", on_change=_load_example)
    report = st.text_area("Bug report", key="analyzer_report", height=140,
                          placeholder="What did you do, what did you expect, and what happened?")

    if st.button("Analyze", type="primary"):
        with st.spinner("Analyzing..."):
            st.session_state.analysis = run_analysis(report)

    if st.session_state.get("analysis") is not None:
        st.divider()
        render_result(st.session_state.analysis)
