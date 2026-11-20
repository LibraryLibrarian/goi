"""dictionary/ 配下の辞書ファイルを探索・読み込む。

ここで検査するのは「ファイル単位で完結すること」まで:
  - ファイルの置き場所と名前（ディレクトリ階層が分類になる）
  - 文字コード（UTF-8、BOM なし）と JSON の構文（キーの重複を含む）
  - モデル（schema）への適合
ファイルをまたぐ検査は validate モジュールで行う。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from dictctl.diagnostics import Issue, error
from dictctl.models import GroupFile

DICTIONARY_DIRNAME = "dictionary"
SEGMENT_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# dictionary/ からの相対パスの段数（ファイル名を含む）。例: company/pc/peripherals.json は3段。
MIN_DEPTH = 2
MAX_DEPTH = 3


@dataclass(frozen=True)
class LoadedGroup:
    rel_path: str  # dictionary/ からの相対パス（POSIX 形式）
    group: GroupFile
    raw: dict[str, Any]

    @property
    def display_path(self) -> str:
        return f"{DICTIONARY_DIRNAME}/{self.rel_path}"


@dataclass(frozen=True)
class LoadResult:
    groups: list[LoadedGroup]
    issues: list[Issue]
    file_count: int = 0  # dictionary/ 配下で見つかったファイルの数（読み込めなかったものを含む）


def load_dictionary(root: Path) -> LoadResult:
    """リポジトリのルートを受け取り、dictionary/ 配下をすべて読み込む。"""
    base = root / DICTIONARY_DIRNAME
    if not base.is_dir():
        return LoadResult([], [error(DICTIONARY_DIRNAME, "", "ディレクトリが見つからない")])

    groups: list[LoadedGroup] = []
    issues: list[Issue] = []
    paths = sorted(p for p in base.rglob("*") if p.is_file())
    for path in paths:
        rel = PurePosixPath(path.relative_to(base).as_posix())
        display = f"{DICTIONARY_DIRNAME}/{rel}"
        path_issues = check_path(rel, display)
        issues.extend(path_issues)
        if path_issues:
            continue
        loaded, file_issues = load_file(path, str(rel), display)
        issues.extend(file_issues)
        if loaded is not None:
            groups.append(loaded)
    return LoadResult(groups, issues, file_count=len(paths))


def check_path(rel: PurePosixPath, display: str) -> list[Issue]:
    if rel.suffix != ".json":
        return [error(display, "", "dictionary/ には .json ファイルだけを置ける")]
    segments = [*rel.parent.parts, rel.stem]
    issues: list[Issue] = []
    if not MIN_DEPTH <= len(segments) <= MAX_DEPTH:
        issues.append(
            error(
                display,
                "",
                f"階層は dictionary/ から {MIN_DEPTH}〜{MAX_DEPTH} 段にする"
                "（例: dictionary/company/pc/peripherals.json）",
            )
        )
    bad = [s for s in segments if not SEGMENT_PATTERN.fullmatch(s)]
    if bad:
        issues.append(
            error(
                display,
                "",
                "ディレクトリ名・ファイル名は英小文字・数字・ハイフンにする: " + ", ".join(bad),
            )
        )
    return issues


def load_file(path: Path, rel_path: str, display: str) -> tuple[LoadedGroup | None, list[Issue]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, [error(display, "", f"ファイルを読めない: {exc.strerror or exc}")]
    if data.startswith(b"\xef\xbb\xbf"):
        return None, [error(display, "", "BOM 付きの UTF-8 は使えない")]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [error(display, "", f"UTF-8 として読めない（{exc.start} バイト目）")]
    try:
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateKeyError as exc:
        return None, [error(display, "", f"JSON のキーが重複している: {exc.key}")]
    except json.JSONDecodeError as exc:
        return None, [error(display, f"{exc.lineno}行目", f"JSON の構文エラー: {exc.msg}")]
    except (ValueError, RecursionError) as exc:
        # 桁数の多すぎる整数（Python の整数変換の上限）や、深すぎる入れ子など。
        # 1ファイルの問題で辞書全体の検査を止めないよう、ファイル単位のエラーにする。
        return None, [error(display, "", f"JSON を読み込めない: {type(exc).__name__}")]
    if not isinstance(raw, dict):
        return None, [error(display, "", "JSON の最上位はオブジェクトにする")]
    try:
        group = GroupFile.model_validate(raw)
    except ValidationError as exc:
        return None, [error(display, loc, msg) for loc, msg in describe_validation_error(exc, raw)]
    except RecursionError:
        return None, [error(display, "", "JSON の入れ子が深すぎる")]
    return LoadedGroup(rel_path=rel_path, group=group, raw=raw), []


class _DuplicateKeyError(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


# --- Pydantic のエラーを日本語の説明に変換する ---

_PATTERN_MESSAGES = {
    "reading": "読みはひらがなと「ー」だけで書く",
    "surface": "表記に使えない文字がある（制御文字・ゼロ幅文字など）か、前後に空白がある",
    "name": "使えない文字がある（制御文字・ゼロ幅文字など）か、前後に空白がある",
    "title": "使えない文字がある（制御文字・ゼロ幅文字など）か、前後に空白がある",
    "note": "使えない文字がある（制御文字・ゼロ幅文字など）か、前後に空白がある",
    "url": "URL は https:// で始まり、ホスト名を含め、空白や制御文字を含まない形にする",
}


def describe_validation_error(exc: ValidationError, raw: dict[str, Any]) -> list[tuple[str, str]]:
    described: list[tuple[str, str]] = []
    for err in exc.errors():
        loc = tuple(err["loc"])
        described.append((format_location(loc, raw), _message(err, loc)))
    return described


def _message(err: dict[str, Any], loc: tuple[Any, ...]) -> str:
    kind = err["type"]
    field = next((p for p in reversed(loc) if isinstance(p, str)), "")
    if kind == "string_pattern_mismatch":
        if field == "tags":
            return "タグは英小文字・数字・ハイフンで書く"
        return _PATTERN_MESSAGES.get(field, err["msg"])
    if kind == "missing":
        return "必須の項目がない"
    if kind == "extra_forbidden":
        return "定義されていない項目がある"
    if kind == "literal_error" and field == "pos":
        return "品詞は 名詞・固有名詞・人名・姓・名・組織・地名・品詞なし のいずれかにする"
    if kind == "too_short":
        return "1件以上必要"
    if kind == "string_too_long":
        return f"長すぎる（{err.get('ctx', {}).get('max_length')}文字まで）"
    return err["msg"]


def format_location(loc: tuple[Any, ...], raw: dict[str, Any]) -> str:
    """('entries', 2, 'conversions', 0, 'reading') → entries[2]「名前」.conversions[0].reading"""
    parts: list[str] = []
    node: Any = raw
    for part in loc:
        if isinstance(part, int):
            label = f"[{part}]"
            child = node[part] if isinstance(node, list) and part < len(node) else None
            if parts and parts[-1] == "entries" and isinstance(child, dict):
                name = child.get("name")
                if isinstance(name, str):
                    label += f"「{name}」"
            parts[-1] += label
            node = child
        else:
            parts.append(str(part))
            node = node.get(part) if isinstance(node, dict) else None
    return ".".join(parts)
