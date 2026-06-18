import random
import streamlit as st
from logic_utils import check_guess, get_range_for_difficulty, update_score


# FIX THIS - The guess parsing should be in logic_utils.py
def parse_guess(raw: str):
    if raw is None:
        return False, None, "Enter a guess."

    if raw == "":
        return False, None, "Enter a guess."
    # FIX THIS - We should not allow decimal guesses. The game depends on whole numbers.
    try:
        if "." in raw:
            value = int(float(raw))
        else:
            value = int(raw)
    except Exception:
        return False, None, "That is not a number."

    return True, value, None



st.set_page_config(page_title="Glitchy Guesser", page_icon="🎮")

st.title("🎮 Game Glitch Investigator")
st.caption("An AI-generated guessing game. Something is off.")

st.sidebar.header("Settings")

difficulty = st.sidebar.selectbox(
    "Difficulty",
    ["Easy", "Normal", "Hard"],
    index=1,
)

# FIX - Claude adjusted the easy difficulty to have a higher limit, leaving the original attempt limits for normal and hard.
attempt_limit_map = {
    "Easy": 10,
    "Normal": 8,
    "Hard": 5,
}
attempt_limit = attempt_limit_map[difficulty]

low, high = get_range_for_difficulty(difficulty)

st.sidebar.caption(f"Range: {low} to {high}")
st.sidebar.caption(f"Attempts allowed: {attempt_limit}")

if "secret" not in st.session_state:
    st.session_state.secret = random.randint(low, high)

if "attempts" not in st.session_state:
    # FIX - I set the initial attempts to 0 instead of 1, otherwise the player starts with a penalty.
    st.session_state.attempts = 0

if "score" not in st.session_state:
    st.session_state.score = 0

if "status" not in st.session_state:
    st.session_state.status = "playing"

if "history" not in st.session_state:
    st.session_state.history = []

# FIX - Fix suggested by Claude: Changing the difficulty will now cause a state update to reset the game so users don't end up with the wrong range or attempts when selecting a different difficulty
if st.session_state.get("difficulty") != difficulty:
    st.session_state.difficulty = difficulty
    st.session_state.secret = random.randint(low, high)
    st.session_state.attempts = 0
    st.session_state.score = 0
    st.session_state.status = "playing"
    # Reset history when changing difficulty to avoid confusion with previous guesses that may be out of range for the new difficulty level.
    st.session_state.history = []

st.subheader("Make a guess")

st.info(
    # FIX - I updated the instructions to reflect the actual range based on the difficulty level instead of just 1 - 100
    f"Guess a number between {low} and {high}. "
    f"Attempts left: {attempt_limit - st.session_state.attempts}"
)

with st.expander("Developer Debug Info"):
    st.write("Secret:", st.session_state.secret)
    st.write("Attempts:", st.session_state.attempts)
    st.write("Score:", st.session_state.score)
    st.write("Difficulty:", difficulty)
    st.write("History:", st.session_state.history)

raw_guess = st.text_input(
    "Enter your guess:",
    key=f"guess_input_{difficulty}"
)

col1, col2, col3 = st.columns(3)
with col1:
    submit = st.button("Submit Guess 🚀")
with col2:
    new_game = st.button("New Game 🔁")
with col3:
    show_hint = st.checkbox("Show hint", value=True)

if new_game:
    st.session_state.attempts = 0
    # FIX - new_game button will now reset the score.
    st.session_state.score = 0
    # FIX - new_game button will now reset the history of guesses.
    st.session_state.history = []
    # FIX - The secret number now reflects the difficulty level when starting a new game using low and high.
    st.session_state.secret = random.randint(low, high)
    # FIX - Claude helped me find a state bug with setting the status to "playing" on new game, which was causing the game to not properly reset after winning or losing.
    st.session_state.status = "playing";
    st.success("New game started.")
    st.rerun()

# FIX THIS - The game does not properly handle the case where the player has already won or lost.
if st.session_state.status != "playing":
    if st.session_state.status == "won":
        st.success("You already won. Start a new game to play again.")
    else:
        st.error("Game over. Start a new game to try again.")
    st.stop()

# FIX THIS - Need to rerun() after submitting a guess to update the UI with the new state, otherwise the user won't see the results of their guess until they interact with the app in a different way.
if submit:
    # FIX THIS - We should parse the guess before incrementing attempts, otherwise invalid guesses are penalized.
    st.session_state.attempts += 1

    ok, guess_int, err = parse_guess(raw_guess)

    if not ok:
        st.session_state.history.append(raw_guess)
        st.error(err)
    else:
        st.session_state.history.append(guess_int)

        # FIX THIS - This appears to be a purpose made glitch where the secret is sometimes a string and sometimes an int depending on the attemtps.
        if st.session_state.attempts % 2 == 0:
            secret = str(st.session_state.secret)
        else:
            secret = st.session_state.secret

        outcome, message = check_guess(guess_int, secret)

        # FIX THIS - There should be feedback even if hint is not enabled, otherwise the user has no other feedback to show that it was a successful guess.
        if show_hint:
            st.warning(message)

        st.session_state.score = update_score(attempt_number=st.session_state.attempts)

        if outcome == "Win":
            st.balloons()
            st.session_state.status = "won"
            st.success(
                f"You won! The secret was {st.session_state.secret}. "
                f"Final score: {st.session_state.score}"
            )
        else:
            if st.session_state.attempts >= attempt_limit:
                st.session_state.status = "lost"
                st.error(
                    f"Out of attempts! "
                    f"The secret was {st.session_state.secret}. "
                    f"Score: {st.session_state.score}"
                )

st.divider()
# Updated the caption to reflect changes made to the game.
st.caption("Built by an AI that claims this code is production-ready. Bugfixed by a human and Claude code who say \"We should test that.\"")
