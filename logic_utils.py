def get_range_for_difficulty(difficulty: str):
    """Return (low, high) inclusive range for a given difficulty."""
    if difficulty == "Easy":
        return 1, 20
    if difficulty == "Normal":
        return 1, 100
    if difficulty == "Hard":
        return 1, 200
    return 1, 100


def parse_guess(raw: str):
    """
    Parse user input into an int guess.

    Returns: (ok: bool, guess_int: int | None, error_message: str | None)
    """
    raise NotImplementedError("Refactor this function from app.py into logic_utils.py")

# FIX - Claude moved the check_guess function from app.py to logic_utils.py and fixed the high/low bug and also fixed a TypeError bug that occurred when the secret was a string.
def check_guess(guess, secret):
    """
    Compare guess to secret and return (outcome, message).

    outcome examples: "Win", "Too High", "Too Low"
    """
    if guess == secret:
        return "Win", "🎉 Correct!"
    try:
        if guess > secret:
            return "Too High", "📉 Go LOWER!"
        else:
            return "Too Low", "📈 Go HIGHER!"
    except TypeError:
        g = str(guess)
        if g == secret:
            return "Win", "🎉 Correct!"
        if int(g) > int(secret):
            return "Too High", "📉 Go LOWER!"
        return "Too Low", "📈 Go HIGHER!"

# FIX - I planned a fix with Claude in plan mode to fix the scoring system. Claude implemented a new scoring formula and 5 tests to validate scores. I verified the tests, and the logic behind Claude's plan before allowing the implementation.
def update_score(attempt_number: int) -> int:
    """Return the current score for a given attempt number.

    Starts at 100 for attempt 1, decreases by 10 per attempt, floors at 10.
    """
    return max(10, 100 - (attempt_number - 1) * 10)
