import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypedDict

import pytest

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


def _base_config() -> JsonObject:
    return {
        "formatVersion": "1.0",
        "exportType": "BOT",
        "name": "Validator fixture",
        "botType": "QuestionAnswer",
        "multiModal": {"multiModalInput": {"fileLimit": 1}},
    }


def _run_validator(tmp_path: Path, config: JsonObject) -> tuple[int, ValidationResult]:
    config_path = tmp_path / "fixture.bot"
    _ = config_path.write_text(json.dumps(config), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(config_path), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, _decode_result(completed.stdout)


def _codes(
    result: ValidationResult,
    level: Literal["errors", "warnings"],
) -> set[str]:
    return {problem["code"] for problem in result[level]}


def test_accepts_latest_bot_configuration_fields(tmp_path: Path) -> None:
    config = _base_config()
    config.update(
        {
            "humanConfig": {
                "manufacturer": "LiveDesk",
                "status": "enable",
                "sendHumanTipSwitch": True,
                "multiLanguages": {
                    "en_US": [{"code": 84, "text": "Transfer failed."}],
                },
            },
            "customVariables": [
                {"name": "var_ticket_id", "type": "STRING", "value": ""},
            ],
            "userProperties": [
                {
                    "name": "customer_tier",
                    "showName": "Customer tier",
                    "type": "string",
                    "value": "",
                    "desc": "Support tier",
                    "chatUpdate": True,
                    "chatQuery": True,
                },
            ],
        }
    )

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 0
    assert result["errors"] == []


def test_old_bot_without_latest_fields_remains_valid(tmp_path: Path) -> None:
    exit_code, result = _run_validator(tmp_path, _base_config())

    assert exit_code == 0
    assert result["errors"] == []


@pytest.mark.parametrize(
    ("human_config", "expected_code"),
    [
        ({"sendHumanTipSwitch": "true"}, "HUMAN_TIP_SWITCH_TYPE"),
        (
            {"multiLanguages": {"en_US": [{"code": "84", "text": "Failed"}]}},
            "HUMAN_MESSAGE_CODE_TYPE",
        ),
        (
            {"multiLanguages": {"en_US": [{"code": 84, "text": 123}]}},
            "HUMAN_MESSAGE_TEXT_TYPE",
        ),
        (
            {
                "multiLanguages": {
                    "en_US": [
                        {"code": 84, "text": "First"},
                        {"code": 84, "text": "Second"},
                    ]
                }
            },
            "HUMAN_MESSAGE_CODE_DUP",
        ),
    ],
)
def test_rejects_invalid_human_service_tip_fields(
    tmp_path: Path,
    human_config: JsonObject,
    expected_code: str,
) -> None:
    config = _base_config()
    config["humanConfig"] = human_config

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 1
    assert expected_code in _codes(result, "errors")


def test_warns_for_unknown_service_status_code(tmp_path: Path) -> None:
    config = _base_config()
    config["humanConfig"] = {"multiLanguages": {"en_US": [{"code": 999, "text": "Future status"}]}}

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 0
    assert "HUMAN_MESSAGE_CODE_UNKNOWN" in _codes(result, "warnings")


@pytest.mark.parametrize(
    ("custom_variables", "expected_code"),
    [
        ([{"name": "var_missing_type"}], "CUSTOM_VARIABLE_TYPE"),
        ([{"name": "var_bad", "type": "UNSUPPORTED"}], "CUSTOM_VARIABLE_TYPE"),
        (
            [
                {"name": "var_duplicate", "type": "STRING"},
                {"name": "var_duplicate", "type": "NUMBER"},
            ],
            "CUSTOM_VARIABLE_NAME_DUP",
        ),
    ],
)
def test_rejects_invalid_custom_variable_definitions(
    tmp_path: Path,
    custom_variables: list[JsonValue],
    expected_code: str,
) -> None:
    config = _base_config()
    config["customVariables"] = custom_variables

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 1
    assert expected_code in _codes(result, "errors")


def test_warns_when_custom_variable_lacks_var_prefix(tmp_path: Path) -> None:
    config = _base_config()
    config["customVariables"] = [{"name": "ticket_id", "type": "STRING"}]

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 0
    assert "CUSTOM_VARIABLE_PREFIX" in _codes(result, "warnings")


@pytest.mark.parametrize(
    ("user_properties", "expected_code"),
    [
        ([{"name": "tier"}], "USER_PROPERTY_TYPE"),
        ([{"name": "tier", "type": "unknown"}], "USER_PROPERTY_TYPE"),
        (
            [
                {"name": "tier", "type": "string"},
                {"name": "tier", "type": "number"},
            ],
            "USER_PROPERTY_NAME_DUP",
        ),
        (
            [{"name": "tier", "type": "string", "chatUpdate": "true"}],
            "USER_PROPERTY_FLAG_TYPE",
        ),
        (
            [{"name": "tier", "type": "string", "accountId": "real-user"}],
            "USER_PROPERTY_RUNTIME_DATA",
        ),
    ],
)
def test_rejects_invalid_user_property_definitions(
    tmp_path: Path,
    user_properties: list[JsonValue],
    expected_code: str,
) -> None:
    config = _base_config()
    config["userProperties"] = user_properties

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 1
    assert expected_code in _codes(result, "errors")


def test_rejects_property_name_collision(tmp_path: Path) -> None:
    config = _base_config()
    config["customVariables"] = [{"name": "var_shared", "type": "STRING"}]
    config["userProperties"] = [{"name": "var_shared", "type": "string"}]

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 1
    assert "PROPERTY_NAME_COLLISION" in _codes(result, "errors")


def test_validates_human_config_inside_flow_component(tmp_path: Path) -> None:
    config = _base_config()
    config["botType"] = "Flow"
    config["flowRule"] = {
        "components": [
            {
                "id": 1,
                "type": "Input",
                "nextComponents": [
                    {
                        "nextComponentId": 2,
                        "sourceHandle": "right1-input",
                        "targetHandle": "left2-artificial",
                    }
                ],
            },
            {
                "id": 2,
                "type": "Human",
                "humanConfig": {"sendHumanTipSwitch": "true"},
                "nextComponents": [],
            },
            {"id": 3, "type": "Output", "nextComponents": []},
        ]
    }

    exit_code, result = _run_validator(tmp_path, config)

    assert exit_code == 1
    assert "HUMAN_TIP_SWITCH_TYPE" in _codes(result, "errors")
    assert result["errors"][0]["path"].startswith("$.flowRule.components[1].humanConfig")
