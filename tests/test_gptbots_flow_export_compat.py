import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final, TypedDict

import pytest

SCRIPTS: Final = Path(__file__).parents[1] / "gptbots-agent-skill" / "scripts"
STG_EXPORT: Final = Path(__file__).parent / "fixtures" / "stg-variable-flow-export.bot"


class Problem(TypedDict):
    code: str
    path: str


class ValidationResult(TypedDict):
    errors: list[Problem]
    warnings: list[Problem]


def _decode_result(
    source: str, loader: Callable[[str], ValidationResult] = json.loads,
) -> ValidationResult:
    return loader(source)


class Edge(TypedDict):
    nextComponentId: int
    sourceHandle: str
    targetHandle: str
    name: str | None


class HumanConfig(TypedDict, total=False):
    sendHumanTipSwitch: bool | str | None


class Component(TypedDict, total=False):
    id: int
    type: str
    humanConfig: HumanConfig | None
    nextComponents: list[Edge]


class FlowRule(TypedDict):
    components: list[Component]


class MultiModalInput(TypedDict):
    fileLimit: int


class MultiModal(TypedDict):
    multiModalInput: MultiModalInput


class FlowConfig(TypedDict, total=False):
    formatVersion: str
    exportType: str
    name: str
    botType: str
    humanConfig: HumanConfig
    flowRule: FlowRule
    multiModal: MultiModal


@pytest.fixture(params=["script", "module"])
def entrypoint(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def _validate(
    tmp_path: Path, config: FlowConfig, entrypoint: str,
) -> tuple[int, ValidationResult]:
    path = tmp_path / "flow.bot"
    _ = path.write_text(json.dumps(config), encoding="utf-8")
    target = (
        [str(SCRIPTS / "validate_gptbots_config.py")]
        if entrypoint == "script" else ["-m", "gptbots_config_validator"]
    )
    result = subprocess.run(
        [sys.executable, *target, str(path), "--json"],
        env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
        capture_output=True, text=True, check=False,
    )
    return result.returncode, _decode_result(result.stdout)


def _human_flow() -> FlowConfig:
    return {
        "formatVersion": "1.0", "exportType": "BOT",
        "name": "Human fallback", "botType": "Flow",
        "multiModal": {"multiModalInput": {"fileLimit": 1}},
        "flowRule": {"components": [
            {"id": 1, "type": "Input", "nextComponents": [{
                "nextComponentId": 2, "sourceHandle": "right1-input",
                "targetHandle": "left2-artificial", "name": None,
            }]},
            {"id": 2, "type": "Human", "nextComponents": []},
            {"id": 3, "type": "Output", "nextComponents": []},
        ]},
    }


def _exported_flow(
    loader: Callable[[str], FlowConfig] = json.loads,
) -> FlowConfig:
    return loader(STG_EXPORT.read_text(encoding="utf-8"))


@pytest.mark.parametrize("top_level_fallback", [False, True])
def test_warns_when_human_component_config_is_missing(
    tmp_path: Path, entrypoint: str, top_level_fallback: bool,
) -> None:
    config = _human_flow()
    if top_level_fallback:
        config["humanConfig"] = {"sendHumanTipSwitch": True}

    exit_code, result = _validate(tmp_path, config, entrypoint)

    assert exit_code == 0, result
    assert result["errors"] == []
    assert [(item["code"], item["path"]) for item in result["warnings"]] == [
        ("FLOW_HUMAN_CONFIG_MISSING", "$.flowRule.components[1].humanConfig"),
    ]


@pytest.mark.parametrize("human_config", [
    None, {}, {"sendHumanTipSwitch": None},
    {"sendHumanTipSwitch": False}, {"sendHumanTipSwitch": True},
])
def test_preserves_explicit_human_config_and_optional_tip_switch(
    tmp_path: Path, entrypoint: str, human_config: HumanConfig | None,
) -> None:
    config = _human_flow()
    config["flowRule"]["components"][1]["humanConfig"] = human_config

    exit_code, result = _validate(tmp_path, config, entrypoint)

    assert exit_code == 0, result
    assert result["errors"] == []
    assert result["warnings"] == []


def test_accepts_unmodified_stg_variable_success_edge(
    tmp_path: Path, entrypoint: str,
) -> None:
    config = _exported_flow()

    exit_code, result = _validate(tmp_path, config, entrypoint)

    assert exit_code == 0, result
    assert result["errors"] == []


def test_accepts_legacy_variable_success_edge(
    tmp_path: Path, entrypoint: str,
) -> None:
    config = _exported_flow()
    config["flowRule"]["components"][2]["nextComponents"][0]["sourceHandle"] = (
        "right3-variable_true"
    )

    exit_code, result = _validate(tmp_path, config, entrypoint)

    assert exit_code == 0, result
    assert result["errors"] == []


@pytest.mark.parametrize(("handle", "name", "expected_code"), [
    ("right3-variable", None, "VAR_SUCCESS_HANDLE"),
    ("right3-variable", "", "VAR_SUCCESS_HANDLE"),
    ("right3-variable", "_exception", "VAR_SUCCESS_HANDLE"),
    ("right3-variable_true", None, "VAR_SUCCESS_HANDLE"),
    ("right99-variable", "_true", "EDGE_SOURCE_ID_MISMATCH"),
    ("right3-wrong", "_true", "EDGE_SOURCE_KEY"),
])
def test_rejects_invalid_variable_success_edges(
    tmp_path: Path, entrypoint: str, handle: str, name: str | None,
    expected_code: str,
) -> None:
    config = _exported_flow()
    edge = config["flowRule"]["components"][2]["nextComponents"][0]
    edge.update(sourceHandle=handle, name=name)

    exit_code, result = _validate(tmp_path, config, entrypoint)

    assert exit_code == 1
    assert expected_code in {item["code"] for item in result["errors"]}
