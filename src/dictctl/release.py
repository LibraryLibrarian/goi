"""リリースの補助: 版の決め方と、前のリリースとの差分（リリースノート）。

版は vYYYY.MM.DD。同じ日に2回目以降のリリースをするときは、その日の何回目かを
末尾に付ける（vYYYY.MM.DD.2、vYYYY.MM.DD.3、…）。

差分は（読み, 表記, 品詞）の組で比べる。Gboard に取り込まれるのはこの組なので、
内容が変わった語は「削除された組」と「追加された組」として現れる。削除された組は、
以前のリリースを取り込んだ端末に残るため、利用者が手動で削除する対象になる。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from dictctl.diagnostics import has_errors
from dictctl.export_gboard import Row, collect_rows
from dictctl.loader import load_dictionary

TAG_PATTERN = re.compile(r"^v(\d{4})\.(\d{2})\.(\d{2})(?:\.(\d+))?$")
# リリースノートの表に載せる行数の上限（GitHub Releases の本文は125,000文字まで）
MAX_ROWS_PER_SECTION = 1000


def next_version(day: date, existing_tags: Iterable[str]) -> str:
    """その日の次の版を返す。1回目は vYYYY.MM.DD、2回目以降は .2、.3、…を付ける。"""
    base = f"v{day:%Y.%m.%d}"
    count = 0
    for tag in existing_tags:
        match = TAG_PATTERN.match(tag.strip())
        if not match or tuple(int(x) for x in match.groups()[:3]) != (
            day.year,
            day.month,
            day.day,
        ):
            continue
        count = max(count, int(match.group(4)) if match.group(4) else 1)
    return base if count == 0 else f"{base}.{count + 1}"


class DictionaryLoadError(Exception):
    pass


def dictionary_rows(root: Path) -> set[Row]:
    """root（リポジトリのルート）の辞書の（読み, 表記, 品詞）の組をすべて返す。"""
    result = load_dictionary(root)
    if has_errors(result.issues):
        raise DictionaryLoadError(f"{root} の辞書にエラーがある（dictctl validate で確認できる）")
    return set(collect_rows(result.groups))


def _escape(cell: str) -> str:
    return cell.replace("\\", "\\\\").replace("|", "\\|")


def _table(rows: list[Row]) -> list[str]:
    lines = ["| 読み | 表記 | 品詞 |", "|---|---|---|"]
    shown = rows[:MAX_ROWS_PER_SECTION]
    lines += [f"| {_escape(r)} | {_escape(s)} | {_escape(p)} |" for r, s, p in shown]
    if len(rows) > len(shown):
        lines.append("")
        lines.append(f"ほか{len(rows) - len(shown)}件（全件は`dictctl diff`で確認できます）")
    return lines


def render_notes(old: set[Row] | None, new: set[Row]) -> str:
    """リリースノートの本文（Markdown）を作る。old が None なら初回のリリース。"""
    added = sorted(new - (old or set()))
    removed = sorted((old or set()) - new)
    lines = [f"収録数: {len(new)}件（読みと表記の組）", ""]
    if old is None:
        lines += ["初回のリリースです。", ""]
    lines += [f"## 追加された語（{len(added)}件）", ""]
    lines += _table(added) if added else ["なし"]
    if old is not None:
        lines += ["", f"## 削除・変更された語（{len(removed)}件）", ""]
        if removed:
            lines += [
                "以前のリリースから削除された語、または内容が変わる前の語です。"
                "以前のリリースを取り込んだ端末では、Gboardの単語リストから手動で削除してください。",
                "",
                *_table(removed),
            ]
        else:
            lines.append("なし")
    return "\n".join(lines) + "\n"
