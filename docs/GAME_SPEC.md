# Game Glitch Investigator: Behavior Specification

Authoritative description of how the game MUST behave. The RAG retriever indexes this file; the debug agent uses it to decide whether a reported behavior is a bug. Each section is a self-contained rule with a unique ID. When a report contradicts a rule, the report describes a bug. Source of truth in code: `logic_utils.py` and `app.py`.

## R-DIFF-01: Difficulty ranges
Function: `get_range_for_difficulty(difficulty)` in `logic_utils.py`.
- Easy: secret is between 1 and 20 inclusive.
- Normal: 1 to 100 inclusive.
- Hard: 1 to 200 inclusive.
- Any unrecognized difficulty falls back to 1-100.
Difficulty must scale monotonically: Hard has the widest range. (Historical bug: Hard was 1-50, making Normal harder than Hard.)

## R-DIFF-02: Attempt limits
Defined in `attempt_limit_map` in `app.py`.
- Easy: 10 attempts. Normal: 8 attempts. Hard: 5 attempts.
- "Attempts left" shown in the info banner equals `limit - attempts`.

## R-DIFF-03: Changing difficulty resets the game
When the sidebar difficulty differs from `session_state.difficulty`, the game resets `secret` (new number in the new range), `attempts` to 0, `score` to 0, `status` to "playing", and `history` to empty. `feedback` is not reset. The new range and attempt limit must appear immediately in the banner and sidebar captions.

## R-SECRET-01: Secret number
The secret is a random integer within the current difficulty's range, chosen with `random.randint(low, high)`. It is generated at session start, on New Game, and on difficulty change. It never changes between guesses within one game.

## R-INPUT-01: Guess parsing
Function: `parse_guess(raw)` returns `(ok, value, error_message)`. Checks run in this order:
1. `None` or empty string: not ok, message "Enter a guess."
2. Contains a `.` anywhere: not ok, message "Whole numbers only. No decimals allowed."
3. `int(raw)` fails (letters, symbols, whitespace-only): not ok, message "That is not a number."
4. Otherwise ok with the integer value.
Surrounding spaces are tolerated by `int()`. Negative integers parse successfully; out-of-range integers are not rejected by the parser (they are simply Too High / Too Low). A decimal such as "45.7" must never be treated as 45 or as a win. (Historical bug.)

## R-INPUT-02: Invalid input costs nothing
An invalid guess (per R-INPUT-01) must NOT increment `attempts` and must NOT change the score. The raw text is appended to `history` and an error message is shown. Empty, text, and decimal input must not consume an attempt. (Historical bug.)

## R-COMPARE-01: Guess comparison
Function: `check_guess(guess, secret)` returns `(outcome, message)`.
- `guess == secret`: ("Win", "Correct!").
- `guess > secret`: ("Too High", "Go LOWER!").
- `guess < secret`: ("Too Low", "Go HIGHER!").
The hint direction must always tell the player to move toward the secret. (Historical bug: messages were inverted.)

## R-COMPARE-02: Numeric comparison only
Comparison must be numeric, never lexicographic. If `secret` is passed as a string, it is converted with `int()` before comparing. Example: guess 9 vs secret "10" is Too Low, not Too High. A `TypeError` from int-vs-str comparison must not escape `check_guess`. (Historical bug.)

## R-ATTEMPT-01: Attempt counting
- `attempts` starts at 0 (not 1) for every new game.
- It increments by 1 for each VALID guess submitted, before the guess is evaluated.
- The attempt counter and "Attempts left" banner must agree: after the first valid guess on Normal, attempts is 1 and attempts left is 7. (Historical bug: attempts started at 1, an off-by-one.)

## R-SCORE-01: Score formula
Function: `update_score(attempt_number)` returns `max(10, 100 - (attempt_number - 1) * 10)`.
- Attempt 1: 100. Attempt 2: 90. Attempt 5: 60. Attempt 10 and later: 10 (floor).
- The score is deterministic and depends only on the attempt number.
- The score is never negative, and never random or dependent on parity (even/odd) of the attempt or guess. (Historical bug: wrong guesses sometimes added points and the score could go negative.)

## R-STATE-01: Game status machine
`status` is one of "playing", "won", "lost".
- Valid guess equal to the secret: status "won", message "You won! The secret was X. Final score: S", balloons.
- Valid wrong guess with `attempts >= limit`: status "lost", message "Out of attempts! The secret was X. Score: S".
- Otherwise status stays "playing" and a hint is shown.
When status is not "playing", further guesses are blocked and a "You already won" or "Game over" message is shown; the player must click New Game.

## R-NEWGAME-01: New Game button
Clicking "New Game" at ANY time (including after a win or loss) must reset: `attempts` to 0, `score` to 0, `history` to empty, `status` to "playing", `feedback` to None, and `secret` to a new random number in the CURRENT difficulty's range. The game must be immediately playable again. (Historical bug: after a win/loss the button did nothing because status was not reset, and the secret could be out of range.)

## R-HINT-01: Hint display
- "Show hint" checked (default): show the directional message (Go HIGHER / Go LOWER).
- "Show hint" unchecked: still show feedback, the text "Incorrect!" as a warning. The player must never get silent no-feedback on a wrong guess. (Historical bug.)

## R-FEEDBACK-01: Feedback persistence across reruns
Messages are stored in `session_state.feedback` as a dict `{"type": "hint"|"win"|"lost"|"error", "message": str}`. They are rendered once on the next run and then cleared. Calling `st.rerun()` right after `st.success`/`st.error` erases that message, which is why the dict pattern is used. A message that flashes and disappears is this bug.

## R-STATE-02: Session state keys
| Key | Initial value | Meaning |
|---|---|---|
| `secret` | random int in range | number to guess |
| `attempts` | 0 | valid guesses used |
| `score` | 0 | score from latest valid guess |
| `status` | "playing" | playing / won / lost |
| `history` | [] | raw or parsed guesses in order |
| `feedback` | None | one-shot message dict |
| `difficulty` | current selection | last-seen difficulty |
The text input widget key is `guess_input_{difficulty}`.

## R-DEBUG-01: Developer Debug Info panel
The "Developer Debug Info" expander shows secret, attempts, score, difficulty and history. It is intended for developers and testing; displaying the secret there is expected and is not a bug.

## R-INVARIANTS-01: Testable invariants
Quick checks the debug agent can use to verify a diagnosis or proposed fix:
1. For any valid guess g and secret s: exactly one of Win / Too High / Too Low, matching g==s, g>s, g<s.
2. `update_score(n) >= 10` for all n >= 1, and `update_score(1) == 100`.
3. `parse_guess` of "", None, "abc", "4.5" returns `ok == False`; of "42" returns `(True, 42, None)`.
4. After New Game: attempts == 0, score == 0, history == [], status == "playing", low <= secret <= high.
5. Attempts used never exceeds the difficulty's limit.
6. `get_range_for_difficulty("Easy")` < "Normal" < "Hard" in range width.

## R-SCOPE-01: Out of scope
This game has no multiplayer (no playing against a friend or other players, no two-player mode), no leaderboard or high-scores table, no saved scores or persistence between browser sessions, no accounts or login, no timer, and no online or network features. Requests or complaints about those describe missing features, not bugs; the agent should say the spec does not cover them rather than invent a rule.
