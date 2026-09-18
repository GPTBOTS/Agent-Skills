from __future__ import annotations

from .common import is_blank
from .constants import NODE_REQUIRED_PARAM
from .model import JsonValue, Report


def check_node_param(node: dict[str, JsonValue], node_path: str, report: Report) -> None:
    node_type = node.get("type")
    required = NODE_REQUIRED_PARAM.get(node_type) if isinstance(node_type, str) else None
    if required and node.get(required) is None and node_type != "END":
        report.err(
            "WF_PARAM_MISSING", f"{node_path}.{required}", f"{node_type} node is missing {required}"
        )
        return
    parameter_checks = {
        "HTTP": ("httpParam", "request", "url", "WF_HTTP_URL", "HTTP node is missing url"),
        "CODE": ("codeParam", None, "code", "WF_CODE_EMPTY", "CODE node code cannot be empty"),
        "DATABASE": (
            "databaseParam",
            None,
            "sqlQuery",
            "WF_DB_SQL",
            "DATABASE node is missing sqlQuery",
        ),
    }
    if node_type in parameter_checks:
        field, nested, value_field, code, message = parameter_checks[node_type]
        value = node.get(field) or {}
        if isinstance(value, dict) and nested:
            value = value.get(nested) or {}
        if not isinstance(value, dict) or is_blank(value.get(value_field)):
            suffix = f".{nested}" if nested else ""
            report.err(code, f"{node_path}.{field}{suffix}.{value_field}", message)
    if node_type == "CONDITION":
        condition = node.get("conditionParam") or {}
        branches = condition.get("conditionBranches") or [] if isinstance(condition, dict) else []
        if not branches:
            report.err(
                "WF_COND_BRANCHES",
                f"{node_path}.conditionParam.conditionBranches",
                "CONDITION must have conditionBranches",
            )
        elif isinstance(branches, list):
            else_count = sum(
                1
                for branch in branches
                if isinstance(branch, dict) and branch.get("type") == "ELSE"
            )
            if else_count != 1:
                report.err(
                    "WF_COND_ELSE",
                    f"{node_path}.conditionParam",
                    f"CONDITION must have exactly one ELSE branch (currently {else_count})",
                )
    if node_type == "INTENT":
        intent = node.get("intentParam") or {}
        if not isinstance(intent, dict) or not (intent.get("intents") or []):
            report.err(
                "WF_INTENT_EMPTY", f"{node_path}.intentParam.intents", "INTENT must have intents"
            )
