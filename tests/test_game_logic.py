from logic_utils import check_guess, parse_guess, update_score


# --- parse_guess tests ---

def test_parse_guess_valid_integer():
    ok, value, err = parse_guess("42")
    assert ok is True
    assert value == 42
    assert err is None


def test_parse_guess_empty_string():
    ok, value, err = parse_guess("")
    assert ok is False
    assert value is None
    assert err is not None and "guess" in err.lower()


def test_parse_guess_none_input():
    ok, value, err = parse_guess(None)
    assert ok is False
    assert value is None
    assert err is not None and "guess" in err.lower()


def test_parse_guess_non_numeric():
    ok, value, err = parse_guess("abc")
    assert ok is False
    assert value is None
    assert err is not None and "number" in err.lower()


def test_parse_guess_decimal_rejected():
    ok, value, err = parse_guess("3.5")
    assert ok is False
    assert value is None
    assert err is not None


def test_parse_guess_negative_integer():
    ok, value, err = parse_guess("-7")
    assert ok is True
    assert value == -7
    assert err is None


# --- check_guess Normal int/int path ---

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


# --- update_score tests ---

def test_attempt_1_gives_100():
    assert update_score(1) == 100

def test_attempt_2_gives_90():
    assert update_score(2) == 90

def test_attempt_10_gives_10():
    assert update_score(10) == 10

def test_score_floors_at_10():
    assert update_score(15) == 10

def test_score_never_negative():
    assert update_score(9999) >= 0
