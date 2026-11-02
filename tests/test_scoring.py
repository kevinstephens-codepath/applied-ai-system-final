import pytest

import scoring
from rag_retriever import Chunk
from scoring import (
    WEIGHTS,
    band_for,
    citation_fraction,
    code_evidence_fraction,
    compute_debug_score,
    empty_score,
    evidence_is_valid,
    reproduction_fraction,
    retrieval_fraction,
    verification_fraction,
)


def chunk(score):
    return Chunk("t", "GAME_SPEC.md", "R-X-01", "R-X-01", "R-X-01", score)


FILES = {"logic_utils.py": 60}
RANGES = {"logic_utils.py": [(1, 60)]}


def ok(tool, **extra):
    return {"tool": tool, "args": {}, "ok": True, "error": None, **extra}


def pytest_run(passed, failed=0, errors=0):
    return ok("run_pytest", pytest={"passed": passed, "failed": failed, "errors": errors})


def test_weights_total_100():
    assert sum(WEIGHTS.values()) == 100


@pytest.mark.parametrize("total, band", [(100, "High"), (75, "High"), (74, "Medium"), (50, "Medium"), (49, "Low"), (0, "Low")])
def test_bands(total, band):
    assert band_for(total) == band


# --- retrieval ---

def test_retrieval_fraction():
    assert retrieval_fraction([]) == 0
    assert retrieval_fraction([chunk(0.5), chunk(0.4), chunk(0.3)]) == 1.0
    weak = retrieval_fraction([chunk(0.1)])
    assert 0 < weak < 0.2
    assert retrieval_fraction([chunk(0.5)]) < 1.0  # one good chunk is not full marks


# --- citations ---

def test_citation_fraction():
    assert citation_fraction(["a", "b"], ["a", "b"], "bug") == 1.0
    assert citation_fraction(["a", "b"], ["a"], "bug") == 0.5
    assert citation_fraction(["x"], [], "bug") == 0.0
    assert citation_fraction([], [], "bug") == 0.0
    assert citation_fraction([], [], "not_covered") == 0.5


# --- reproduction / verification ---

def test_reproduction_fraction():
    assert reproduction_fraction([]) == 0
    assert reproduction_fraction([pytest_run(3)]) == 0.5
    assert reproduction_fraction([ok("run_repro")]) == 1.0
    assert reproduction_fraction([{"tool": "run_repro", "ok": False, "error": "bad"}]) == 0
    assert reproduction_fraction([ok("read_file")]) == 0


def test_verification_fraction():
    assert verification_fraction([]) == 0
    assert verification_fraction([pytest_run(21)]) == 1.0
    assert verification_fraction([pytest_run(20, failed=1)]) == 0
    assert verification_fraction([pytest_run(20, errors=1)]) == 0
    assert verification_fraction([pytest_run(0)]) == 0  # nothing ran
    assert verification_fraction([ok("run_repro")]) == 0


# --- code evidence ---

@pytest.mark.parametrize("entry", [
    {"file": "logic_utils.py", "start_line": 10, "end_line": 20},
    {"file": "logic_utils.py", "start_line": 1, "end_line": 60},
    {"file": "logic_utils.py", "start_line": 5, "end_line": 5},
])
def test_valid_evidence(entry):
    assert evidence_is_valid(entry, FILES, RANGES)


@pytest.mark.parametrize("entry", [
    {"file": "app.py", "start_line": 1, "end_line": 5},                 # never read
    {"file": "logic_utils.py", "start_line": 10, "end_line": 70},       # past the end of file
    {"file": "logic_utils.py", "start_line": 0, "end_line": 5},
    {"file": "logic_utils.py", "start_line": 20, "end_line": 10},
    {"file": "logic_utils.py", "start_line": "1", "end_line": 5},
    {"file": "logic_utils.py", "start_line": True, "end_line": 5},
    {"file": "logic_utils.py", "start_line": 1},
    "logic_utils.py:1-5",
    None,
])
def test_invalid_evidence(entry):
    assert not evidence_is_valid(entry, FILES, RANGES)


def test_evidence_must_lie_within_lines_actually_read():
    ranges = {"logic_utils.py": [(1, 20)]}
    assert evidence_is_valid({"file": "logic_utils.py", "start_line": 5, "end_line": 15}, FILES, ranges)
    assert not evidence_is_valid({"file": "logic_utils.py", "start_line": 15, "end_line": 30}, FILES, ranges)


def test_code_evidence_fraction_is_share_of_valid_entries():
    good = {"file": "logic_utils.py", "start_line": 1, "end_line": 5}
    bad = {"file": "nope.py", "start_line": 1, "end_line": 5}
    assert code_evidence_fraction([good, bad], FILES, RANGES) == 0.5
    assert code_evidence_fraction([], FILES, RANGES) == 0


# --- total ---

def test_full_marks():
    result = compute_debug_score(
        [chunk(0.6), chunk(0.5), chunk(0.4)], ["R-X-01"], ["R-X-01"], "bug",
        [{"file": "logic_utils.py", "start_line": 1, "end_line": 10}],
        [ok("run_repro"), pytest_run(21)], FILES, RANGES,
    )
    assert result.total == 100
    assert result.band == "High"


def test_model_claims_alone_earn_little():
    """Confident-sounding answer with nothing checkable behind it must land in Low."""
    result = compute_debug_score(
        [chunk(0.25)], ["R-X-01", "R-FAKE-01"], ["R-X-01"], "bug",
        [{"file": "app.py", "start_line": 1, "end_line": 200}], [], {}, {},
    )
    assert result.band == "Low"
    assert result.components["reproduction"] == 0
    assert result.components["code_evidence"] == 0
    assert result.components["verification"] == 0


def test_components_sum_to_total_and_empty_score():
    result = compute_debug_score([chunk(0.3)], ["R-X-01"], ["R-X-01"], "bug", [], [pytest_run(5)], {}, {})
    assert result.total == round(sum(result.components.values()))
    assert set(result.components) == set(WEIGHTS)
    empty = empty_score()
    assert (empty.total, empty.band) == (0, "Low")
    assert scoring.DebugScore  # exported
