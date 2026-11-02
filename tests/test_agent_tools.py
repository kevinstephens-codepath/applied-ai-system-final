import os

import pytest

from agent_tools import PYTEST_ENV_FLAG, ToolBox


@pytest.fixture
def project(tmp_path):
    """A small fake project with files the sandbox should and should not expose."""
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "docs").mkdir()
    (root / "app.py").write_text("line one\nline two\nline three\nline four\n")
    (root / "docs" / "notes.md").write_text("# notes\n")
    (root / "example.env").write_text("GEMINI_API_KEY=your_api_key_here\n")
    (root / ".env").write_text("GEMINI_API_KEY=real-secret\n")
    (root / ".env.local").write_text("X=1\n")
    (root / "prod.env").write_text("X=1\n")
    (root / ".git" / "config.txt").write_text("git\n")
    (root / ".venv" / "lib" / "mod.py").write_text("venv\n")
    (root / "logs" / "run.json").write_text("{}\n")
    (root / "binary.png").write_bytes(b"\x89PNG")
    (root / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret\n")
    (root / "escape.txt").symlink_to(outside)
    (root / "env_link.txt").symlink_to(root / ".env")
    return root


@pytest.fixture
def box(project):
    return ToolBox(root=project)


# --- path sandbox ---

def test_reads_allowed_file_with_numbered_lines(box):
    result = box.read_file("app.py")
    assert result["path"] == "app.py"
    assert result["total_lines"] == 4
    assert result["content"].splitlines()[0] == "   1: line one"
    assert result["truncated"] is False


def test_line_slicing(box):
    result = box.read_file("app.py", start_line=2, end_line=3)
    assert (result["start_line"], result["end_line"]) == (2, 3)
    assert result["content"] == "   2: line two\n   3: line three"


def test_reads_nested_file_and_example_env(box):
    assert "error" not in box.read_file("docs/notes.md")
    assert "your_api_key_here" in box.read_file("example.env")["content"]


@pytest.mark.parametrize("path", [
    "../outside.txt",
    "docs/../../outside.txt",
    "/etc/passwd",
    "escape.txt",          # symlink pointing outside the project
])
def test_paths_outside_project_refused(box, path):
    result = box.read_file(path)
    assert "error" in result
    assert "outside" not in result.get("content", "")


@pytest.mark.parametrize("path", [
    ".env",
    ".env.local",
    "prod.env",
    "./.env",
    "docs/../.env",
    "env_link.txt",        # symlink pointing at .env inside the project
    ".git/config.txt",
    ".venv/lib/mod.py",
    "logs/run.json",
])
def test_denied_files_refused(box, path):
    result = box.read_file(path)
    assert "error" in result
    assert "content" not in result


def test_disallowed_extension_refused(box):
    assert "error" in box.read_file("binary.png")


@pytest.mark.parametrize("path", [None, "", "  ", 5, "a\x00b"])
def test_bad_path_values_refused(box, path):
    assert "error" in box.read_file(path)


def test_missing_file_and_bad_ranges(box):
    assert "error" in box.read_file("nope.py")
    assert "error" in box.read_file("app.py", start_line=0)
    assert "error" in box.read_file("app.py", start_line=3, end_line=2)
    assert "error" in box.read_file("app.py", start_line=99)
    assert "error" in box.read_file("app.py", start_line="1")


def test_line_cap_truncates(project):
    (project / "big.py").write_text("\n".join(f"x{i}" for i in range(1000)))
    result = ToolBox(root=project).read_file("big.py")
    assert result["end_line"] == 300
    assert result["truncated"] is True
    assert result["total_lines"] == 1000


def test_oversize_file_refused(project):
    (project / "huge.md").write_text("a" * (201 * 1024))
    assert "error" in ToolBox(root=project).read_file("huge.md")


def test_list_files_shows_only_allowed_files(box):
    files = box.list_files()["files"]
    assert files == ["app.py", "docs/notes.md", "example.env", "tests/test_x.py"]


def test_list_files_subdir_and_denied_dirs(box):
    assert box.list_files("docs")["files"] == ["docs/notes.md"]
    assert "error" in box.list_files(".git")
    assert "error" in box.list_files("../")
    assert "error" in box.list_files("app.py")


# --- call dispatch and budgets ---

def test_read_budget_enforced_across_list_and_read(project):
    box = ToolBox(root=project, read_budget=2)
    assert "error" not in box.call("read_file", {"path": "app.py"})
    assert "error" not in box.call("list_files", {})
    assert box.call("read_file", {"path": "app.py"}) == {"error": "Read budget used up."}


def test_call_rejects_unknown_tool_and_bad_args(box):
    assert "error" in box.call("delete_file", {"path": "app.py"})
    assert "error" in box.call("read_file", ["app.py"])
    assert "error" in box.call("read_file", {"path": "app.py", "mode": "w"})


def test_call_log_and_reads_tracked(box):
    box.call("read_file", {"path": "app.py", "start_line": 2, "end_line": 3})
    box.call("read_file", {"path": ".env"})
    assert [(e["tool"], e["ok"]) for e in box.log] == [("read_file", True), ("read_file", False)]
    assert box.files_read == {"app.py": 4}
    assert box.ranges_read == {"app.py": [(2, 3)]}


def test_no_write_tools_exposed(box):
    for name in ("write_file", "delete_file", "run_shell", "exec"):
        assert "error" in box.call(name, {})


# --- run_repro ---

def test_repro_calls_game_functions():
    box = ToolBox()
    assert box.run_repro("update_score", [3])["result"] == 80
    assert box.run_repro("check_guess", [5, "30"])["result"] == ["Too Low", "📈 Go HIGHER!"]
    assert box.run_repro("parse_guess", ["45.7"])["result"][0] is False
    assert box.run_repro("get_range_for_difficulty", ["Hard"])["result"] == [1, 200]


def test_repro_reports_exceptions_as_data():
    result = ToolBox().run_repro("check_guess", [5, "abc"])
    assert "ValueError" in result["raised"]


@pytest.mark.parametrize("function, args", [
    ("os.system", ["ls"]),
    ("open", [".env"]),
    ("update_score", []),
    ("update_score", [1, 2]),
    ("update_score", "3"),
    ("update_score", [[3]]),
    ("update_score", [True]),
    ("parse_guess", ["x" * 500]),
])
def test_repro_rejects_bad_calls(function, args):
    assert "error" in ToolBox().run_repro(function, args)


def test_repro_budget(project):
    box = ToolBox(root=project, repro_budget=1)
    assert "error" not in box.call("run_repro", {"function": "update_score", "args": [1]})
    assert "budget" in box.call("run_repro", {"function": "update_score", "args": [1]})["error"]


# --- run_pytest (single test file only: a full run would re-enter these tests) ---

def test_pytest_runs_one_file():
    result = ToolBox().run_pytest("tests/test_game_logic.py")
    assert result["failed"] == 0 and result["passed"] == 21
    assert result["exit_code"] == 0


def test_pytest_keyword_filter():
    result = ToolBox().run_pytest("tests/test_game_logic.py", keyword="score")
    assert result["passed"] == 2 and result["failed"] == 0  # the two tests with "score" in their name


def test_pytest_reports_failures(project):
    (project / "tests" / "test_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    result = ToolBox(root=project).run_pytest("tests/test_bad.py")
    assert result["failed"] == 1
    assert result["failing_tests"] == ["tests/test_bad.py::test_bad"]


@pytest.mark.parametrize("target", [
    "logic_utils.py",
    "../outside.txt",
    "/etc/passwd",
    "tests",
    "tests/missing.py",
    ".env",
])
def test_pytest_target_must_be_a_test_file(project, target):
    assert "error" in ToolBox(root=project).run_pytest(target)


@pytest.mark.parametrize("keyword", ["a; rm -rf /", "x $(id)", "a' or '1", "", "x" * 200, 5])
def test_pytest_keyword_validated(keyword):
    assert "error" in ToolBox().run_pytest("tests/test_game_logic.py", keyword=keyword)


def test_pytest_cannot_nest(monkeypatch):
    monkeypatch.setenv(PYTEST_ENV_FLAG, "1")
    assert "nested" in ToolBox().run_pytest("tests/test_game_logic.py")["error"]


def test_pytest_child_does_not_see_secrets(project, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    (project / "tests" / "test_env.py").write_text(
        "import os\n\ndef test_env():\n    assert 'GEMINI_API_KEY' not in os.environ\n"
    )
    assert ToolBox(root=project).run_pytest("tests/test_env.py")["passed"] == 1
    assert os.environ["GEMINI_API_KEY"] == "super-secret-value"
