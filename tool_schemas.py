"""Function declarations the model chooses from each turn (plain dicts; no SDK dependency).

Each non-final entry mirrors a ToolBox method in agent_tools.py; tests keep the two in sync.
"""

FINAL_TOOL_NAME = "final_answer"

TOOL_SCHEMAS = [
    {
        "name": "list_files",
        "description": "List the readable project files (source, docs, tests) under a folder.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"subdir": {"type": "STRING", "description": "Folder relative to the project root. Default '.'."}},
        },
    },
    {
        "name": "read_file",
        "description": "Read lines of one project file. Lines are returned with their line numbers.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "File path relative to the project root, e.g. logic_utils.py."},
                "start_line": {"type": "INTEGER", "description": "First line to read (1-based)."},
                "end_line": {"type": "INTEGER", "description": "Last line to read."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_repro",
        "description": "Call one of the game's functions with literal arguments and see what it returns.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "function": {
                    "type": "STRING",
                    "enum": ["parse_guess", "check_guess", "update_score", "get_range_for_difficulty"],
                },
                "args": {
                    "type": "ARRAY",
                    "description": "Positional arguments, e.g. [12] for update_score or [5, 30] for check_guess.",
                    "items": {"any_of": [{"type": "INTEGER"}, {"type": "STRING"}], "nullable": True},
                },
            },
            "required": ["function", "args"],
        },
    },
    {
        "name": "run_pytest",
        "description": "Run the project's tests and report passes and failures.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {"type": "STRING", "description": "Optional test file, e.g. tests/test_game_logic.py."},
                "keyword": {"type": "STRING", "description": "Optional name filter (letters, digits, underscores, spaces)."},
            },
        },
    },
    {
        "name": FINAL_TOOL_NAME,
        "description": "Give your final diagnosis. Call this once you have enough evidence.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "verdict": {"type": "STRING", "enum": ["bug", "known_fixed_bug", "correct_behavior", "not_covered"]},
                "summary": {"type": "STRING", "description": "One or two sentences."},
                "root_cause": {"type": "STRING", "description": "Why it happens, or why it is not a bug."},
                "suggested_fix": {"type": "STRING", "description": "What to change, or 'No change needed'."},
                "cited_rules": {
                    "type": "ARRAY",
                    "description": "Ids of CONTEXT chunks you relied on, e.g. R-SCORE-01.",
                    "items": {"type": "STRING"},
                },
                "code_evidence": {
                    "type": "ARRAY",
                    "description": "Line ranges you actually read that support the diagnosis.",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "file": {"type": "STRING"},
                            "start_line": {"type": "INTEGER"},
                            "end_line": {"type": "INTEGER"},
                        },
                        "required": ["file", "start_line", "end_line"],
                    },
                },
                "self_critique": {"type": "STRING", "description": "What is weak or unverified in this diagnosis."},
                "code_feedback": {"type": "STRING", "description": "Feedback on the app's code or tests."},
            },
            "required": ["verdict", "summary", "root_cause", "suggested_fix", "cited_rules"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOL_SCHEMAS]
