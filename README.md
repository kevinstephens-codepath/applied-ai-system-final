# 🎮 Game Glitch Investigator: The Impossible Guesser

## 🚨 The Situation

You asked an AI to build a simple "Number Guessing Game" using Streamlit.
It wrote the code, ran away, and now the game is unplayable. 

- You can't win.
- The hints lie to you.
- The secret number seems to have commitment issues.

## 🛠️ Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run the broken app: `python -m streamlit run app.py`

## 🕵️‍♂️ Your Mission

1. **Play the game.** Open the "Developer Debug Info" tab in the app to see the secret number. Try to win.
2. **Find the State Bug.** Why does the secret number change every time you click "Submit"? Ask ChatGPT: *"How do I keep a variable from resetting in Streamlit when I click a button?"*
3. **Fix the Logic.** The hints ("Higher/Lower") are wrong. Fix them.
4. **Refactor & Test.** - Move the logic into `logic_utils.py`.
   - Run `pytest` in your terminal.
   - Keep fixing until all tests pass!

## 📝 Document Your Experience

- [✅] Describe the game's purpose.
  - This is a web browser number guessing game. To win, you must guess the secret number.
- [✅] Detail which bugs you found.
  - I found at least 10 major bugs in this application, including hints being incorrect, TypeErrors in parsing the guess, and lack of user feedback.
- [✅] Explain what fixes you applied.
  - With Claudes help I fixed over 8 major bugs:
   1. Game state did not update upon difficulty change.
   2. High/Low bug on guess, feedback was reversed, was giving High when guess was Low, and Low when guess was High.
   3. The number of attempts was off by 1 when starting the game.
   4. Certain Types of inputs were not giving user feedback, such as strings and decimals.
   5. The new game button was not working after winning or losing the game
   6. There was no user feedback when submitting a guess without hints being toggled on.
   7. Attempts were being used even when the user submitted an incorrect type of input.
   8. The difficulty of the game was off balance.
   9. The score was capable of going negative, and would randomly reward points for an incorrect guess.


## 📸 Demo Walkthrough

Describe your fixed game in numbered steps so a reader can follow along without watching a video:

1. User enters a guess of 56
2. Game returns "Too High"
3. User enters a guess of 50 -> "Too High"
4. Score and attempts update after the user makes guesses
5. When user inputs correct guess, game shows score and gives balloons, and the game ends.

**Screenshot** *(optional)*: <!-- Insert a screenshot of your fixed, winning game here -->

## 🧪 Test Results

```
================================ test session starts ================================
platform darwin -- Python 3.13.13, pytest-9.0.3, pluggy-1.6.0 -- /Users/ks3276/projects/CodePath/AI110-Glitch-Investigator/ai110-module1show-gameglitchinvestigator-starter/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/ks3276/projects/CodePath/AI110-Glitch-Investigator/ai110-module1show-gameglitchinvestigator-starter
plugins: anyio-4.13.0
collected 21 items                                                                  

tests/test_game_logic.py::test_parse_guess_valid_integer PASSED               [  4%]
tests/test_game_logic.py::test_parse_guess_empty_string PASSED                [  9%]
tests/test_game_logic.py::test_parse_guess_none_input PASSED                  [ 14%]
tests/test_game_logic.py::test_parse_guess_non_numeric PASSED                 [ 19%]
tests/test_game_logic.py::test_parse_guess_decimal_rejected PASSED            [ 23%]
tests/test_game_logic.py::test_parse_guess_negative_integer PASSED            [ 28%]
tests/test_game_logic.py::test_exact_match_returns_win PASSED                 [ 33%]
tests/test_game_logic.py::test_guess_too_high_returns_too_high_and_go_lower PASSED [ 38%]
tests/test_game_logic.py::test_guess_too_low_returns_too_low_and_go_higher PASSED [ 42%]
tests/test_game_logic.py::test_off_by_one_above PASSED                        [ 47%]
tests/test_game_logic.py::test_off_by_one_below PASSED                        [ 52%]
tests/test_game_logic.py::test_boundary_guess_of_one PASSED                   [ 57%]
tests/test_game_logic.py::test_large_numbers PASSED                           [ 61%]
tests/test_game_logic.py::test_string_secret_exact_match PASSED               [ 66%]
tests/test_game_logic.py::test_string_secret_guess_too_low PASSED             [ 71%]
tests/test_game_logic.py::test_string_secret_guess_too_high PASSED            [ 76%]
tests/test_game_logic.py::test_attempt_1_gives_100 PASSED                     [ 80%]
tests/test_game_logic.py::test_attempt_2_gives_90 PASSED                      [ 85%]
tests/test_game_logic.py::test_attempt_10_gives_10 PASSED                     [ 90%]
tests/test_game_logic.py::test_score_floors_at_10 PASSED                      [ 95%]
tests/test_game_logic.py::test_score_never_negative PASSED                    [100%]

================================ 21 passed in 0.02s =================================
```

## 🚀 Stretch Features

- [X] [If you choose to complete Challenge 4, describe the Enhanced UI changes here — a screenshot is optional]
