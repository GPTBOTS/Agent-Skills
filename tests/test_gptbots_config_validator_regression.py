import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TypedDict

import pytest

SCRIPTS = Path(__file__).parents[1] / "gptbots-agent-skill" / "scripts"
VALIDATOR = SCRIPTS / "validate_gptbots_config.py"

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


def _load_script(module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{module_name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_accepts_platform_exported_creativity_level_one(tmp_path: Path) -> None:
    config: JsonObject = {
        "formatVersion": "1.0",
        "exportType": "BOT",
        "name": "Creativity boundary",
        "botType": "QuestionAnswer",
        "multiModal": {"multiModalInput": {"fileLimit": 1}},
        "creativityLevel": 1.0,
    }

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 0
    assert "VAL_RANGE" not in {problem["code"] for problem in result["errors"]}


def test_rejects_creativity_level_above_one(tmp_path: Path) -> None:
    config: JsonObject = {
        "formatVersion": "1.0",
        "exportType": "BOT",
        "name": "Creativity out of range",
        "botType": "QuestionAnswer",
        "multiModal": {"multiModalInput": {"fileLimit": 1}},
        "creativityLevel": 1.01,
    }

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 1
    assert "VAL_RANGE" in {problem["code"] for problem in result["errors"]}


def test_agent_builder_accepts_platform_creativity_boundary() -> None:
    builder = _load_script("build_gptbots_agent")
    config = builder.agent_config("Boundary", "Valid identity prompt", creativity=1.0)
    assert config["creativityLevel"] == 1.0


def test_agent_builder_rejects_creativity_above_platform_boundary() -> None:
    builder = _load_script("build_gptbots_agent")
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        _ = builder.agent_config("Boundary", "Valid identity prompt", creativity=1.01)


def test_audio_builder_accepts_platform_creativity_boundary() -> None:
    builder = _load_script("build_gptbots_audioagent")
    config = builder.audio_config(
        "Boundary",
        identity_prompt="Valid identity prompt",
        creativity=1.0,
    )
    assert config["creativityLevel"] == 1.0


def test_audio_builder_rejects_creativity_above_platform_boundary() -> None:
    builder = _load_script("build_gptbots_audioagent")
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        _ = builder.audio_config(
            "Boundary",
            identity_prompt="Valid identity prompt",
            creativity=1.01,
        )


def _supported_extended_bot_configs() -> list[JsonObject]:
    audio_builder = _load_script("build_gptbots_audioagent")
    loop_builder = _load_script("build_gptbots_loopagent")
    return [
        audio_builder.audio_config(
            "Audio entrypoint parity",
            identity_prompt="You are a concise voice support agent.",
        ),
        loop_builder.loopagent_config(
            "Loop entrypoint parity",
            persona="You are a concise support agent.",
        ),
    ]


@pytest.mark.parametrize(
    "config",
    _supported_extended_bot_configs(),
    ids=["audio", "loopagent"],
)
def test_module_entrypoint_matches_script_for_extended_bot_types(
    tmp_path: Path,
    config: JsonObject,
) -> None:
    config_path = tmp_path / "extended.bot"
    _ = config_path.write_text(json.dumps(config), encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": str(SCRIPTS)}
    script_result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(config_path), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    module_result = subprocess.run(
        [sys.executable, "-m", "gptbots_config_validator", str(config_path), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert script_result.returncode == 0
    assert module_result.returncode == script_result.returncode
    assert _decode_result(module_result.stdout) == _decode_result(script_result.stdout)


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
