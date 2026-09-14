from __future__ import annotations

from .common import check_enum, check_list_enum, is_blank
from .constants import (
    BOT_TYPES,
    CUSTOM_KNOWLEDGE_TYPES,
    DATA_SOURCE_SHOW,
    EXPORT_TYPES,
    MODE_TYPES,
    MULTI_MODAL_DATA_TYPES,
    REASONING_EFFORTS,
    REASONING_SHOW,
    RESPONSE_FORMATS,
)
from .model import JsonObject, JsonValue, Report


def check_top_level(config: JsonValue, report: Report) -> str | None:
    if not isinstance(config, dict):
        report.err("L0_NOT_OBJECT", "$", "The config root must be a JSON object")
        return None
    if is_blank(config.get("name")):
        report.err("L0_NAME", "$.name", "Missing name", "Set a meaningful name")
    export_type = config.get("exportType")
    if export_type not in EXPORT_TYPES:
        report.err(
            "L0_EXPORT_TYPE",
            "$.exportType",
            f"Invalid exportType: {export_type}",
            "Set it to BOT or WORKFLOW",
        )
    bot_type = config.get("botType")
    if bot_type not in BOT_TYPES:
        report.err(
            "L0_BOT_TYPE",
            "$.botType",
            f"Invalid botType: {bot_type}",
            "Set it to QuestionAnswer / Flow / Workflow",
        )
        normalized_bot_type = None
    else:
        normalized_bot_type = str(bot_type)
    if bot_type == "Workflow" and export_type != "WORKFLOW":
        report.err(
            "L0_TYPE_MISMATCH",
            "$.exportType",
            "Workflow requires exportType=WORKFLOW",
        )
    if bot_type in {"QuestionAnswer", "Flow"} and export_type == "WORKFLOW":
        report.err(
            "L0_TYPE_MISMATCH",
            "$.exportType",
            f"{bot_type} requires exportType=BOT",
        )
    if is_blank(config.get("formatVersion")):
        report.warn(
            "L0_FORMAT_VERSION",
            "$.formatVersion",
            'It is recommended to set formatVersion (e.g. "1.0")',
        )
    return normalized_bot_type


def check_top_level_enums(config: JsonObject, report: Report) -> None:
    fields = (
        ("reasoningEffort", REASONING_EFFORTS, "ENUM_REASONING_EFFORT"),
        ("showReasoning", REASONING_SHOW, "ENUM_SHOW_REASONING"),
        ("dataSourceShowType", DATA_SOURCE_SHOW, "ENUM_DATA_SOURCE_SHOW"),
        ("customKnowledgeType", CUSTOM_KNOWLEDGE_TYPES, "ENUM_CUSTOM_KNOWLEDGE"),
        ("responseFormat", RESPONSE_FORMATS, "ENUM_RESPONSE_FORMAT"),
        ("modeType", MODE_TYPES, "ENUM_MODE_TYPE"),
    )
    for field, allowed, code in fields:
        check_enum(
            config.get(field),
            allowed,
            code,
            f"$.{field}",
            report,
            field,
        )
    check_list_enum(
        config.get("multiResponseTypes"),
        MULTI_MODAL_DATA_TYPES,
        "ENUM_MULTI_RESPONSE",
        "$.multiResponseTypes",
        report,
        "multiResponseTypes",
    )


def check_secrets_and_ranges(config: JsonObject, report: Report) -> None:
    plugins = config.get("plugins") or []
    if isinstance(plugins, list):
        for index, plugin in enumerate(plugins):
            if not isinstance(plugin, dict):
                continue
            for field in (
                "authKey",
                "authSecret",
                "oAuthId",
                "oAuthBean",
                "authProvider",
            ):
                if plugin.get(field):
                    report.warn(
                        "SEC_PLUGIN",
                        f"$.plugins[{index}].{field}",
                        f"Plugin credential {field} should not be present (it is cleared on import)",
                        "Leave it blank and reconfigure on the platform after import",
                    )
            if plugin.get("headers") or plugin.get("queries"):
                report.warn(
                    "SEC_PLUGIN_HDR",
                    f"$.plugins[{index}]",
                    "Plugin headers/queries are cleared on import",
                )
    if config.get("apiSecrets"):
        report.warn(
            "SEC_API",
            "$.apiSecrets",
            "apiSecrets should not be present (it is cleared on import)",
        )
    check_range(config.get("creativityLevel"), 0.0, 0.95, "$.creativityLevel", report, True)
    check_range(config.get("docCorrelation"), 0.0, 1.0, "$.docCorrelation", report)
    check_range(config.get("embeddingRate"), 0.0, 1.0, "$.embeddingRate", report)


def check_range(
    value: JsonValue,
    low: float,
    high: float,
    path: str,
    report: Report,
    exclusive_high: bool = False,
) -> None:
    if value is None:
        return
    if isinstance(value, (list, dict)):
        report.err("VAL_NUM", path, f"{path} must be a number")
        return
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        report.err("VAL_NUM", path, f"{path} must be a number")
        return
    out_of_range = normalized < low or (normalized >= high if exclusive_high else normalized > high)
    if out_of_range:
        bound = f"[{low}, {high})" if exclusive_high else f"[{low}, {high}]"
        report.err("VAL_RANGE", path, f"{path}={normalized} is out of range {bound}")
