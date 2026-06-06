from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    level: str  # "error" | "warning"
    code: str
    message: str
    hint: str = ""
