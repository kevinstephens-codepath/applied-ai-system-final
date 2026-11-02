# Known Bugs (Fixed): Game Glitch Investigator

History of bugs found and fixed in the original project, taken from `OLD_README.md` and `reflection.md`. Each entry has a unique ID, the symptom a player would report, the root cause, the fix, the related rules in `GAME_SPEC.md`, and how the fix was verified. If a new report matches one of these, the behavior should already be fixed in the current code; the agent should say so and point to the rule, not invent a new defect.

## B-01: Difficulty change did not reset the game
Symptom: switching difficulty in the sidebar kept the old secret, attempts, score and history. The range text changed but the game did not.
Root cause: nothing compared the selected difficulty to the last-seen difficulty in `st.session_state`, so state was only initialized once.
Fix: `app.py` stores `session_state.difficulty` and, when it differs from the selection, resets secret, attempts, score, status and history.
Related rules: R-DIFF-03, R-SECRET-01, R-STATE-02.
Verified: manual test in the browser.

## B-02: Hint messages were inverted
Symptom: guessing below the secret showed "Go LOWER!" and guessing above showed "Go HIGHER!". Players were sent the wrong way.
Root cause: the outcome was computed correctly but the message strings in `check_guess` were swapped.
Fix: swapped the messages and moved `check_guess` into `logic_utils.py`. Too High returns "Go LOWER!", Too Low returns "Go HIGHER!".
Related rules: R-COMPARE-01.
Verified: pytest (`test_guess_too_high_returns_too_high_and_go_lower`, `test_guess_too_low_returns_too_low_and_go_higher`, off-by-one and boundary tests).

## B-03: String secret caused lexicographic comparison
Symptom: with a string secret, `check_guess(5, "30")` said Too High, because "5" > "30" as text. Also a `TypeError` from comparing int to str.
Root cause: the `TypeError` fallback cast the guess to `str` and compared strings alphabetically instead of numerically.
Fix: the fallback now compares `int(guess)` with `int(secret)`.
Related rules: R-COMPARE-02.
Verified: pytest (`test_string_secret_exact_match`, `test_string_secret_guess_too_low`, `test_string_secret_guess_too_high`). This bug was found because a test failed on its first run.

## B-04: Attempts off by one
Symptom: the attempts shown in-game were one lower than the limit listed for the difficulty, so the player got one fewer guess than advertised.
Root cause: `session_state.attempts` was initialized to 1 instead of 0.
Fix: initial attempts is 0 and increments only on valid guesses.
Related rules: R-ATTEMPT-01, R-DIFF-02.
Verified: manual test.

## B-05: Invalid input consumed an attempt (text, empty)
Symptom: submitting a word, or submitting with an empty box, used up an attempt while also showing an error.
Root cause: the attempt counter was incremented before the guess was validated.
Fix: `parse_guess` in `logic_utils.py` validates first; the attempt is only counted when parsing succeeds.
Related rules: R-INPUT-01, R-INPUT-02.
Verified: pytest (`test_parse_guess_empty_string`, `test_parse_guess_none_input`, `test_parse_guess_non_numeric`) and manual test.

## B-06: Decimal guess counted as a win
Symptom: with secret 45, entering 45.7 was accepted as a correct guess and the game ended.
Root cause: input was converted by truncating a float to int, so 45.7 became 45.
Fix: `parse_guess` rejects any input containing "." with "Whole numbers only. No decimals allowed."
Related rules: R-INPUT-01, R-INPUT-02.
Verified: pytest (`test_parse_guess_decimal_rejected`).

## B-07: New Game button did nothing after a win or loss
Symptom: once the game was won or lost, clicking New Game gave no feedback and the game stayed over. Sometimes the new secret came from the wrong range.
Root cause: the New Game handler did not reset `status` to "playing", and did not reset score, history, or draw the secret from the current difficulty's range.
Fix: New Game resets attempts, score, history, status and feedback, and picks a new secret in the current range.
Related rules: R-NEWGAME-01, R-STATE-01, R-SECRET-01.
Verified: manual test.

## B-08: No feedback with "Show hint" unchecked
Symptom: with hints off, a wrong guess produced no message at all, so the player could not tell whether the guess registered.
Root cause: the feedback was only rendered inside the `if show_hint` branch.
Fix: when hints are off, a wrong guess shows "Incorrect!" as a warning.
Related rules: R-HINT-01.
Verified: manual test.

## B-09: Difficulty was unbalanced
Symptom: Normal (1-100) was harder than Hard (1-50), and Easy gave only 6 attempts.
Root cause: ranges and attempt limits did not scale with difficulty.
Fix: Hard range widened to 1-200; Easy attempts raised from 6 to 10. Final: Easy 1-20/10, Normal 1-100/8, Hard 1-200/5.
Related rules: R-DIFF-01, R-DIFF-02.
Verified: manual test.

## B-10: Score could go negative and rewarded wrong guesses
Symptom: the score randomly went up or down, rewarded incorrect guesses, and could drop below zero.
Root cause: the original `update_score` had a deliberate glitch based on even/odd attempts plus separate penalties for wrong guesses.
Fix: replaced with `max(10, 100 - 10 * (attempt_number - 1))`, which is deterministic, floored at 10, and updated after every valid guess (not only on a win, so the score can be shown during play).
Related rules: R-SCORE-01.
Verified: pytest (`test_attempt_1_gives_100`, `test_attempt_2_gives_90`, `test_attempt_10_gives_10`, `test_score_floors_at_10`, `test_score_never_negative`).

## B-11: Feedback vanished immediately after a guess
Symptom: after submitting a guess, no hint or win message appeared (or it flashed for a moment). After a win, only "You already won. Start a new game to play again." showed, with no balloons or score.
Root cause: `st.rerun()` was called right after `st.success`/`st.error`, and the rerun redrew the page before the message could be seen. Messages shown before a rerun are lost.
Fix: messages are stored in `session_state.feedback` as a dict `{"type", "message"}`, shown once on the next run, then cleared.
Related rules: R-FEEDBACK-01, R-STATE-01.
Verified: manual test. See also `STREAMLIT_NOTES.md` (transient messages and reruns).

## B-12: Game-over gate hid the final result
Symptom: after the winning or losing guess, the player saw the generic "already won / game over" text instead of the result message.
Root cause: the status check ran before the one-shot feedback was rendered, so the gate pre-empted it.
Fix: render stored feedback first; the game-over gate only shows its own message when no feedback was just displayed, then stops the script.
Related rules: R-STATE-01, R-FEEDBACK-01.
Verified: manual test.

## Not covered by tests
Bugs B-01, B-04, B-07, B-08, B-09, B-11 and B-12 were verified manually only; `get_range_for_difficulty` and the Streamlit flow in `app.py` have no pytest coverage. A gap worth reporting if the agent is asked what the test suite does not protect.
