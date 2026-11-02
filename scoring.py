"""Debug score: a 0-100 confidence score for one diagnosis, computed from checkable evidence.

Nothing here trusts the model's own claim of confidence. Each component is derived from what was
actually retrieved, cited, run, and read.
"""

from dataclasses import dataclass

from rag_retriever import DEFAULT_MIN_SCORE

WEIGHTS = {"retrieval": 30, "citation": 20, "reproduction": 20, "code_evidence": 20, "verification": 10}
HIGH_MIN = 75
MEDIUM_MIN = 50

FULL_TOP_SCORE = 0.5   # top-1 retrieval score that earns full marks
FULL_CHUNK_COUNT = 3   # relevant chunks that earn full marks
NOT_COVERED_CITATION_SHARE = 0.5


@dataclass(frozen=True)
class DebugScore:
    total: int
    band: str
    components: dict


def band_for(total: float) -> str:
    return "High" if total >= HIGH_MIN else "Medium" if total >= MEDIUM_MIN else "Low"


def retrieval_fraction(chunks) -> float:
    if not chunks:
        return 0.0
    top = max(c.score for c in chunks)
    relevant = sum(c.score >= DEFAULT_MIN_SCORE for c in chunks)
    return 0.75 * min(1.0, top / FULL_TOP_SCORE) + 0.25 * min(1.0, relevant / FULL_CHUNK_COUNT)


def citation_fraction(claimed: list, valid: list, verdict: str) -> float:
    """Share of the model's citations that were really retrieved."""
    if not claimed:
        return NOT_COVERED_CITATION_SHARE if verdict == "not_covered" else 0.0
    return len(valid) / len(claimed)


def reproduction_fraction(tool_log: list[dict]) -> float:
    """Full marks if a game function was replayed, half if only the tests were run."""
    ok = [e["tool"] for e in tool_log if e["ok"]]
    if "run_repro" in ok:
        return 1.0
    return 0.5 if "run_pytest" in ok else 0.0


def evidence_is_valid(entry, files_read: dict, ranges_read: dict) -> bool:
    """A cited code range counts only if that file was read and the lines were within what was read."""
    if not isinstance(entry, dict):
        return False
    path, start, end = entry.get("file"), entry.get("start_line"), entry.get("end_line")
    ints = all(isinstance(n, int) and not isinstance(n, bool) for n in (start, end))
    if path not in files_read or not ints or not 1 <= start <= end <= files_read[path]:
        return False
    return any(lo <= start and end <= hi for lo, hi in ranges_read.get(path, []))


def code_evidence_fraction(evidence: list, files_read: dict, ranges_read: dict) -> float:
    if not evidence:
        return 0.0
    return sum(evidence_is_valid(e, files_read, ranges_read) for e in evidence) / len(evidence)


def verification_fraction(tool_log: list[dict]) -> float:
    """Full marks if a pytest run executed tests and none failed or errored."""
    runs = [e["pytest"] for e in tool_log if e["tool"] == "run_pytest" and e.get("pytest")]
    return 1.0 if any(r["passed"] > 0 and r["failed"] == 0 and r["errors"] == 0 for r in runs) else 0.0


def compute_debug_score(chunks, claimed_citations, valid_citations, verdict, evidence,
                        tool_log, files_read, ranges_read) -> DebugScore:
    fractions = {
        "retrieval": retrieval_fraction(chunks),
        "citation": citation_fraction(claimed_citations, valid_citations, verdict),
        "reproduction": reproduction_fraction(tool_log),
        "code_evidence": code_evidence_fraction(evidence, files_read, ranges_read),
        "verification": verification_fraction(tool_log),
    }
    components = {name: round(WEIGHTS[name] * f, 1) for name, f in fractions.items()}
    total = round(sum(components.values()))
    return DebugScore(total, band_for(total), components)


def empty_score() -> DebugScore:
    """Score for a request that was refused before or instead of a diagnosis."""
    return DebugScore(0, "Low", {name: 0.0 for name in WEIGHTS})
