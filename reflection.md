# 💭 Reflection: Game Glitch Investigator

Answer each question in 3 to 5 sentences. Be specific and honest about what actually happened while you worked. This is about your process, not trying to sound perfect.

## 1. What was broken when you started?

- What did the game look like the first time you ran it?
  - The game is a browser based streamlit app in the form of a simple number guessing game. The game looked to be solid with a decent UI and basic features such as difficuly select, and options such as hiding the hints. There is also a developer feature to show the secret for debugging. I immediatly noticed that the difficulties were weirdly balanced and the number of attempts looked incorrect.
- List at least two concrete bugs you noticed at the start  
  (for example: "the hints were backwards").
  1. I expected the amount of attempts reflected in the difficulty to be shown in the game. The number of attempts actually shown in the game is one lower than shown in the difficulty select. This would confuse players and could feel unfair.
  2. I expected the Hint to show "Go higher" when the amount is below the secret, and "Go lower" when the amount is above the secret. The Hint actually shows "Go lower" when the amount is lower than the secret, and "Go higher" when the amount is higher than the secret. This would confuse players since the hint does not properly reflect against the secret.

**Bug Reproduction Log**

Document at least 3 bugs you found. Add rows as needed.

| Input | Expected Behavior | Actual Behavior | Console Output / Error |
|-------|-------------------|-----------------|------------------------|
| Dificulty change | New Game | Game State stays the same | None |
| Any user input above or below the secret | If input is below, the hint should be "Go higher" vice versa if input is above, the hint should be "Go lower" | If input is below, the hint is "Go lower" vice versa if input is above, the hint is "Go higher" | None |
| Number of attempts | The attempts should reflect the same amount of attempts as listed in the difficulty information | The actual attempts after testing are lower than the listed attempts by exactly 1 | None |
| String as user input | Do not use an attempt, give error feedback. | Uses up an attempt, gives error feedback | None |
| 45.7 as user input when secret is 45 | Do not use attempt, give error feedback | Correct guess, game completed | None |
| New game Button press when state is "Game Over" or "Game Won" | Reset state to "New Game", give feedback that new game has started | Does not reset state, and gives no feedback | None |
| No input when pressing submit guess | Do not use attempt, give error feedback | Uses attempt, gives error feedback | None |
| Submiting a guess with "Show Hint" unchecked and input != secret | Give user feedback that a guess was incorrect | Does not give any feedback | None |
| Difficulty Balance | The scale of difficulty should increase in contrast to the level, easy -> normal -> hard | The normal difficulty is harder than the hard difficulty seeing as the amount of numbers guessable are double | None |

---

## 2. How did you use AI as a teammate?

- Which AI tools did you use on this project (for example: ChatGPT, Gemini, Copilot)?
  - Claude code was used for this project.
- Give one example of an AI suggestion that was correct (including what the AI suggested and how you verified the result).
  - Answer.
- Give one example of an AI suggestion that was incorrect or misleading (including what the AI suggested and how you verified the result).
  - Answer.

---

## 3. Debugging and testing your fixes

- How did you decide whether a bug was really fixed?
  - Answer.
- Describe at least one test you ran (manual or using pytest)  
  and what it showed you about your code.
  - Answer.
- Did AI help you design or understand any tests? How?
  - Answer.

---

## 4. What did you learn about Streamlit and state?

- How would you explain Streamlit "reruns" and session state to a friend who has never used Streamlit?
  - Answer.

---

## 5. Looking ahead: your developer habits

- What is one habit or strategy from this project that you want to reuse in future labs or projects?
  - This could be a testing habit, a prompting strategy, or a way you used Git.
    - Answer.
- What is one thing you would do differently next time you work with AI on a coding task?
  - Answer.
- In one or two sentences, describe how this project changed the way you think about AI generated code.
  - Answer.

## Reflect: All prompts that were used in this project:
| Prompt | Result |
| I am working on debugging a guessing game that is written with python, and is running through streamlit. The first bug I would like to tackle is with the check_guess function. The expected behavior is to show the user "Go HIGHER!" when the user inputs a number that is lower than the secret number, and "Go LOWER!" when the user inputs a number that is higher than the secret number. The current output is opposite.
I would like you to move the check_guess funciton to logic_utils.py, fix the high/low bug, and update the import for app.py. | Result |
| Prompt | Result |