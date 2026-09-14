from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from .bot_fields import check_bot_fields
from .constants import MAX_FILE_SIZE
from .flow import check_flow
from .model import JsonValue, Problem, Report
from .top_level import check_secrets_and_ranges, check_top_level, check_top_level_enums
from .workflow import check_workflow_graph


class ValidationResult(TypedDict):
    ok: bool
    errors: list[Problem]
    warnings: list[Problem]


class ParsedArguments(argparse.Namespace):
    file: str
    json: bool

    def __init__(self) -> None:
        super().__init__()
        self.file = ""
        self.json = False


def decode_json(
    source: str,
    loader: Callable[[str], JsonValue] = json.loads,
) -> JsonValue:
    return loader(source)


def validate(config: JsonValue, raw_length: int) -> Report:
    report = Report()
    if raw_length > MAX_FILE_SIZE:
        report.err("L0_SIZE", "$", f"The file exceeds the {MAX_FILE_SIZE}-byte limit")
    bot_type = check_top_level(config, report)
    if not isinstance(config, dict):
        return report
    check_top_level_enums(config, report)
    match bot_type:
        case "Workflow":
            check_workflow_graph(config.get("workflow"), report, "$.workflow")
        case "Flow":
            check_flow(config.get("flowRule"), report)
            if config.get("workflow"):
                check_workflow_graph(config.get("workflow"), report, "$.workflow")
        case "QuestionAnswer" | None:
            pass
        case _:
            pass
    check_secrets_and_ranges(config, report)
    check_bot_fields(config, report)
    return report


def main(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(description="GPTBots .bot/.flow config quality check")
    _ = parser.add_argument("file", help="path to the .bot or .flow file")
    _ = parser.add_argument("--json", action="store_true", help="output the result as JSON")
    args = parser.parse_args(arguments, namespace=ParsedArguments())
    try:
        raw = Path(args.file).read_bytes()
    except OSError as error:
        print(f"Unable to read file: {error}", file=sys.stderr)
        return 2
    try:
        config = decode_json(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        result: ValidationResult = {
            "ok": False,
            "errors": [
                {
                    "code": "L0_JSON",
                    "path": "$",
                    "message": f"Invalid JSON: {error}",
                    "fix": "Fix the JSON syntax",
                }
            ],
            "warnings": [],
        }
        emit(result, args.json)
        return 1
    report = validate(config, len(raw))
    result = {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
    }
    emit(result, args.json)
    return 0 if report.ok else 1


def emit(result: ValidationResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result["ok"]:
        warning_suffix = f" ({len(result['warnings'])} warning(s))" if result["warnings"] else ""
        print("✅ Quality check passed" + warning_suffix)
    else:
        error_count = len(result["errors"])
        warning_count = len(result["warnings"])
        print(f"❌ Quality check failed: {error_count} error(s), {warning_count} warning(s)")
    for problem in result["errors"]:
        print_problem("ERROR", problem)
    for problem in result["warnings"]:
        print_problem("WARN ", problem)


def print_problem(level: str, problem: Problem) -> None:
    fix = f" → {problem['fix']}" if problem["fix"] else ""
    print(f"  [{level} {problem['code']}] {problem['path']}: {problem['message']}{fix}")
