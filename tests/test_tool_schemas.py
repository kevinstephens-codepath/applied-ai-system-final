import inspect

from agent_tools import ToolBox
from guardrails import REQUIRED_FIELDS, TEXT_FIELDS, VERDICTS
from tool_schemas import FINAL_TOOL_NAME, TOOL_NAMES, TOOL_SCHEMAS

SCHEMAS = {t["name"]: t for t in TOOL_SCHEMAS}
TOOLS = [name for name in TOOL_NAMES if name != FINAL_TOOL_NAME]


def test_every_schema_matches_a_toolbox_method():
    assert sorted(TOOLS) == sorted(["list_files", "read_file", "run_repro", "run_pytest"])
    for name in TOOLS:
        params = set(inspect.signature(getattr(ToolBox, name)).parameters) - {"self"}
        schema = SCHEMAS[name]["parameters"]
        assert set(schema["properties"]) == params, name


def test_required_parameters_have_no_default_in_the_method():
    for name in TOOLS:
        signature = inspect.signature(getattr(ToolBox, name)).parameters
        for required in SCHEMAS[name]["parameters"].get("required", []):
            assert signature[required].default is inspect.Parameter.empty, (name, required)
        optional = set(SCHEMAS[name]["parameters"]["properties"]) - set(SCHEMAS[name]["parameters"].get("required", []))
        for param in optional:
            assert signature[param].default is not inspect.Parameter.empty, (name, param)


def test_run_repro_functions_match_the_allowed_list():
    from agent_tools import REPRO_FUNCTIONS
    assert set(SCHEMAS["run_repro"]["parameters"]["properties"]["function"]["enum"]) == set(REPRO_FUNCTIONS)


def test_final_answer_schema_matches_the_output_guardrail():
    schema = SCHEMAS[FINAL_TOOL_NAME]["parameters"]
    assert set(REQUIRED_FIELDS) <= set(schema["properties"])
    assert set(schema["required"]) == set(REQUIRED_FIELDS)
    assert set(schema["properties"]["verdict"]["enum"]) == set(VERDICTS)
    assert set(TEXT_FIELDS) <= set(schema["properties"])
    for extra in ("code_evidence", "self_critique", "code_feedback"):
        assert extra in schema["properties"]


def test_tool_names_are_unique_and_final_is_last():
    assert len(set(TOOL_NAMES)) == len(TOOL_NAMES)
    assert TOOL_NAMES[-1] == FINAL_TOOL_NAME


def test_schemas_are_accepted_by_the_sdk():
    from google.genai import types
    for schema in TOOL_SCHEMAS:
        declaration = types.FunctionDeclaration(**schema)
        assert declaration.name == schema["name"]
