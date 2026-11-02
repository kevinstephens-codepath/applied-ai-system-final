"""Sandboxed tools for the debug agent: read project files, replay game functions, run pytest.

Every tool returns a dict and never raises: failures come back as {"error": "..."} so the model can
see them. A ToolBox is created per request and enforces per-request call budgets.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import logic_utils

PROJECT_ROOT = Path(__file__).parent.resolve()

ALLOWED_SUFFIXES = {".py", ".md", ".json", ".txt", ".toml"}
ALLOWED_NAMES = {"example.env"}
DENIED_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".streamlit", "logs", "node_modules"}

MAX_FILE_BYTES = 200 * 1024
MAX_LINES_PER_READ = 300
MAX_LISTED_FILES = 200
MAX_OUTPUT_CHARS = 4000
PYTEST_TIMEOUT_S = 30
PYTEST_ENV_FLAG = "GLITCH_PYTEST_SUBPROCESS"

READ_BUDGET = 8
REPRO_BUDGET = 6
PYTEST_BUDGET = 2

# function name -> number of positional arguments
REPRO_FUNCTIONS = {
    "parse_guess": 1,
    "check_guess": 2,
    "update_score": 1,
    "get_range_for_difficulty": 1,
}
MAX_ARG_STR_CHARS = 200
_KEYWORD = re.compile(r"^[A-Za-z0-9_ ]{1,100}$")
_SECRET_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _is_denied_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.") or (name.endswith(".env") and name not in ALLOWED_NAMES)


def _part_error(rel: Path, is_file: bool) -> str | None:
    """Check a project-relative path against the denylist (and, for files, the allowlist)."""
    parts = rel.parts
    for part in parts[:-1] if is_file else parts:
        if part in DENIED_DIRS:
            return f"Access to '{part}' is not allowed."
    if is_file and parts:
        name = parts[-1]
        if _is_denied_file(name):
            return "Access to environment files is not allowed."
        if name not in ALLOWED_NAMES and Path(name).suffix not in ALLOWED_SUFFIXES:
            return f"Only {', '.join(sorted(ALLOWED_SUFFIXES))} files can be read."
    return None


class ToolBox:
    def __init__(self, root: Path | str = PROJECT_ROOT, read_budget: int = READ_BUDGET,
                 repro_budget: int = REPRO_BUDGET, pytest_budget: int = PYTEST_BUDGET):
        self.root = Path(root).resolve()
        self._budget = {"run_repro": repro_budget, "run_pytest": pytest_budget}
        self._reads_left = read_budget  # shared by list_files and read_file
        self.log: list[dict] = []
        self.files_read: dict[str, int] = {}  # relative path -> total lines
        self.ranges_read: dict[str, list[tuple[int, int]]] = {}

    # --- dispatch ---

    def call(self, name: str, args) -> dict:
        tools = {"list_files": self.list_files, "read_file": self.read_file,
                 "run_repro": self.run_repro, "run_pytest": self.run_pytest}
        if name not in tools:
            return self._record(name, args, {"error": f"Unknown tool '{name}'. Use one of: {', '.join(tools)}."})
        if not isinstance(args, dict):
            return self._record(name, args, {"error": "args must be an object."})
        if name in ("list_files", "read_file"):
            if self._reads_left <= 0:
                return self._record(name, args, {"error": "Read budget used up."})
            self._reads_left -= 1
        else:
            if self._budget[name] <= 0:
                return self._record(name, args, {"error": f"{name} budget used up."})
            self._budget[name] -= 1
        try:
            result = tools[name](**args)
        except TypeError:
            result = {"error": f"Bad arguments for {name}."}
        return self._record(name, args, result)

    def _record(self, name, args, result: dict) -> dict:
        entry = {"tool": name, "args": args, "ok": "error" not in result, "error": result.get("error")}
        if name == "run_pytest" and entry["ok"]:
            entry["pytest"] = {k: result[k] for k in ("passed", "failed", "errors")}
        self.log.append(entry)
        return result

    # --- path sandbox ---

    def _resolve(self, path, is_file: bool):
        """Return (absolute_path, error). Confines access to the project root."""
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            return None, "path must be a non-empty string."
        given = Path(path)
        if given.is_absolute():
            return None, "Absolute paths are not allowed; use a path relative to the project folder."
        if err := _part_error(Path(*[p for p in given.parts if p != "."]), is_file):
            return None, err
        full = (self.root / given).resolve()
        try:
            rel = full.relative_to(self.root)
        except ValueError:
            return None, "That path is outside the project folder."
        if err := _part_error(rel, is_file):  # catches symlinks that point at denied files
            return None, err
        return full, None

    # --- tools ---

    def list_files(self, subdir: str = ".") -> dict:
        full, err = self._resolve(subdir, is_file=False)
        if err:
            return {"error": err}
        if not full.is_dir():
            return {"error": "Not a directory."}
        files = []
        for dirpath, dirnames, filenames in os.walk(full):
            dirnames[:] = sorted(d for d in dirnames if d not in DENIED_DIRS)
            for name in sorted(filenames):
                path = Path(dirpath, name)
                try:
                    rel = path.resolve().relative_to(self.root)
                except ValueError:
                    continue
                if _part_error(rel, is_file=True) is None and _part_error(path.relative_to(self.root), True) is None:
                    files.append(path.relative_to(self.root).as_posix())
        files.sort()
        truncated = len(files) > MAX_LISTED_FILES
        return {"files": files[:MAX_LISTED_FILES], "truncated": truncated}

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict:
        full, err = self._resolve(path, is_file=True)
        if err:
            return {"error": err}
        if not full.is_file():
            return {"error": "File not found."}
        if full.stat().st_size > MAX_FILE_BYTES:
            return {"error": f"File is larger than {MAX_FILE_BYTES // 1024} KB."}
        if not isinstance(start_line, int) or isinstance(start_line, bool) or start_line < 1:
            return {"error": "start_line must be an integer >= 1."}
        if end_line is not None and (not isinstance(end_line, int) or isinstance(end_line, bool) or end_line < start_line):
            return {"error": "end_line must be an integer >= start_line."}
        try:
            lines = full.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return {"error": "File could not be read as text."}
        total = len(lines)
        last = min(end_line if end_line is not None else total, total, start_line + MAX_LINES_PER_READ - 1)
        if start_line > total:
            return {"error": f"File has only {total} lines."}
        rel = full.relative_to(self.root).as_posix()
        self.files_read[rel] = total
        self.ranges_read.setdefault(rel, []).append((start_line, last))
        content = "\n".join(f"{n:4d}: {lines[n - 1]}" for n in range(start_line, last + 1))
        return {"path": rel, "start_line": start_line, "end_line": last, "total_lines": total,
                "truncated": last < (end_line if end_line is not None else total), "content": content}

    def run_repro(self, function: str, args: list) -> dict:
        """Call one of the game's pure functions with literal arguments."""
        if function not in REPRO_FUNCTIONS:
            return {"error": f"Unknown function. Allowed: {', '.join(REPRO_FUNCTIONS)}."}
        if not isinstance(args, list) or len(args) != REPRO_FUNCTIONS[function]:
            return {"error": f"{function} takes {REPRO_FUNCTIONS[function]} argument(s) in a list."}
        for a in args:
            ok = a is None or (isinstance(a, (int, str)) and not isinstance(a, bool))
            if not ok or (isinstance(a, str) and len(a) > MAX_ARG_STR_CHARS):
                return {"error": "Arguments must be null, integers, or short strings."}
        try:
            result = getattr(logic_utils, function)(*args)
        except Exception as exc:
            return {"function": function, "args": args, "raised": f"{type(exc).__name__}: {exc}"}
        return {"function": function, "args": args, "result": list(result) if isinstance(result, tuple) else result}

    def run_pytest(self, target: str | None = None, keyword: str | None = None) -> dict:
        """Run the project's tests (optionally one file under tests/ and a -k expression)."""
        if os.environ.get(PYTEST_ENV_FLAG):
            return {"error": "run_pytest cannot be nested."}
        argv = [sys.executable, "-m", "pytest", "-q", "--no-header", "-rf", "-p", "no:cacheprovider"]
        if target is not None:
            full, err = self._resolve(target, is_file=True)
            if err:
                return {"error": err}
            tests_dir = (self.root / "tests").resolve()
            if tests_dir not in full.parents or full.suffix != ".py" or not full.is_file():
                return {"error": "target must be an existing .py file inside tests/."}
            argv.append(str(full))
        else:
            argv.append(str(self.root / "tests"))
        if keyword is not None:
            if not isinstance(keyword, str) or not _KEYWORD.match(keyword):
                return {"error": "keyword may only contain letters, digits, underscores and spaces."}
            argv += ["-k", keyword]
        env = {k: v for k, v in os.environ.items() if not any(h in k.upper() for h in _SECRET_ENV_HINTS)}
        env[PYTEST_ENV_FLAG] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            proc = subprocess.run(argv, cwd=self.root, env=env, capture_output=True, text=True,
                                  timeout=PYTEST_TIMEOUT_S, shell=False)
        except subprocess.TimeoutExpired:
            return {"error": f"pytest timed out after {PYTEST_TIMEOUT_S} seconds."}
        output = proc.stdout + proc.stderr

        def count(word):
            m = re.search(rf"(\d+) {word}", output)
            return int(m.group(1)) if m else 0

        return {"passed": count("passed"), "failed": count("failed"), "errors": count("error"),
                "failing_tests": re.findall(r"^FAILED (\S+)", output, re.MULTILINE),
                "exit_code": proc.returncode, "output_tail": output[-MAX_OUTPUT_CHARS:]}
