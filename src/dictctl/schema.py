"""Pydantic モデルから JSON Schema を生成する。

生成した schema/group.schema.json はコミットしておき、エディターの補完・検証に使う。
CI では再生成した結果とコミット済みのファイルに差分がないことを確認する。
"""

from __future__ import annotations

import json
from pathlib import Path

from dictctl.models import GroupFile

SCHEMA_FILENAME = "group.schema.json"


def build_schema() -> dict:
    schema = GroupFile.model_json_schema(by_alias=True, mode="validation")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **schema,
    }


def render_schema() -> str:
    return json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n"


def write_schema(directory: Path) -> Path:
    path = directory / SCHEMA_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_schema(), encoding="utf-8", newline="\n")
    return path


if __name__ == "__main__":
    print(write_schema(Path("schema")))
