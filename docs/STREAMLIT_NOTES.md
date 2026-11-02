# Streamlit Notes for Debugging Game Glitch Investigator

Background the debug agent needs to explain state and UI bugs in `app.py`. Many of the game's historical bugs were Streamlit state bugs, not logic bugs.

## S-RERUN-01: The script reruns top to bottom
Streamlit re-executes the whole script on every interaction (button click, text change, checkbox, selectbox). Ordinary variables are re-created on each run, so a plain variable like `secret = random.randint(1, 100)` changes on every click. Anything that must survive a click has to live in `st.session_state`.

## S-STATE-01: session_state persists between reruns
`st.session_state` is a dict-like store that survives reruns within one browser session. The standard pattern is to initialize a key only if it is missing (`if "secret" not in st.session_state:`). Forgetting this guard, or initializing outside it, resets the value every run. In this game the keys are listed in R-STATE-02 of `GAME_SPEC.md`.

## S-STATE-02: Detecting a changed widget value
A selectbox returns its current value on every run. To react to a change, store the last-seen value in `session_state` and compare (`session_state.difficulty != difficulty`), then reset the dependent state. Without this comparison nothing resets when the user changes difficulty (see B-01).

## S-RERUN-02: st.rerun() discards messages shown before it
`st.rerun()` stops the current run and starts a new one immediately. Anything drawn with `st.success`, `st.error`, `st.warning` or `st.balloons` just before the call is wiped by the new run. Symptom: a message that flashes or never appears. Fix pattern: save the message in `session_state.feedback`, call `st.rerun()`, then render and clear the stored message near the top of the next run (see B-11, R-FEEDBACK-01).

## S-RERUN-03: Why st.rerun() is used at all
After a button handler changes `session_state` values that were already drawn higher on the page (attempts left, the info banner, history), the page shows stale numbers until another run. Calling `st.rerun()` makes the page redraw with the updated state. Without it the banner lags one click behind.

## S-STOP-01: st.stop() ends the run
`st.stop()` halts execution of the script at that line. The game uses it after showing "Game over" or "You already won" so no input handling runs when `status` is not "playing". Anything that must display must be rendered before the stop (see B-12).

## S-WIDGET-01: Widget keys and state
A widget with a `key` stores its value in `session_state[key]`. The guess box uses `guess_input_{difficulty}`, so each difficulty has its own text box state. Changing a widget's key creates a new widget with empty state. A value cannot be assigned to a widget's key after the widget has been created in the same run; it raises an error.

## S-BUTTON-01: Buttons are only True for one run
`st.button` returns True only on the run triggered by the click, then False again. Logic that depends on a button must be inside the `if st.button(...)` block in that same run, or the result must be copied into `session_state`.

## S-DEBUG-01: Common symptom to cause map
| Symptom | Likely cause |
|---|---|
| Secret number changes on every click | secret not stored in `session_state` or init not guarded |
| Value never updates on screen | state changed after the widget drew and no `st.rerun()` |
| Message flashes then disappears | `st.rerun()` right after drawing the message (S-RERUN-02) |
| Game stays "over" after New Game | `status` not reset to "playing" (B-07) |
| Settings change but game does not reset | no comparison against last-seen value (S-STATE-02) |
| Score or attempts wrong after a click | updated after the display that uses it, with no rerun |
