"""Evaluate retrieval, refusals and (optionally) live model verdicts on eval/eval_cases.json.

    python -m eval.run_eval            offline: retrieval hit-rates and refusals, no API calls
    python -m eval.run_eval --live     also runs the full agent on every case (uses Gemini quota)
"""

import argparse
import json
import time
from pathlib import Path

from rag_retriever import Retriever

CASES_PATH = Path(__file__).with_name("eval_cases.json")


def load_cases(path: Path | str = CASES_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_retrieval(cases: list[dict], retriever: Retriever) -> dict:
    """In-scope cases: is an expected chunk first / in the top 3? Off-topic cases: is the result empty?"""
    rows = []
    for case in cases:
        results = retriever.search(case["report"])
        ids = [c.chunk_id for c in results]
        row = {"id": case["id"], "kind": case["kind"], "top_ids": ids[:3],
               "top_score": results[0].score if results else 0.0}
        if case["kind"] == "off_topic":
            row["refused"] = not results
        else:
            expected = set(case["expect_chunks"])
            row["top1"] = bool(ids) and ids[0] in expected
            row["top3"] = any(i in expected for i in ids[:3])
        rows.append(row)
    in_scope = [r for r in rows if r["kind"] != "off_topic"]
    off_topic = [r for r in rows if r["kind"] == "off_topic"]
    return {
        "rows": rows,
        "top1_rate": sum(r["top1"] for r in in_scope) / len(in_scope) if in_scope else None,
        "top3_rate": sum(r["top3"] for r in in_scope) / len(in_scope) if in_scope else None,
        "refusal_rate": sum(r["refused"] for r in off_topic) / len(off_topic) if off_topic else None,
        "lowest_in_scope_score": min((r["top_score"] for r in in_scope), default=None),
        "highest_off_topic_score": max((r["top_score"] for r in off_topic), default=None),
    }


def evaluate_live(cases: list[dict], retriever: Retriever, llm, pause_s: float = 0.0, analyze=None) -> dict:
    """Run the whole agent per case. A case is correct if the verdict matches (off-topic: no_context)."""
    if analyze is None:
        from debug_agent import analyze
    rows = []
    for case in cases:
        result = analyze(case["report"], retriever, llm)
        if case["kind"] == "off_topic":
            correct = result.status == "no_context"
            verdict = None
        else:
            verdict = (result.answer or {}).get("verdict")
            correct = result.status == "ok" and verdict == case["expect_verdict"]
        rows.append({"id": case["id"], "kind": case["kind"], "status": result.status, "verdict": verdict,
                     "expected": case["expect_verdict"], "correct": correct, "score": result.score.total,
                     "band": result.score.band, "steps": result.steps})
        if pause_s:
            time.sleep(pause_s)

    def mean(values):
        return round(sum(values) / len(values), 1) if values else None

    answered = [r for r in rows if r["status"] == "ok"]
    return {
        "rows": rows,
        "accuracy": sum(r["correct"] for r in rows) / len(rows) if rows else None,
        "mean_score_correct": mean([r["score"] for r in answered if r["correct"]]),
        "mean_score_incorrect": mean([r["score"] for r in answered if not r["correct"]]),
    }


def _pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def format_report(retrieval: dict, live: dict | None = None) -> str:
    lines = ["Retrieval", "---------"]
    for r in retrieval["rows"]:
        if r["kind"] == "off_topic":
            mark = "refused" if r["refused"] else "NOT REFUSED"
        else:
            mark = "top1" if r["top1"] else ("top3" if r["top3"] else "MISS")
        lines.append(f"{mark:12} {r['top_score']:.3f}  {r['id']:26} {', '.join(r['top_ids'])}")
    lines += ["",
              f"top-1 hit rate (in scope):   {_pct(retrieval['top1_rate'])}",
              f"top-3 hit rate (in scope):   {_pct(retrieval['top3_rate'])}",
              f"off-topic refusal rate:      {_pct(retrieval['refusal_rate'])}",
              f"lowest in-scope top score:   {retrieval['lowest_in_scope_score']}",
              f"highest off-topic top score: {retrieval['highest_off_topic_score']}"]
    if live:
        lines += ["", "Live agent", "----------"]
        for r in live["rows"]:
            lines.append(f"{'ok' if r['correct'] else 'WRONG':6} {r['id']:26} status={r['status']:10} "
                         f"verdict={r['verdict']} (expected {r['expected']}) score={r['score']} {r['band']}")
        lines += ["", f"verdict accuracy:                 {_pct(live['accuracy'])}",
                  f"mean debug score, correct:        {live['mean_score_correct']}",
                  f"mean debug score, incorrect:      {live['mean_score_incorrect']}"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="also run the full agent with Gemini")
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between live cases (rate limits)")
    args = parser.parse_args()

    cases, retriever = load_cases(), Retriever()
    retrieval = evaluate_retrieval(cases, retriever)
    live = None
    if args.live:
        from llm_client import GeminiClient
        live = evaluate_live(cases, retriever, GeminiClient(), pause_s=args.pause)
    print(format_report(retrieval, live))


if __name__ == "__main__":
    main()
