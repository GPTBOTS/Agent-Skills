from __future__ import annotations

from .common import check_enum, check_list_enum
from .constants import (
    COMBINE_TYPES,
    CUSTOM_KNOWLEDGE_TYPES,
    DATA_SOURCE_SHOW,
    FILE_MODES,
    FLOW_CONTENT_TYPES,
    FORM_GATHER_TYPES,
    GATHER_FIELD_TYPES,
    GATHER_VALUE_TYPES,
    MULTI_MODAL_DATA_TYPES,
    OPTION_FIELD_TYPES,
    PROMPT_MESSAGE_TYPES,
    PROPERTY_TYPES,
    REASONING_EFFORTS,
    REASONING_SHOW,
    REGULAR_CATEGORIES,
    RESPONSE_FORMATS,
    VARIABLE_OPERATE_TYPES,
    VARIABLE_TYPES,
)
from .model import JsonValue, Report


def check_component_enums(component: dict[str, JsonValue], path: str, report: Report) -> None:
    scalar_fields = (
        ("reasoningEffort", REASONING_EFFORTS, "COMP_ENUM_REASONING_EFFORT"),
        ("showReasoning", REASONING_SHOW, "COMP_ENUM_SHOW_REASONING"),
        ("dataSourceShowType", DATA_SOURCE_SHOW, "COMP_ENUM_DATA_SOURCE_SHOW"),
        ("customKnowledgeType", CUSTOM_KNOWLEDGE_TYPES, "COMP_ENUM_CUSTOM_KNOWLEDGE"),
        ("responseFormat", RESPONSE_FORMATS, "COMP_ENUM_RESPONSE_FORMAT"),
        ("contentType", FLOW_CONTENT_TYPES, "COMP_ENUM_CONTENT_TYPE"),
    )
    for field, allowed, code in scalar_fields:
        check_enum(component.get(field), allowed, code, f"{path}.{field}", report, field)
    check_list_enum(
        component.get("multiResponseTypes"),
        MULTI_MODAL_DATA_TYPES,
        "COMP_ENUM_MULTI_RESPONSE",
        path + ".multiResponseTypes",
        report,
        "multiResponseTypes",
    )
    for field in ("messages", "datasetMessages"):
        messages = component.get(field)
        if isinstance(messages, list):
            for index, message in enumerate(messages):
                if isinstance(message, dict):
                    check_enum(
                        message.get("type"),
                        PROMPT_MESSAGE_TYPES,
                        "COMP_ENUM_MESSAGE_TYPE",
                        f"{path}.{field}[{index}].type",
                        report,
                        "message type",
                    )
    gather_fields = component.get("gatherFields")
    if isinstance(gather_fields, list):
        for index, gather_field in enumerate(gather_fields):
            if not isinstance(gather_field, dict):
                continue
            item_path = f"{path}.gatherFields[{index}]"
            check_enum(
                gather_field.get("gatherType"),
                GATHER_FIELD_TYPES,
                "COMP_ENUM_GATHER_TYPE",
                item_path + ".gatherType",
                report,
                "gatherType",
            )
            check_enum(
                gather_field.get("valueType"),
                GATHER_VALUE_TYPES,
                "COMP_ENUM_GATHER_VALUE_TYPE",
                item_path + ".valueType",
                report,
                "valueType",
            )
            check_enum(
                gather_field.get("optionFieldType"),
                OPTION_FIELD_TYPES,
                "COMP_ENUM_OPTION_FIELD_TYPE",
                item_path + ".optionFieldType",
                report,
                "optionFieldType",
            )
    gather_control = component.get("gatherControl")
    if isinstance(gather_control, dict):
        check_enum(
            gather_control.get("formGatherType"),
            FORM_GATHER_TYPES,
            "COMP_ENUM_FORM_GATHER_TYPE",
            path + ".gatherControl.formGatherType",
            report,
            "formGatherType",
        )
    variable_configs = component.get("variableSetValueConfigs")
    if isinstance(variable_configs, list):
        for index, variable in enumerate(variable_configs):
            if isinstance(variable, dict):
                item_path = f"{path}.variableSetValueConfigs[{index}]"
                check_enum(
                    variable.get("variableType"),
                    VARIABLE_TYPES,
                    "COMP_ENUM_VARIABLE_TYPE",
                    item_path + ".variableType",
                    report,
                    "variableType",
                )
                check_enum(
                    variable.get("variableOperateType"),
                    VARIABLE_OPERATE_TYPES,
                    "COMP_ENUM_VARIABLE_OPERATE_TYPE",
                    item_path + ".variableOperateType",
                    report,
                    "variableOperateType",
                )
    check_rule_groups(component.get("regularGroups"), path, report)
    multimodal = component.get("multiModalLlmInput")
    if isinstance(multimodal, dict):
        check_enum(
            multimodal.get("fileMode"),
            FILE_MODES,
            "COMP_ENUM_FILE_MODE",
            path + ".multiModalLlmInput.fileMode",
            report,
            "fileMode",
        )


def check_rule_groups(groups: JsonValue, path: str, report: Report) -> None:
    if not isinstance(groups, list):
        return
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        group_path = f"{path}.regularGroups[{group_index}]"
        check_enum(
            group.get("combine"),
            COMBINE_TYPES,
            "COMP_ENUM_COMBINE",
            group_path + ".combine",
            report,
            "combine",
        )
        items = group.get("items")
        if not isinstance(items, list):
            continue
        for item_index, item in enumerate(items):
            if isinstance(item, dict):
                item_path = f"{group_path}.items[{item_index}]"
                check_enum(
                    item.get("category"),
                    REGULAR_CATEGORIES,
                    "COMP_ENUM_REGULAR_CATEGORY",
                    item_path + ".category",
                    report,
                    "category",
                )
                check_enum(
                    item.get("type"),
                    PROPERTY_TYPES,
                    "COMP_ENUM_PROPERTY_TYPE",
                    item_path + ".type",
                    report,
                    "property type",
                )
