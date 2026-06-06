from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import publisher
from .config import load_config
from .packager import package
from .source import load_source
from .validator import has_blocking, validate


def _render(problems) -> str:
    lines = []
    for p in problems:
        prefix = "ERROR" if p.level == "error" else "WARN"
        line = f"{prefix}: [{p.code}] {p.message}"
        if p.hint:
            line += f"\n        hint: {p.hint}"
        lines.append(line)
    return "\n".join(lines)


def _load(args):
    config = load_config(Path(args.config) if args.config else None)
    path = args.path or config.skill_path
    return config, path, load_source(path)


def _print_summary(problems) -> None:
    if problems:
        print(_render(problems))
    errs = sum(1 for p in problems if p.level == "error")
    warns = sum(1 for p in problems if p.level == "warning")
    print(f"\n{errs} error(s), {warns} warning(s)")


def cmd_validate(args) -> int:
    config, _path, source = _load(args)
    problems = validate(source, config)
    _print_summary(problems)
    return 1 if has_blocking(problems, args.strict) else 0


def cmd_package(args) -> int:
    config, _path, source = _load(args)
    problems = validate(source, config)
    _print_summary(problems)
    if has_blocking(problems, strict=False):
        print("\nValidation failed; not packaging.")
        return 1
    outputs = package(source, config, Path(args.out))
    print("\nWrote:")
    for o in outputs:
        print(f"  {o}")
    return 0


def cmd_publish(args) -> int:
    config, path, source = _load(args)
    problems = validate(source, config)
    _print_summary(problems)
    if has_blocking(problems, strict=False):
        print("\nValidation failed; not publishing.")
        return 1
    name = source.frontmatter["name"]
    message = args.message or f"skill: update {name}"
    result = publisher.publish(Path("."), path, message, config.git.remote, config.git.branch,
                               assume_yes=args.yes)
    print(result)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="skillpack")
    parser.add_argument("--config")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate")
    pv.add_argument("path", nargs="?")
    pv.add_argument("--strict", action="store_true")
    pv.set_defaults(func=cmd_validate)

    pp = sub.add_parser("package")
    pp.add_argument("path", nargs="?")
    pp.add_argument("--out", default="dist")
    pp.set_defaults(func=cmd_package)

    pu = sub.add_parser("publish")
    pu.add_argument("path", nargs="?")
    pu.add_argument("--message")
    pu.add_argument("--yes", action="store_true")
    pu.set_defaults(func=cmd_publish)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
