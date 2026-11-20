"""検証結果（エラー・警告）の表現。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["error", "warning"]


@dataclass(frozen=True, order=True)
class Issue:
    path: str
    location: str
    level: Level
    message: str

    def format(self) -> str:
        where = f"{self.path}: {self.location}" if self.location else self.path
        label = "エラー" if self.level == "error" else "警告"
        return f"{label}: {where}: {self.message}"


def error(path: str, location: str, message: str) -> Issue:
    return Issue(path=path, location=location, level="error", message=message)


def warning(path: str, location: str, message: str) -> Issue:
    return Issue(path=path, location=location, level="warning", message=message)


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == "error" for issue in issues)
