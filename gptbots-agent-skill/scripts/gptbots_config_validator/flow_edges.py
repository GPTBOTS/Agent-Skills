from __future__ import annotations

from .common import parse_handle
from .constants import HANDLE_SOURCE_KEY, HANDLE_TARGET_KEY
from .model import JsonValue, Report


def check_component_edges(
    component: dict[str, JsonValue],
    path: str,
    type_by_id: dict[JsonValue, JsonValue],
    report: Report,
) -> None:
    owner_id = component.get("id")
    owner_type = component.get("type")
    source_key = HANDLE_SOURCE_KEY.get(owner_type) if isinstance(owner_type, str) else None
    connections = component.get("nextComponents") or []
    if not isinstance(connections, list):
        return
    for index, connection in enumerate(connections):
        if not isinstance(connection, dict):
            continue
        edge_path = f"{path}.nextComponents[{index}]"
        source_handle = connection.get("sourceHandle")
        target_handle = connection.get("targetHandle")
        next_id = connection.get("nextComponentId")
        parsed_source = parse_handle(source_handle) if source_handle else None
        if source_handle and (parsed_source is None or parsed_source[0] != "right"):
            report.err(
                "EDGE_SOURCE_FORMAT",
                edge_path + ".sourceHandle",
                f"Malformed source handle: {source_handle}",
                "Expected right{componentId}-{key}[_suffix]",
            )
        elif parsed_source:
            _, source_id, key = parsed_source
            if owner_id is not None and source_id != str(owner_id):
                report.err(
                    "EDGE_SOURCE_ID_MISMATCH",
                    edge_path + ".sourceHandle",
                    f"sourceHandle id {source_id} != owning component id {owner_id} (the canvas will draw a distorted edge)",
                    f"Use right{owner_id}-...",
                )
            if source_key is not None and key != source_key:
                report.err(
                    "EDGE_SOURCE_KEY",
                    edge_path + ".sourceHandle",
                    f"sourceHandle key '{key}' does not match a {owner_type} component (expected '{source_key}')",
                    f"Use right{owner_id}-{source_key}...",
                )
        if next_id is not None:
            check_target_handle(target_handle, next_id, type_by_id, edge_path, report)
        elif target_handle:
            report.err(
                "EDGE_TARGET_ORPHAN",
                edge_path + ".targetHandle",
                f"targetHandle '{target_handle}' is set but nextComponentId is empty",
                "Set nextComponentId, or remove the targetHandle",
            )


def check_target_handle(
    target_handle: JsonValue,
    next_id: JsonValue,
    type_by_id: dict[JsonValue, JsonValue],
    edge_path: str,
    report: Report,
) -> None:
    if not target_handle:
        report.err(
            "EDGE_TARGET_MISSING",
            edge_path + ".targetHandle",
            f"nextComponentId={next_id} but targetHandle is empty (the canvas will draw a distorted edge)",
            "Set targetHandle to left{nextComponentId}-{key}",
        )
        return
    parsed_target = parse_handle(target_handle)
    if parsed_target is None or parsed_target[0] != "left":
        report.err(
            "EDGE_TARGET_FORMAT",
            edge_path + ".targetHandle",
            f"Malformed target handle: {target_handle}",
            "Expected left{componentId}-{key}",
        )
        return
    _, target_id, key = parsed_target
    if target_id != str(next_id):
        report.err(
            "EDGE_TARGET_ID_MISMATCH",
            edge_path + ".targetHandle",
            f"targetHandle id {target_id} != nextComponentId {next_id} (the canvas will draw a distorted edge)",
            f"Use left{next_id}-...",
        )
    target_type = type_by_id.get(next_id)
    expected_key = HANDLE_TARGET_KEY.get(target_type) if isinstance(target_type, str) else None
    if expected_key is not None and key != expected_key:
        report.err(
            "EDGE_TARGET_KEY",
            edge_path + ".targetHandle",
            f"targetHandle key '{key}' does not match the target {target_type} component (expected '{expected_key}')",
            f"Use left{next_id}-{expected_key}",
        )
