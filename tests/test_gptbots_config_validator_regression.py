import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

VALIDATOR = (
    Path(__file__).parents[1] / "gptbots-agent-skill" / "scripts" / "validate_gptbots_config.py"
)

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class Problem(TypedDict):
    code: str
    path: str
    message: str
    fix: str


class ValidationResult(TypedDict):
    ok: bool
    errors: list[Problem]
    warnings: list[Problem]


def _decode_result(
    source: str,
    loader: Callable[[str], ValidationResult] = json.loads,
) -> ValidationResult:
    return loader(source)


def _run_validator(tmp_path: Path, config: JsonObject) -> tuple[int, ValidationResult]:
    config_path = tmp_path / "regression.bot"
    _ = config_path.write_text(json.dumps(config), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(config_path), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, _decode_result(completed.stdout)


def test_accepts_minimal_valid_workflow(tmp_path: Path) -> None:
    config: JsonObject = {
        "formatVersion": "1.0",
        "exportType": "WORKFLOW",
        "name": "Workflow regression",
        "botType": "Workflow",
        "workflow": {
            "workflowNodes": [
                {"id": "start", "name": "Start", "type": "START", "x": 0, "y": 0},
                {"id": "end", "name": "End", "type": "END", "x": 300, "y": 0},
            ],
            "workflowEdges": [
                {
                    "id": "edge-1",
                    "sourceNodeID": "start",
                    "targetNodeID": "end",
                    "sourceHandle": "start-source",
                    "targetHandle": "end-target",
                }
            ],
        },
    }

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 0
    assert result["errors"] == []


def test_preserves_top_level_enum_validation(tmp_path: Path) -> None:
    config: JsonObject = {
        "formatVersion": "1.0",
        "exportType": "BOT",
        "name": "Enum regression",
        "botType": "QuestionAnswer",
        "multiModal": {"multiModalInput": {"fileLimit": 1}},
        "reasoningEffort": "INVALID",
        "humanConfig": {"manufacturer": "livechat"},
    }

    exit_code, result = _run_validator(tmp_path, config)
    codes = {problem["code"] for problem in result["errors"]}

    assert exit_code == 1
    assert codes == {"ENUM_REASONING_EFFORT", "HUMAN_MANUFACTURER_INVALID"}


def test_preserves_flow_handle_validation(tmp_path: Path) -> None:
    config: JsonObject = {
        "formatVersion": "1.0",
        "exportType": "BOT",
        "name": "Flow regression",
        "botType": "Flow",
        "flowRule": {
            "components": [
                {
                    "id": 1,
                    "type": "Input",
                    "nextComponents": [
                        {
                            "nextComponentId": 2,
                            "sourceHandle": "right1-wrong",
                            "targetHandle": "left2-output",
                        }
                    ],
                },
                {"id": 2, "type": "Output", "nextComponents": []},
            ]
        },
    }

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 1
    assert "EDGE_SOURCE_KEY" in {problem["code"] for problem in result["errors"]}
