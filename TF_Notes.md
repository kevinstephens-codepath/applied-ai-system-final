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
