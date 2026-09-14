from __future__ import annotations

from collections.abc import Collection

from .model import JsonValue, Report


def is_blank(value: JsonValue) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


def check_enum(
    value: JsonValue,
    allowed: Collection[str],
    code: str,
    path: str,
    report: Report,
    label: str,
) -> None:
    if value is None or value == "":
        return
    if not isinstance(value, str) or value not in allowed:
        report.err(
            code,
            path,
            f"Invalid {label}: {value}",
            "Use one of: " + ", ".join(sorted(allowed)),
        )


def check_required_enum(
    value: JsonValue,
    allowed: Collection[str],
    code: str,
    path: str,
    report: Report,
    label: str,
) -> None:
    if value is None or value == "":
        report.err(
            code,
            path,
            f"Missing {label}",
            "Use one of: " + ", ".join(sorted(allowed)),
        )
        return
    check_enum(value, allowed, code, path, report, label)


def check_list_enum(
    values: JsonValue,
    allowed: Collection[str],
    code: str,
    path: str,
    report: Report,
    label: str,
) -> None:
    if not isinstance(values, list):
        return
    for index, value in enumerate(values):
        check_enum(value, allowed, code, f"{path}[{index}]", report, label)


def parse_handle(handle: JsonValue) -> tuple[str, str, str] | None:
    if not isinstance(handle, str):
        return None
    if handle.startswith("right"):
        side, body = "right", handle[5:]
    elif handle.startswith("left"):
        side, body = "left", handle[4:]
    else:
        return None
    dash = body.find("-")
    if dash <= 0:
        return None
    return side, body[:dash], body[dash + 1 :].split("_", 1)[0]
