from __future__ import annotations

from .bot_fields import check_human_config
from .common import is_blank
from .constants import FLOW_COMPONENT_TYPES
from .flow_edges import check_component_edges
from .flow_fields import check_component_enums
from .model import JsonValue, Report


def check_flow(flow_rule: JsonValue, report: Report) -> None:
    if not isinstance(flow_rule, dict):
        report.err("FLOW_MISSING", "$.flowRule", "Missing flowRule")
        return
    components = flow_rule.get("components") or []
    if not isinstance(components, list) or not components:
        report.err(
            "FLOW_NO_COMPONENTS",
            "$.flowRule.components",
            "A FlowAgent must have at least one component",
        )
        return
    inputs = [item for item in components if isinstance(item, dict) and item.get("type") == "Input"]
    outputs = [
        item for item in components if isinstance(item, dict) and item.get("type") == "Output"
    ]
    if len(inputs) != 1:
        report.err(
            "FLOW_INPUT",
            "$.flowRule",
            f"There must be exactly one Input component (currently {len(inputs)})",
        )
    if len(outputs) != 1:
        report.err(
            "FLOW_OUTPUT",
            "$.flowRule",
            f"There must be exactly one Output component (currently {len(outputs)})",
        )

    component_ids: set[JsonValue] = set()
    for index, component in enumerate(components):
        path = f"$.flowRule.components[{index}]"
        if not isinstance(component, dict):
            report.err("FLOW_COMP_OBJ", path, "A component must be an object")
            continue
        component_id = component.get("id")
        if component_id is None:
            report.err("FLOW_COMP_ID", path + ".id", "Component id cannot be empty")
        elif isinstance(component_id, (str, int, float, bool)):
            if component_id in component_ids:
                report.err(
                    "FLOW_COMP_ID_DUP", path + ".id", f"Duplicate component id: {component_id}"
                )
            component_ids.add(component_id)
        else:
            report.err("FLOW_COMP_ID", path + ".id", "Component id must be scalar")
        component_type = component.get("type")
        if is_blank(component_type):
            report.err("FLOW_COMP_TYPE", path + ".type", "Component type cannot be empty")
        elif not isinstance(component_type, str) or component_type not in FLOW_COMPONENT_TYPES:
            report.err(
                "FLOW_COMP_TYPE_INVALID",
                path + ".type",
                f"Invalid component type: {component_type}",
                "Use a FlowComponentType value: " + ", ".join(sorted(FLOW_COMPONENT_TYPES)),
            )

    type_by_id = {
        component.get("id"): component.get("type")
        for component in components
        if isinstance(component, dict) and isinstance(component.get("id"), (str, int, float, bool))
    }
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            continue
        path = f"$.flowRule.components[{index}]"
        component_type = component.get("type")
        next_components = component.get("nextComponents") or []
        if not isinstance(next_components, list):
            next_components = []
        for next_index, connection in enumerate(next_components):
            if not isinstance(connection, dict):
                continue
            next_id = connection.get("nextComponentId")
            if next_id is not None and (
                not isinstance(next_id, (str, int, float, bool)) or next_id not in component_ids
            ):
                report.err(
                    "FLOW_NEXT_MISSING",
                    f"{path}.nextComponents[{next_index}].nextComponentId",
                    f"Points to a non-existent component: {next_id}",
                )
        if component_type in {"Output", "Human"} and next_components:
            report.warn(
                "FLOW_TERMINAL",
                path,
                f"{component_type} is a terminal node and usually should have no downstream",
            )
        if component_type not in {"Output", "Human", "Message"} and not next_components:
            report.warn(
                "FLOW_NO_NEXT",
                path,
                f"The {component_type} component has no downstream connection; please confirm whether a branch was missed",
            )
        check_component_enums(component, path, report)
        check_component_edges(component, path, type_by_id, report)
        if component_type == "Human":
            if "humanConfig" not in component:
                report.warn(
                    "FLOW_HUMAN_CONFIG_MISSING",
                    path + ".humanConfig",
                    "Human component should include component-level humanConfig",
                    "Copy the intended humanConfig onto the Human component",
                )
            else:
                check_human_config(component.get("humanConfig"), path + ".humanConfig", report)
