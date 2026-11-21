"""辞書ファイルを正規の形に整形する。

整形の内容:
  - キーの順序を固定し、インデントは2スペース、改行は LF、末尾に改行を1つ置く
  - 語（entries）を読み順に並べる（PR 同士の衝突を減らすため）。
    並べ替えのキーは「最初の読み → name」。語の中の conversions と sources の順は変えない
  - テキストを NFC 正規化し、前後の空白を取り除く（出典の URL は変更しない）
  - 読みは NFKC 正規化（半角カナ → 全角）したうえで、カタカナをひらがなに直す
  - タグは辞書順に並べ、空の項目（tags・defaults、null の pos・note）は省く
  - $schema に、ファイルの位置から schema/group.schema.json への相対パスを入れる

モデルの検証は通らなくても整形できるよう、JSON をそのまま扱う。
定義されていないキーは消さずに末尾へ残し、検出は validate に任せる。
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from dictctl.diagnostics import Issue
from dictctl.loader import DICTIONARY_DIRNAME, discover_files, read_json
from dictctl.models import EDGE_SPACE_CHARS
from dictctl.schema import SCHEMA_FILENAME

GROUP_KEYS = ("$schema", "schema_version", "title", "tags", "defaults", "entries")
ENTRY_KEYS = ("name", "conversions", "sources", "tags")
CONVERSION_KEYS = ("reading", "surface", "pos")
SOURCE_KEYS = ("url", "note")
DEFAULTS_KEYS = ("pos",)


_KATAKANA_TO_HIRAGANA = {code: code - 0x60 for code in range(ord("ァ"), ord("ヶ") + 1)}


def schema_ref(rel_path: str) -> str:
    """dictionary/ からの相対パスに対する、schema/group.schema.json への相対参照。"""
    depth = len(PurePosixPath(rel_path).parts)  # dictionary/ 自体の分を含めて上がる回数
    return "../" * depth + f"schema/{SCHEMA_FILENAME}"


def normalize_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return unicodedata.normalize("NFC", value).strip(EDGE_SPACE_CHARS)


def normalize_reading(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = unicodedata.normalize("NFKC", value).strip(EDGE_SPACE_CHARS)
    return value.translate(_KATAKANA_TO_HIRAGANA)


def _ordered(obj: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """既知のキーを決まった順に並べ、未知のキーはもとの順のまま後ろに付ける。"""
    result = {key: obj[key] for key in keys if key in obj}
    result.update({key: value for key, value in obj.items() if key not in keys})
    return result


def _format_conversion(conv: Any) -> Any:
    if not isinstance(conv, dict):
        return conv
    conv = dict(conv)
    if "reading" in conv:
        conv["reading"] = normalize_reading(conv["reading"])
    if "surface" in conv:
        conv["surface"] = normalize_text(conv["surface"])
    if conv.get("pos") is None:
        conv.pop("pos", None)
    return _ordered(conv, CONVERSION_KEYS)


def _format_source(source: Any) -> Any:
    if not isinstance(source, dict):
        return source
    source = dict(source)
    # URL は変更しない（正規化すると別の URL を指したり、他の出典と重複したりするため）
    if "note" in source:
        source["note"] = normalize_text(source["note"])
    if source.get("note") is None:
        source.pop("note", None)
    return _ordered(source, SOURCE_KEYS)


def _format_entry(entry: Any) -> Any:
    if not isinstance(entry, dict):
        return entry
    entry = dict(entry)
    if "name" in entry:
        entry["name"] = normalize_text(entry["name"])
    if isinstance(entry.get("conversions"), list):
        entry["conversions"] = [_format_conversion(c) for c in entry["conversions"]]
    if isinstance(entry.get("sources"), list):
        entry["sources"] = [_format_source(s) for s in entry["sources"]]
    _format_tags(entry)
    return _ordered(entry, ENTRY_KEYS)


def _format_tags(obj: dict[str, Any]) -> None:
    """空のタグを省き、タグを辞書順に並べる（ファイルと語で共通）。"""
    tags = obj.get("tags")
    if tags == [] or tags is None:
        obj.pop("tags", None)
    elif isinstance(tags, list) and all(isinstance(t, str) for t in tags):
        obj["tags"] = sorted(normalize_text(t) for t in tags)


def _entry_sort_key(entry: Any) -> tuple[str, str]:
    reading = name = ""
    if isinstance(entry, dict):
        convs = entry.get("conversions")
        if isinstance(convs, list) and convs and isinstance(convs[0], dict):
            first = convs[0].get("reading")
            reading = first if isinstance(first, str) else ""
        name = entry["name"] if isinstance(entry.get("name"), str) else ""
    return (reading, name)


def format_group(raw: dict[str, Any], rel_path: str) -> dict[str, Any]:
    group = dict(raw)
    group["$schema"] = schema_ref(rel_path)
    if "title" in group:
        group["title"] = normalize_text(group["title"])
    _format_tags(group)

    defaults = group.get("defaults")
    if isinstance(defaults, dict):
        defaults = dict(defaults)
        if defaults.get("pos", "") is None:
            defaults.pop("pos")
        if defaults:
            group["defaults"] = _ordered(defaults, DEFAULTS_KEYS)
        else:
            group.pop("defaults")
    elif defaults is None:
        group.pop("defaults", None)

    entries = group.get("entries")
    if isinstance(entries, list):
        formatted = [_format_entry(e) for e in entries]
        group["entries"] = sorted(formatted, key=_entry_sort_key)
    return _ordered(group, GROUP_KEYS)


def render(raw: dict[str, Any]) -> str:
    return json.dumps(raw, ensure_ascii=False, indent=2) + "\n"


@dataclass(frozen=True)
class FormatResult:
    checked: int
    changed: list[str]  # 整形が必要だった（または整形した）ファイルの表示用パス
    issues: list[Issue]  # 読み込めず整形できなかったファイル


def format_dictionary(root: Path, *, write: bool) -> FormatResult:
    base = root / DICTIONARY_DIRNAME
    changed: list[str] = []
    checked = 0
    if not base.exists() and not base.is_symlink():
        return FormatResult(0, [], [])
    # シンボリックリンクや読めないディレクトリはエラーとして報告し、書き込みの対象にしない
    paths, issues = discover_files(root)
    for path in paths:
        if path.suffix != ".json":
            continue  # .json 以外のファイルは validate がエラーにする
        rel = path.relative_to(base).as_posix()
        display = f"{DICTIONARY_DIRNAME}/{rel}"
        raw, read_issues = read_json(path, display)
        if raw is None:
            issues.extend(read_issues)
            continue
        checked += 1
        current = path.read_bytes()
        expected = render(format_group(raw, rel)).encode("utf-8")
        if current != expected:
            changed.append(display)
            if write:
                path.write_bytes(expected)
    return FormatResult(checked, changed, issues)
