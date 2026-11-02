import pytest

from debug_agent import AnalysisResult
from eval.run_eval import evaluate_live, evaluate_retrieval, format_report, load_cases
from rag_retriever import Retriever
from scoring import DebugScore

VALID_KINDS = {"known_bug", "correct_behavior", "out_of_scope", "off_topic"}
VERDICTS = {"bug", "known_fixed_bug", "correct_behavior", "not_covered", None}


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


@pytest.fixture(scope="module")
def cases():
    return load_cases()


def test_cases_are_well_formed(cases, retriever):
    assert len({c["id"] for c in cases}) == len(cases)
    chunk_ids = {c.chunk_id for c in retriever.chunks}
    for c in cases:
        assert c["kind"] in VALID_KINDS, c["id"]
        assert c["expect_verdict"] in VERDICTS, c["id"]
        assert c["report"].strip(), c["id"]
        assert set(c["expect_chunks"]) <= chunk_ids, c["id"]  # no stale chunk ids
        assert (c["kind"] == "off_topic") == (not c["expect_chunks"]), c["id"]
    kinds = {c["kind"] for c in cases}
    assert kinds == VALID_KINDS  # each category is represented


def test_retrieval_quality_does_not_regress(cases, retriever):
    """Floors sit just under the measured numbers (top-1 92%, top-3 100%, refusal 64%)."""
    result = evaluate_retrieval(cases, retriever)
    assert result["top1_rate"] >= 0.85
    assert result["top3_rate"] >= 0.95
    assert result["refusal_rate"] >= 0.6


def test_clearly_off_topic_reports_are_always_refused(cases, retriever):
    rows = {r["id"]: r for r in evaluate_retrieval(cases, retriever)["rows"]}
    for cid in ["weather", "recipe", "hard-piano", "hard-lakers", "hard-deploy"]:
        assert rows[cid]["refused"], cid


def test_known_bug_reports_find_their_entry_first(cases, retriever):
    rows = {r["id"]: r for r in evaluate_retrieval(cases, retriever)["rows"]}
    for cid in ["decimal-win", "negative-score", "inverted-hint", "new-game-after-loss", "difficulty-no-reset"]:
        assert rows[cid]["top1"], cid


def test_retrieval_metrics_are_computed_from_rows(cases, retriever):
    result = evaluate_retrieval(cases, retriever)
    in_scope = [r for r in result["rows"] if r["kind"] != "off_topic"]
    assert result["top1_rate"] == sum(r["top1"] for r in in_scope) / len(in_scope)
    assert result["lowest_in_scope_score"] == min(r["top_score"] for r in in_scope)


# --- live evaluation, with a fake analyzer (no API calls) ---

def fake_analyze_factory(wrong_ids=()):
    def fake_analyze(report, retriever, llm):
        case = next(c for c in load_cases() if c["report"] == report)
        if case["kind"] == "off_topic":
            return AnalysisResult(status="no_context", message="no")
        verdict = "bug" if case["id"] in wrong_ids else case["expect_verdict"]
        score = DebugScore(40, "Low", {}) if case["id"] in wrong_ids else DebugScore(90, "High", {})
        return AnalysisResult(status="ok", answer={"verdict": verdict}, score=score, steps=3)
    return fake_analyze


def test_live_eval_scores_accuracy_and_confidence_split(cases, retriever):
    live = evaluate_live(cases, retriever, llm=None, analyze=fake_analyze_factory({"decimal-win", "negative-score"}))
    assert len(live["rows"]) == len(cases)
    wrong = {r["id"] for r in live["rows"] if not r["correct"]}
    assert wrong == {"decimal-win", "negative-score"}
    assert live["accuracy"] == (len(cases) - 2) / len(cases)
    assert live["mean_score_correct"] == 90.0
    assert live["mean_score_incorrect"] == 40.0


def test_live_eval_treats_off_topic_answers_as_wrong(cases, retriever):
    def answers_everything(report, retriever, llm):
        return AnalysisResult(status="ok", answer={"verdict": "bug"}, score=DebugScore(70, "Medium", {}))
    live = evaluate_live(cases, retriever, llm=None, analyze=answers_everything)
    off_topic = [r for r in live["rows"] if r["kind"] == "off_topic"]
    assert off_topic and not any(r["correct"] for r in off_topic)


def test_report_text_lists_metrics_and_live_section(cases, retriever):
    retrieval = evaluate_retrieval(cases, retriever)
    live = evaluate_live(cases, retriever, llm=None, analyze=fake_analyze_factory())
    text = format_report(retrieval, live)
    for expected in ["top-1 hit rate", "off-topic refusal rate", "Live agent", "verdict accuracy"]:
        assert expected in text
    assert "Live agent" not in format_report(retrieval)
