from __future__ import annotations

from typing import TypedDict

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class Problem(TypedDict):
    code: str
    path: str
    message: str
    fix: str


class Report:
    def __init__(self) -> None:
        self.errors: list[Problem] = []
        self.warnings: list[Problem] = []

    def err(self, code: str, path: str, message: str, fix: str = "") -> None:
        self.errors.append({"code": code, "path": path, "message": message, "fix": fix})

    def warn(self, code: str, path: str, message: str, fix: str = "") -> None:
        self.warnings.append({"code": code, "path": path, "message": message, "fix": fix})

    @property
    def ok(self) -> bool:
        return not self.errors
