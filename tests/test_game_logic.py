from logic_utils import check_guess


# --- Normal int/int path ---

def test_exact_match_returns_win():
    outcome, message = check_guess(42, 42)
    assert outcome == "Win"
    assert message == "🎉 Correct!"


def test_guess_too_high_returns_too_high_and_go_lower():
    outcome, message = check_guess(50, 30)
    assert outcome == "Too High"
    assert "LOWER" in message


def test_guess_too_low_returns_too_low_and_go_higher():
    outcome, message = check_guess(10, 30)
    assert outcome == "Too Low"
    assert "HIGHER" in message


def test_off_by_one_above():
    outcome, _ = check_guess(31, 30)
    assert outcome == "Too High"


def test_off_by_one_below():
    outcome, _ = check_guess(29, 30)
    assert outcome == "Too Low"


def test_boundary_guess_of_one():
    outcome, _ = check_guess(1, 1)
    assert outcome == "Win"


def test_large_numbers():
    outcome, _ = check_guess(999, 1000)
    assert outcome == "Too Low"


# --- String secret path (TypeError branch) ---

def test_string_secret_exact_match():
    outcome, message = check_guess(42, "42")
    assert outcome == "Win"
    assert message == "🎉 Correct!"


def test_string_secret_guess_too_low():
    outcome, message = check_guess(5, "30")
    assert outcome == "Too Low"
    assert "HIGHER" in message


def test_string_secret_guess_too_high():
    outcome, message = check_guess(80, "30")
    assert outcome == "Too High"
    assert "LOWER" in message
