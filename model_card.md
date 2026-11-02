# Model Card: Game Glitch Investigator Bug Analyzer

This card describes the whole system (retriever, guardrails, agent, scorer), not a single model. The language model is Google Gemini (`gemini-3.5-flash-lite` by default, set with `GEMINI_MODEL`). It is used as-is, with no fine-tuning.

## What it is for

**Intended use:** answer questions like "why did the game do X?" for one specific Streamlit number-guessing game, by grounding the answer in the game's written spec and its history of fixed bugs, then checking the answer against the real code and tests.

**Intended users:** the project author, and classmates or reviewers evaluating the project.

**Out of scope:** debugging any other program; judging code quality in general; making changes (the analyzer is read-only and cannot edit files); anything where a wrong answer would cause real harm. This is a learning project, not a production tool.

## How it works (short)

Retrieve chunks from three markdown documents with BM25, give the top chunks and the report to Gemini, let it use sandboxed tools for up to 6 turns (one native function call per turn), validate its answer, then compute a debug score from what was actually done. See [README.md](README.md) and [RAG_Plan.md](RAG_Plan.md).

**Knowledge base:** `docs/GAME_SPEC.md` (rules derived from the code), `docs/KNOWN_BUGS.md` (12 fixed bugs from the original project's notes), `docs/STREAMLIT_NOTES.md`. About 40 chunks. These were written for this project and are the system's entire "world knowledge" about the game.

## Evaluation

24 labeled reports in `eval/eval_cases.json`. Offline retrieval results:

| Metric | Result |
|---|---|
| Right chunk ranked first (13 in-scope reports) | 92% |
| Right chunk in top 3 | 100% |
| Off-topic reports refused (11 reports) | 64% |

**Not measured:** how often the model's verdict is correct, and whether the debug score is higher for correct diagnoses than for wrong ones. The eval script can do this (`--live`) but Gemini free-tier quota ran out during development. Until that is run, the debug score's meaning rests on its design (it only credits checkable evidence), not on measured calibration.

**Caveats on the numbers:** the set is small; I wrote the cases myself, after already seeing how the retriever behaved; and I picked the retrieval threshold by sweeping it over this same set. Treat 92% and 64% as optimistic. The threshold trades recall against precision: at 0.20, 3 of 13 real in-scope reports were wrongly refused (top-1 hit rate 69%) while only 1 of 11 off-topic reports got through; at 0.13, top-1 is 92% but 4 of 11 off-topic reports get through. I chose recall because a wrongly refused real bug has no second line of defense, while a wrongly accepted off-topic report can still be caught by the model's `not_covered` verdict and a low score.

## Safeguards

- **Input guardrail:** rejects empty, very short, gibberish, and instruction-like text (including requests for the system prompt or API key); truncates over 2,000 characters.
- **No-context refusal:** if retrieval finds nothing, the model is not called.
- **Prompt-injection hygiene:** the report, documents and tool output are treated as data in the prompt; delimiter tags inside them are neutralized; the system prompt says never to follow instructions found in them.
- **Output guardrail:** the answer must be structured JSON with a known verdict; citations that were not actually retrieved are dropped; an answer with no valid citation is refused (unless the verdict is "not covered").
- **Tool sandbox:** the file tool reads only inside the project folder, only certain file types, and never `.env`, `.git` or `.venv` (path traversal and symlink escapes are tested); the pytest tool runs without a shell, on `tests/` only, with secret-looking environment variables removed; every tool has a per-request call budget; there are no write or delete tools.
- **Debug score from evidence:** the model's own claims earn nothing by themselves. Cited code lines count only if that file was read and the lines were within what was read.
- **Logging:** every request is appended to `logs/analyzer.jsonl` (gitignored). The API key is never written.

## Limitations and failure modes (observed or known)

- **Keyword retrieval:** BM25 matches words, not meaning. Reports phrased with unusual words can score below the threshold and be refused. Off-topic reports that share words with the game can pass: in my eval, a "game console button" report and an "encryption key secret number" report both got through retrieval.
- **Thin margin:** one in-scope eval case clears the threshold by about 0.004, so small changes to the docs or tokenizer could flip it.
- **Irrelevant tests earn verification credit:** the "tests passing" part of the score (10 points) is awarded for any pytest run that passes, not for running tests relevant to the report. In a live run the model used `pytest -k scoring`, which selected the scorer's own test file instead of the game's `update_score` tests, and still got full verification marks. The score therefore overstates verification in some runs.
- **The model does not always follow the prompt:** early runs skipped running the tests entirely despite a "must" instruction; after switching to forced function calls, the model ran tests in all my latest runs, but I do not know how reliable that is. It also sometimes skips replaying the game function (reproduction score halves).
- **Flaky replies (fixed, but worth knowing why):** the first version asked Gemini for plain JSON describing a tool call. With `gemini-3.5-flash-lite` that failed often: in one 11-turn sample, 5 turns finished with `MALFORMED_FUNCTION_CALL` and 3 were empty, and users saw errors like "the model did not return a JSON object". The model prefers its native function-calling format. Switching to native function calling (one forced function call per turn, schema-validated arguments) gave 0 failures in the next 12 turns. That is a small sample, not a guaranteed failure rate. The client also retries once with a corrective note.
- **Timing and cost:** each tool call is a separate model turn, so a diagnosis is 4 to 6 API calls: about 5 to 10 seconds in my latest runs, but 54 seconds in one earlier run. On a free API tier the analyzer can hit rate limits; it reports this clearly and shows the closest documents instead.
- **Docs can drift:** the spec is the source of truth the agent grades the code against. If someone changes the game without updating `docs/`, the analyzer can confidently report the new behavior as a bug, or the old behavior as correct.
- **Mostly "already fixed":** the game's known bugs are already fixed, so the usual honest answer is "this is correct" or "this was a known bug". The analyzer is built not to invent a defect, but it has not been tested against a real new bug.
- **Self-assessment is weak evidence:** the "self-critique" and "feedback on the code" fields are the model's own text. They are shown to the user but not scored.

## Bias, fairness and misuse

There is no user data about people and no personalization, so classic demographic bias is not a main concern here. The relevant biases are about coverage: the analyzer is biased toward the bugs already written in `KNOWN_BUGS.md` (it will tend to match reports to known entries), toward English text, and toward users who describe problems in words the docs happen to use.

Misuse risks are small but real: someone could try to get the model to reveal secrets or run commands through the report text or through file contents. Mitigations are above (input guardrail, data-not-instructions prompting, sandboxed read-only tools, no shell, secrets stripped from the test subprocess, `.env` unreadable). These are tested, but they are not a security audit. Bug reports are logged locally in plain text, so do not paste personal information into the analyzer.

## Reflection

*Draft written from the project's actual history. Edit it into your own words and add your own experience.*

**What worked.** Writing the specification first (`GAME_SPEC.md`) gave every later piece something concrete to check against: the retriever's chunks, the agent's self-check, and the tests. Making the debug score depend only on things the code can verify (retrieved chunks, tools that actually ran, line ranges that were really read) meant the score could not be inflated by a confident-sounding model. Testing with a scripted fake model made the agent loop deterministic to test, including the awkward cases (denied files, never-finishing loops, invented citations).

**What surprised or went wrong.**
- Tests caught real defects in my own AI-assisted code: a stemmer that turned "scores" into "scor" but left "score" alone, and a prompt-delimiter defense that neutralized closing tags but not opening ones.
- A real report ("the New Game button does nothing after I lose") was wrongly refused as having no context. A live run found it, and the fix was in the retriever's vocabulary handling, not the threshold.
- Sweeping the threshold showed that keyword relevance alone cannot cleanly separate real reports from off-topic ones that share vocabulary. That pushed the design toward defense in depth (model verdict, citation checks, score) rather than trusting one filter.
- Repeated live testing used up the free-tier quota, which blocked measuring the model's accuracy. In hindsight a small, planned live eval (a few calls per case) would have been better than ad-hoc runs.
- The first agent protocol (ask the model for JSON text describing a tool call) was unreliable: a user hit "the model did not return a JSON object", and live sampling showed the cause was the model's own preference for native function calling. Disabling function calls in the request did not help; using native function calling did. The lesson: when an API offers a mechanism for what you are doing, use it instead of imitating it in prompt text.
- The model ignored a "must run the tests" instruction under the old protocol. A rule in a prompt does not enforce it, and the new protocol's improvement here is unexplained. Enforcing it would need a check in the loop (not built yet).

**One AI suggestion I accepted.** *[Write your own: what the AI suggested, why you accepted it, and how you checked that it was right.]*

**One AI suggestion I rejected or revised.** *[Write your own: what the AI suggested, what you changed or turned down and why, and what happened as a result.]*

**Working with AI.** Most of the code in this extension was written by an AI assistant working from a plan I reviewed, in the same way as the original project. What kept that safe was the same habit as before: tests first for anything with a safety property, running the real thing instead of trusting a summary, and recording what is *not* verified.

**What I would do next.** Run the live eval and check that the score separates correct from incorrect diagnoses; enforce "run the tests" in the loop; try embedding-based retrieval and compare it with BM25 on the same eval set; add a few brand-new bugs to the game (not already in the history) and see whether the analyzer finds them.

*[Add your own reflection here: what you learned about RAG and agents, what you would explain to someone new, and anything about your own process that the project history does not show.]*
