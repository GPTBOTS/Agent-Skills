from __future__ import annotations

from .common import check_enum, check_required_enum, is_blank
from .constants import (
    CUSTOM_VARIABLE_TYPES,
    HUMAN_CONFIG_STATUS,
    HUMAN_MANUFACTURERS,
    HUMAN_MESSAGE_CODES,
    USER_PROPERTY_TYPES,
)
from .model import JsonObject, JsonValue, Report


def check_bot_fields(config: JsonObject, report: Report) -> None:
    if "humanConfig" in config:
        check_human_config(config.get("humanConfig"), "$.humanConfig", report)
    custom_names = check_custom_variables(config, report)
    check_user_properties(config, custom_names, report)


def check_human_config(
    human_config: JsonValue,
    path: str,
    report: Report,
) -> None:
    if human_config is None:
        return
    if not isinstance(human_config, dict):
        report.err("HUMAN_CONFIG_TYPE", path, "humanConfig must be an object")
        return
    check_enum(
        human_config.get("manufacturer"),
        HUMAN_MANUFACTURERS,
        "HUMAN_MANUFACTURER_INVALID",
        path + ".manufacturer",
        report,
        "human-service manufacturer",
    )
    check_enum(
        human_config.get("status"),
        HUMAN_CONFIG_STATUS,
        "HUMAN_STATUS_INVALID",
        path + ".status",
        report,
        "humanConfig status",
    )
    switch = human_config.get("sendHumanTipSwitch")
    if switch is not None and not isinstance(switch, bool):
        report.err(
            "HUMAN_TIP_SWITCH_TYPE",
            path + ".sendHumanTipSwitch",
            "sendHumanTipSwitch must be a JSON boolean",
            "Use true or false without quotes",
        )
    check_human_messages(human_config.get("multiLanguages"), path, report)


def check_human_messages(
    multi_languages: JsonValue,
    human_config_path: str,
    report: Report,
) -> None:
    if multi_languages is None:
        return
    languages_path = human_config_path + ".multiLanguages"
    if not isinstance(multi_languages, dict):
        report.err(
            "HUMAN_LANGUAGES_TYPE",
            languages_path,
            "multiLanguages must be an object keyed by language",
        )
        return
    for language, messages in multi_languages.items():
        path = f"{languages_path}.{language}"
        if not isinstance(messages, list):
            report.err(
                "HUMAN_LANGUAGE_MESSAGES_TYPE",
                path,
                "Each language value must be an array of service-status messages",
            )
            continue
        seen_codes: set[int] = set()
        for index, message in enumerate(messages):
            message_path = f"{path}[{index}]"
            if not isinstance(message, dict):
                report.err(
                    "HUMAN_MESSAGE_OBJECT",
                    message_path,
                    "A service-status message must be an object",
                )
                continue
            code = message.get("code")
            if not isinstance(code, int) or isinstance(code, bool):
                report.err(
                    "HUMAN_MESSAGE_CODE_TYPE",
                    message_path + ".code",
                    "Service-status code must be an integer",
                )
            else:
                if code in seen_codes:
                    report.err(
                        "HUMAN_MESSAGE_CODE_DUP",
                        message_path + ".code",
                        f"Duplicate service-status code {code} for language {language}",
                    )
                seen_codes.add(code)
                if code not in HUMAN_MESSAGE_CODES:
                    report.warn(
                        "HUMAN_MESSAGE_CODE_UNKNOWN",
                        message_path + ".code",
                        f"Unknown service-status code: {code}",
                        "Confirm the code against the deployed backend version",
                    )
            if not isinstance(message.get("text"), str):
                report.err(
                    "HUMAN_MESSAGE_TEXT_TYPE",
                    message_path + ".text",
                    "Service-status text must be a string",
                )


def check_custom_variables(config: JsonObject, report: Report) -> set[str]:
    if "customVariables" not in config or config.get("customVariables") is None:
        return set()
    custom_variables = config.get("customVariables")
    if not isinstance(custom_variables, list):
        report.err(
            "CUSTOM_VARIABLES_TYPE",
            "$.customVariables",
            "customVariables must be an array",
        )
        return set()
    names: set[str] = set()
    for index, variable in enumerate(custom_variables):
        path = f"$.customVariables[{index}]"
        if not isinstance(variable, dict):
            report.err(
                "CUSTOM_VARIABLE_OBJECT",
                path,
                "A custom-variable definition must be an object",
            )
            continue
        name = variable.get("name")
        if not isinstance(name, str) or is_blank(name):
            report.err(
                "CUSTOM_VARIABLE_NAME",
                path + ".name",
                "Custom-variable name must be a non-empty string",
            )
        else:
            if name in names:
                report.err(
                    "CUSTOM_VARIABLE_NAME_DUP",
                    path + ".name",
                    f"Duplicate custom-variable name: {name}",
                )
            names.add(name)
            if not name.startswith("var_"):
                report.warn(
                    "CUSTOM_VARIABLE_PREFIX",
                    path + ".name",
                    f"Custom-variable name does not use the recommended var_ prefix: {name}",
                    f"Prefer var_{name} for newly generated variables",
                )
        check_required_enum(
            variable.get("type"),
            CUSTOM_VARIABLE_TYPES,
            "CUSTOM_VARIABLE_TYPE",
            path + ".type",
            report,
            "custom-variable type",
        )
    return names


def check_user_properties(
    config: JsonObject,
    custom_names: set[str],
    report: Report,
) -> None:
    if "userProperties" not in config or config.get("userProperties") is None:
        return
    user_properties = config.get("userProperties")
    if not isinstance(user_properties, list):
        report.err(
            "USER_PROPERTIES_TYPE",
            "$.userProperties",
            "userProperties must be an array",
        )
        return
    names: set[str] = set()
    for index, user_property in enumerate(user_properties):
        path = f"$.userProperties[{index}]"
        if not isinstance(user_property, dict):
            report.err(
                "USER_PROPERTY_OBJECT",
                path,
                "A user-property definition must be an object",
            )
            continue
        name = user_property.get("name")
        if not isinstance(name, str) or is_blank(name):
            report.err(
                "USER_PROPERTY_NAME",
                path + ".name",
                "User-property name must be a non-empty string",
            )
        else:
            if name in names:
                report.err(
                    "USER_PROPERTY_NAME_DUP",
                    path + ".name",
                    f"Duplicate user-property name: {name}",
                )
            if name in custom_names:
                report.err(
                    "PROPERTY_NAME_COLLISION",
                    path + ".name",
                    f"User property collides with a custom variable: {name}",
                    "Use unique names across customVariables and userProperties",
                )
            names.add(name)
        check_required_enum(
            user_property.get("type"),
            USER_PROPERTY_TYPES,
            "USER_PROPERTY_TYPE",
            path + ".type",
            report,
            "user-property type",
        )
        for flag in ("chatUpdate", "chatQuery"):
            value = user_property.get(flag)
            if value is not None and not isinstance(value, bool):
                report.err(
                    "USER_PROPERTY_FLAG_TYPE",
                    f"{path}.{flag}",
                    f"{flag} must be a JSON boolean",
                    "Use true or false without quotes",
                )
        runtime_fields = {
            field
            for field in ("accountId", "userProperties")
            if user_property.get(field) is not None
        }
        for field in sorted(runtime_fields):
            report.err(
                "USER_PROPERTY_RUNTIME_DATA",
                f"{path}.{field}",
                f"Runtime user data field must not be exported: {field}",
                "Keep only the user-property definition and its default value",
            )
