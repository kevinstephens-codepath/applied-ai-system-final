# Applied AI Systems Project
## Guidelines:
3a. Extension from P1: Game Glitch Investigator → RAG-enhanced bug analysis  

Original system: Takes a game crash description or code snippet; uses an LLM to explain the bug and suggest a fix.  

Strong extension (RAG path):  

User input (bug description)  
      ↓  
Input guardrail — validate format; block empty or nonsense input  
      ↓  
Retrieval — search indexed documentation (e.g., game engine docs, error code reference)  
      ↓  
Context assembly — top-k retrieved chunks + original bug description  
      ↓  
LLM generation — produce explanation and fix grounded in retrieved docs  
      ↓  
Output guardrail — check confidence / length / refusal if context is absent  
      ↓  
Formatted response + logging  

Required files: retriever.py (or rag_retriever.py), updated main.py (or app.py) with integrated retrieval call, /assets/ with system diagram, README.md with sample inputs/outputs, model_card.md with reflection.  

Guardrail minimum bar: Input validation (non-empty, structured query) + output handling for low-confidence or no-context case.  

## Part 0 - 
Picked Game Glitch Investigator -> RAG enhanced bug analysis, cloned my original completed Game Glitch Investigator Project from when I was a student (Not the ai-final version, just the project version)
Setup git, VSCode, and installed environment/basic test run. Ready to rock and roll.

## Part 1 -
For part one, it seems that they want us to make sure we have a plan envisioned for our project. I'm going to follow the standard RAG enhanced bug analysis flow on Game Glitch Investigator

This will look like a standard debug RAG loop, we will have base documentation that the agent will use as a basis for how the game should function, then I will link tools that the RAG agent can use to read code and compare functionality with intended design for the app. The loop will continue through multiple RAG flow steps and give a final debug score and suggestions to fix present bugs.
RAG -> Agentic workflow -> Debug output

Planning with Claude -> RAG_Plan.md -> All of our planning steps and actions are there. Full transparency is within that file.

## Part 2 - 
Had Claude help me generate the diagram, and verified it's contents, making sure it matches our plan.
The design diagram is a png and svg file under assets and also linked in the README

## Part 3 -
- First draft of README done with help of AI, then refined by me.

## Part 4 -
Reliability Evaluation is recorded within README.

## Part 5 -
What are the limitations or biases in your system?
> A. 
Could your AI be misused, and how would you prevent that?
> A.
What surprised you while testing your AI's reliability?
> A.
describe your collaboration with AI during this project. Identify one suggestion you accepted and one you did not accept as written, and say why you rejected or changed it. It does not have to be a suggestion that was wrong: over-engineered, out of scope, harder to read, or a poor fit for your system all count. If nothing the AI suggested was outright wrong, look for one you still changed: shortened, simplified, renamed, or scoped down. That counts.
> A.
