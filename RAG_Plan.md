# RAG_Plan: RAG-Enhanced Bug Analysis for Game Glitch Investigator

## 1. Goal and scope
Extend the finished Streamlit game into an applied AI system. A user pastes a bug description (or a code snippet) about the game. The system retrieves the relevant parts of the game's specification and bug history, asks an LLM for a diagnosis and fix grounded in that context, runs read-only checks to reproduce and verify, and returns an answer with a **debug score** that says how trustworthy the diagnosis is.

Non-goals: debugging arbitrary programs, executing user-supplied code, changing game rules.

## 2. Architecture

```
User bug report
   |
   v
[1] Input guardrail      validate: non-empty, length, on-topic, no injection
   |
   v
[2] Retriever            BM25/TF-IDF over docs/ chunks -> top-k with scores
   |
   v
[3] Context assembly     top-k chunks (with rule IDs) + report
   |
   v
[4] Agent loop (<= N)    classify -> reproduce with tool -> LLM diagnosis
   |                     -> self-check against spec invariants
   v
[5] Debug scorer         0-100 from retrieval, citations, repro, verification
   |
   v
[6] Output guardrail     low confidence / no context -> refuse or caveat
   |
   v
Formatted response in Streamlit  +  JSONL log
```
Export this diagram to `assets/system_diagram.png` at the end (Mermaid or draw.io).

## 3. Knowledge base (`docs/`)
| File | Purpose |
|---|---|
| `docs/GAME_SPEC.md` | **Grounding document (written).** Authoritative rules with IDs such as `R-SCORE-01`, derived from `logic_utils.py` and `app.py`, plus testable invariants. |
| `docs/KNOWN_BUGS.md` | **(written)** The 12 bugs already fixed (`OLD_README.md`/`reflection.md`): symptom, root cause, fix, related rules, how verified. Lets the retriever match user symptoms to past root causes. |
| `docs/STREAMLIT_NOTES.md` | Short notes on `session_state`, `st.rerun()` erasing transient messages, widget keys. |

Maintenance rule: when game code changes, update `GAME_SPEC.md` in the same commit. The spec is the source of truth the agent grades against.

## 4. Retrieval design: `rag_retriever.py`
- **Chunking:** split markdown on `##` headings; one chunk per rule/bug entry. Metadata: source file, heading, rule ID.
- **Index:** start with BM25 (or TF-IDF via scikit-learn); deterministic, no API cost, easy to unit test. Optional flag to swap in Gemini embeddings if the eval hit-rate is poor.
- **API:** `Retriever(docs_dir).search(query, k=4) -> list[Chunk(text, source, rule_id, score)]`.
- **No-context signal:** if the top score is below a tuned threshold, return an empty list; downstream treats this as "insufficient grounding".
- **Query building:** raw report plus extracted keywords (function names, "score", "attempts", "New Game", etc.).

## 5. Agentic loop: `debug_agent.py`
Bounded (max 3 iterations), tool-using, not free-form.
1. **Classify** the report into an area (difficulty, input, comparison, attempts, score, state, UI feedback, out-of-scope).
2. **Retrieve** spec + known-bug chunks.
3. **Inspect code (read tool):** the agent uses the sandboxed read tool (section 5a) to open the relevant source (e.g. `logic_utils.py`, the matching section of `app.py`, the matching tests) so its diagnosis and its self-score rest on the actual code, not only on the spec text.
4. **Reproduce (tool):** a whitelisted tool calls the pure functions in `logic_utils.py` (`parse_guess`, `check_guess`, `update_score`, `get_range_for_difficulty`) with inputs extracted from the report, and compares the real output to the spec rule. Tools never exec user code and never touch the network.
5. **Diagnose (LLM, Gemini via `google-genai`):** prompt includes only retrieved chunks, file excerpts the agent read, and tool results; must cite rule IDs and file:line references, and say "not covered by spec" when applicable.
6. **Self-check and self-critique:** verify the proposed fix against the invariants in `R-INVARIANTS-01` (optionally run `pytest -k` on the relevant tests). The agent also reads the code once more and gives feedback on the app's code (spec mismatches, missing tests, risky patterns) and on its own diagnosis (what evidence is weak). If a check fails, loop once with the failure as extra context.
7. **Return** structured result: `{summary, root_cause, suggested_fix, cited_rules, code_evidence, repro_result, verified, self_critique}`.

### 5a. Read tool: `agent_tools.py`
Basic, read-only, confined to this project folder. Two functions exposed to the model as Gemini function declarations:
- `list_files(subdir=".") -> list[str]`: relative paths of allowed files under the project root.
- `read_file(path, start_line=1, end_line=None) -> {path, start_line, end_line, content}`: returns numbered lines.

Safety rules (enforced in code, covered by tests):
- Resolve every path with `Path(root, path).resolve()` and require it to be inside `PROJECT_ROOT` (blocks `../` and symlink escapes). Absolute paths are rejected.
- Extension allowlist: `.py`, `.md`, `.json`, `.txt`, `.toml`, `.example`; `example.env` is allowed.
- Denylist, checked on every path component: `.env` (real secrets), `.git/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `logs/`, `.streamlit/secrets.toml`.
- Size caps: 200 KB per file, 300 lines per call; truncated results say so.
- Per-request call budget (e.g. 8 reads) so the loop cannot run away; every call is logged.
- No write, delete, rename, or shell capability exists in this module. Errors return a short message string to the model instead of raising.
- File contents are treated as untrusted data in the prompt (a file cannot instruct the agent).

Key point: the existing code is already fixed, so "reproduce" typically shows current behavior matches the spec. The agent must then report "this behavior is correct per R-XXX" or "this was a known past bug", not fabricate a defect.

## 6. Debug score: `scoring.py`
Score 0-100, deterministic given its inputs:
| Component | Weight | Signal |
|---|---|---|
| Retrieval confidence | 30 | normalized top-1 score and number of chunks above threshold |
| Citation coverage | 20 | answer cites >= 1 valid rule ID that exists in the retrieved set |
| Reproduction | 20 | tool run executed and matched or contradicted the report definitively |
| Code evidence | 20 | agent read the relevant source via the read tool and cited real file:line ranges that exist (checked programmatically, not by the LLM) |
| Verification | 10 | proposed fix satisfies invariants / relevant tests pass |
Bands: High >= 75, Medium 50-74, Low < 50. Low triggers the output guardrail caveat. Weights live in one constants block so they can be tuned against the eval set.

## 7. Guardrails: `guardrails.py`
**Input:** reject empty/whitespace; min 10 and max ~2,000 chars; reject gibberish (low alphabetic ratio, no recognizable game or code terms); strip or flag prompt-injection patterns ("ignore previous instructions"); truncate large code snippets. Returns `(ok, cleaned_text, reason)` mirroring the `parse_guess` style.
**Output:** if retrieval is empty or the score is Low, return "I don't have enough information in the game spec to diagnose this", with the closest chunks if any, instead of an LLM guess; require at least one valid citation; cap length; handle API errors/timeouts by falling back to retrieved chunks only.

## 8. Logging
Append one JSON line per request to `logs/analyzer.jsonl` (gitignored): timestamp, cleaned input, guardrail result, retrieved chunk IDs and scores, tool results, final answer, debug score and band, latency, error. Never log the API key.

## 9. UI integration (`app.py`)
Keep the game flow untouched. Add a "Bug Analyzer" section (sidebar toggle or `st.tabs`) with a text area, "Analyze" button, and result panel: diagnosis, suggested fix, cited rule IDs as expandable source chunks, and the debug score badge. All logic lives in importable modules (`rag_retriever.py`, `debug_agent.py`, `scoring.py`, `guardrails.py`), consistent with the existing convention of keeping logic in `logic_utils.py` for testability. Cache the retriever with `st.cache_resource`.

## 10. Proposed file layout
```
app.py                  game + Bug Analyzer UI
logic_utils.py          existing game logic (unchanged)
rag_retriever.py        chunking + search
guardrails.py           input/output checks
debug_agent.py          agent loop + LLM call
agent_tools.py          sandboxed read tool (list_files, read_file) + repro tool
scoring.py              debug score
docs/                   GAME_SPEC.md, KNOWN_BUGS.md, STREAMLIT_NOTES.md
eval/eval_cases.json    labeled bug reports
tests/                  existing + test_retriever / test_guardrails / test_scoring / test_agent
assets/system_diagram.png
logs/                   gitignored
README.md               updated with setup, sample inputs/outputs
model_card.md           reflection, limits, biases, misuse
```

## 11. Milestones (maps to TF_Notes Part 2 onward)
1. **M1 Docs:** `GAME_SPEC.md` (done), write `KNOWN_BUGS.md` and `STREAMLIT_NOTES.md`.
2. **M2 Retriever:** `rag_retriever.py` + tests; tune threshold.
3. **M3 Guardrails + LLM:** `guardrails.py`; Gemini client with `.env` key; prompt template with citation requirement.
4. **M4 Agent + scoring:** `agent_tools.py` (read tool + path-sandbox tests first), loop, `scoring.py`, tests with a mocked LLM.
5. **M5 UI + logging:** wire into `app.py`, JSONL logging.
6. **M6 Polish:** eval run, diagram to `assets/`, README sample inputs/outputs, `model_card.md`.

## 12. Testing and evaluation
- **Read-tool tests:** `../` traversal, absolute paths, symlink escape, `.env`, `.git/`, `.venv/` are all refused; an allowed file reads with correct line slicing; oversize files and line ranges truncate; call budget is enforced.
- **Unit tests (pytest):** retriever returns `R-SCORE-01` for "score goes negative"; returns nothing for "what's the weather"; guardrails reject empty/gibberish/injection; scorer bands; agent with mocked LLM returns cited, structured output. Existing 21 tests must stay green.
- **Eval set:** ~10 labeled reports (several matching historical bugs, a few "this is actually correct", 2 out-of-scope). Metrics: top-1/top-3 source hit-rate, correct refusal rate on out-of-scope, mean debug score by correct vs. incorrect diagnosis.
- **Manual:** run Streamlit and try the sample inputs listed in the README.

## 13. Housekeeping and risks
- `requirements.txt`: `google-genai` and `example.env` are already added. Still to do: confirm the dotenv entry is `python-dotenv` (the package that provides `load_dotenv`), (no retrieval dependency is needed; BM25 is built in).
- Load `GEMINI_API_KEY` from `.env` via `load_dotenv()`; `.env` is already gitignored and the read tool refuses to open it. `example.env` documents the variable with a placeholder only. Add `logs/` to `.gitignore`.
- Hallucination: mitigated by context-only prompting, mandatory rule-ID citations, and the self-check step.
- Prompt injection via the bug report: guardrail plus treating the report as data in the prompt.
- Cost/latency: lexical retrieval is free; one LLM call per loop iteration, capped.
- Spec drift: spec must be updated with code changes; consider a test asserting spec constants (ranges, limits) match `logic_utils.py`.

## 14. Confirmed decisions
- LLM is Gemini, via the `google-genai` SDK (installed and in requirements).
- "Debug scoring" is a confidence score for each diagnosis, not a game score.
- Agent tools: a read-only file tool confined to this project folder (section 5a), plus the game's pure functions and pytest. The agent uses the read tool to score itself and to give feedback on its own and the app's code.

- Gemini model is chosen through the `GEMINI_MODEL` environment variable (already added to `.env`), so it can be switched without code changes.
- The agent gets a `run_pytest` tool in the first version, in addition to the read tool (section 5b).

### 5b. Pytest tool (decided)
`run_pytest(target=None)` in `agent_tools.py`: runs `pytest` with a fixed argv (`sys.executable -m pytest -q`), only against `tests/`, optionally one file or `-k` expression from a validated pattern (letters, digits, `_`, spaces, `and/or/not`). No shell (`shell=False`), working directory pinned to the project root, 30 s timeout, output truncated to ~4 KB, per-request call budget (e.g. 2). Returns `{passed, failed, errors, failing_tests, output_tail}`. It feeds the Reproduction and Verification score components and the self-critique (which tests pass, which behavior has no test). Tests are trusted project code; the agent cannot create or edit tests.

## 15. Status
- M1 docs: `GAME_SPEC.md`, `KNOWN_BUGS.md` (12 entries, B-01 to B-12), `STREAMLIT_NOTES.md` written.
- M2 retriever: `rag_retriever.py` + `tests/test_retriever.py` done (42 tests passing in total). BM25 is implemented in the module itself, so `rank-bm25` is not needed. Scores are normalized to 0-1; the best chunk must reach `DEFAULT_MIN_SCORE = 0.2` or the result is empty (no-context signal), and other chunks need half that. Tuned on 11 sample queries: off-topic "weather" scores under 0.1, real symptoms score 0.24-0.76 at top-1.
- M3 guardrails + LLM: `guardrails.py` (`validate_input`, `check_output`, `confidence_note`), `prompts.py` (system prompt + `build_prompt` with delimiter defanging), `llm_client.py` (`GeminiClient.generate_json`, settings from `.env`) and their tests done (90 tests passing). The model answers in JSON with a verdict (`bug`, `known_fixed_bug`, `correct_behavior`, `not_covered`), summary, root cause, suggested fix and `cited_rules`. `check_output` refuses when nothing was retrieved, drops citations that were not retrieved, and refuses an answer with no valid citation unless the verdict is `not_covered`. A live call succeeded with `gemini-3.5-flash-lite`; `gemini-2.5-flash-lite` now returns 404 for new users, so the default and `example.env` were updated and the local `.env` needs the same change.
- M4 agent + scoring: `agent_tools.py` (`ToolBox`: `list_files`, `read_file`, `run_repro`, `run_pytest`, with the sandbox and budgets from 5a/5b), `scoring.py` (`compute_debug_score`, weights in `WEIGHTS`), `debug_agent.py` (`analyze(report, retriever, llm)` returning an `AnalysisResult`) and `prompts.py` (agent prompt) done, 206 tests passing. Design notes:
  - The loop is a JSON protocol on top of `generate_json`: each turn the model returns one tool call or `{"action": "final", "answer": {...}}`, max 6 turns, and the last turn must be final. Native Gemini function-calling was not used so the loop stays testable with a scripted fake model.
  - Statuses: `ok`, `rejected` (input guardrail), `no_context` (nothing retrieved, no LLM call), `refused` (output guardrail), `llm_error` (closest docs shown), `unfinished`.
  - Scoring is computed only from checkable evidence. Code-evidence entries count only when that file was read and the cited lines lie within a range actually read; malformed entries count against the score. Reproduction is full marks for a successful `run_repro`, half for tests only; verification needs a pytest run with passes and no failures or errors.
  - `run_pytest` runs without a shell, strips secret-looking env vars from the child, and refuses to nest (`GLITCH_PYTEST_SUBPROCESS`), so tests of it must target a single file.
  - `GeminiClient` retries once on API errors or unparseable JSON (a live run returned a non-JSON reply once). Quota/rate-limit (429) and key/model errors (400/401/403/404) are not retried and give a specific message; the agent shows that message plus the closest docs.
  - Live runs against Gemini (`gemini-3.5-flash-lite`) completed end to end for both sample reports (decimal-as-win, New Game after a loss), then the free-tier quota ran out (429) during testing. Observed: the model sometimes finishes a turn with `MALFORMED_FUNCTION_CALL` yet the text is still valid JSON; if non-JSON replies become common, add a corrective retry or a `response_schema`. Pytest was not run by the model in the sampled runs, so verification scored 0 there; consider telling the model to always run the tests. A report that was wrongly refused (B-07 phrased with "lose", "cannot start another round") led to retrieval fixes: more filler stopwords, trailing-"e" stemming and irregular forms (lost/won). Off-topic queries top out around 0.12 against the 0.2 threshold; recheck with the M6 eval set.
- M5 UI + logging: `analysis_log.py` (`log_analysis` appends one JSON line per analysis to `logs/analyzer.jsonl`, returns False instead of raising), `analyzer_ui.py` (`render_bug_analyzer`, `run_analysis`) and a sidebar **Mode** switch in `app.py` ("Play the game" / "Bug Analyzer"), 234 tests passing. The analyzer branch sits after the sidebar widgets and before the game body, so the difficulty choice survives switching modes and the analyzer stays reachable after a win or loss (the game body ends with `st.stop()`). `AppTest` tests cover the game still working, state surviving mode switches, and every result status. Sidebar-only widgets in the game body (guess box, "Show hint" checkbox) reset to defaults when the analyzer is shown, since Streamlit drops state for widgets that are not rendered. A missing API key is shown in the UI and is not logged. `run_pytest` is now required by the agent prompt. The Streamlit app itself has not been opened in a browser yet.
- M6 polish: `eval/` (24 labeled reports incl. 8 hard negatives, `python -m eval.run_eval [--live]`), `assets/system_diagram.svg` and `.png`, new `README.md` with real sample outputs, `model_card.md` (reflection section is a draft for the author to rewrite), 246 tests passing. Eval results with the threshold now at 0.13 (`DEFAULT_MIN_SCORE`, `RELATED_FRACTION` 0.75): top-1 92%, top-3 100% on in-scope reports, 64% of off-topic reports refused (false accepts: sports-score, hard-game-console, hard-encryption-key, hard-lottery). A threshold sweep (0.10-0.25) showed in-scope and off-topic score ranges overlap, so no single cutoff separates them; 0.2 gave top-1 69% / refusal 91%. Numbers are optimistic (threshold tuned on the same set). The `R-SCOPE-01` spec rule was enriched with the words users actually use (friend, two-player, high scores) to fix a vocabulary miss. `GeminiClient` now adds a corrective nudge on retry and reports the finish reason for empty replies. Not done: live verdict-accuracy eval (quota), enforcing "run pytest before final" in the loop, embedding retrieval.
- Agent protocol change (after a user hit "the model did not return a JSON object"): live sampling of the JSON-text protocol showed 5 of 11 turns ending in `MALFORMED_FUNCTION_CALL` and 3 empty, and forbidding function calls (`mode=NONE`) did not help. The agent now uses Gemini native function calling: `tool_schemas.py` declares the tools and `final_answer`, `GeminiClient.generate_action` forces exactly one function call per turn (`mode=ANY`; only `final_answer` allowed on the last turn), integer arguments that arrive as floats are converted back, and an array of calls keeps the first. `tests/test_tool_schemas.py` keeps the schemas in sync with `ToolBox` and the output guardrail. 12 live turns afterwards: 0 failures, the model ran pytest, runs took about 5-8 s. Fresh real samples are in the README. Known weakness: verification credit is given for any passing pytest run, even unrelated tests. 269 tests passing. `generate_json` is still in the client (plain JSON mode) but the agent no longer uses it.
- The original README now lives in `OLD_README.md`; the new `README.md` is written in M6.
