"""リリースの補助: 版の決め方と、前のリリースとの差分（リリースノート）。

版は vYYYY.MM.DD。同じ日に2回目以降のリリースをするときは、その日の何回目かを
末尾に付ける（vYYYY.MM.DD.2、vYYYY.MM.DD.3、…）。

差分は（読み, 表記, 品詞）の組で比べる。Gboard に取り込まれるのはこの組なので、
内容が変わった語は「削除された組」と「追加された組」として現れる。削除された組は、
以前のリリースを取り込んだ端末に残るため、利用者が手動で削除する対象になる。

リリースノートでは、表記を Markdown や HTML として解釈させず文字どおりに見せるため、
語の一覧をコードブロックの中にタブ区切りで書く。一覧は件数によらず <details> で折りたたみ、
添付ファイルの欄までスクロールしやすくする。本文は GitHub Releases の上限
（125,000文字）を超えないよう、文字数で打ち切る。全件はタブ区切りのファイル
（リリースに添付する goi-gboard-changes.tsv、または dictctl diff --format tsv）で確認できる。
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
# リリースノートの本文の上限。GitHub Releases の上限（125,000文字）より余裕を持たせる
MAX_NOTES_CHARS = 100_000
CHANGES_FILENAME = "goi-gboard-changes.tsv"
# 一覧を折りたたむ。<summary> の後と </details> の前に空行がないと、中のコードブロックが表示されない
DETAILS_OPEN = ["<details>", "<summary>一覧を開く</summary>", ""]
DETAILS_CLOSE = ["", "</details>"]
TABLE_HEADER = "読み\t表記\t品詞"


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


def split_changes(old: set[Row] | None, new: set[Row]) -> tuple[list[Row], list[Row]]:
    """（削除・変更された組, 追加された組）を返す。"""
    previous = old or set()
    return sorted(previous - new), sorted(new - previous)


def render_tsv(old: set[Row] | None, new: set[Row]) -> str:
    """差分の全件をタブ区切りで返す（省略しない）。"""
    removed, added = split_changes(old, new)
    lines = ["change\treading\tsurface\tpos"]
    lines += [f"removed\t{r}\t{s}\t{p}" for r, s, p in removed]
    lines += [f"added\t{r}\t{s}\t{p}" for r, s, p in added]
    return "\n".join(lines) + "\n"


def _fence(rows: list[Row]) -> str:
    """内容に含まれるどのバッククォートの連続よりも長いフェンスを返す。"""
    longest = max(
        (len(run) for r in rows for cell in r for run in re.findall(r"`+", cell)), default=0
    )
    return "`" * max(3, longest + 1)


def _section(title: str, rows: list[Row], intro: str | None, budget: int) -> list[str]:
    lines = [f"## {title}（{len(rows)}件）", ""]
    if not rows:
        return [*lines, "なし"]
    if intro:
        lines += [intro, ""]
    fence = _fence(rows)
    opening = [*DETAILS_OPEN, fence + "text", TABLE_HEADER]
    closing = [fence, *DETAILS_CLOSE]
    # 見出し・折りたたみ・フェンス・省略時の案内（200文字を見込む）を除いた残りに載せる
    remaining = budget - _length(lines) - _length(opening) - _length(closing) - 200
    shown: list[str] = []
    for r, s, p in rows:
        line = f"{r}\t{s}\t{p}"
        if remaining - (len(line) + 1) < 0:
            break
        shown.append(line)
        remaining -= len(line) + 1
    lines += [*opening, *shown, *closing]
    if len(shown) < len(rows):
        lines += [
            "",
            f"ほか{len(rows) - len(shown)}件。全件は、リリースに添付の`{CHANGES_FILENAME}`、"
            "または`dictctl diff --format tsv`で確認できます。",
        ]
    return lines


def render_notes(old: set[Row] | None, new: set[Row], budget: int = MAX_NOTES_CHARS) -> str:
    """リリースノートの本文（Markdown）を作る。old が None なら初回のリリース。"""
    removed, added = split_changes(old, new)
    lines = [f"収録数: {len(new)}件（読みと表記の組）", ""]
    if old is None:
        lines += ["初回のリリースです。", ""]
    else:
        # 利用者が対応する必要がある「削除・変更された語」を先に載せる
        intro = (
            "以前のリリースから削除された語、または内容が変わる前の語です。"
            "以前のリリースを取り込んだ端末では、Gboardの単語リストから手動で削除してください。"
        )
        used = sum(len(line) + 1 for line in lines)
        # 後に続く「追加された語」の見出し・フェンス・案内の分を、先に確保しておく
        reserved = _length(_section("追加された語", added, None, 0)) + 1
        lines += [*_section("削除・変更された語", removed, intro, budget - used - reserved), ""]
    used = sum(len(line) + 1 for line in lines)
    lines += _section("追加された語", added, None, budget - used)
    return "\n".join(lines) + "\n"


def _length(lines: list[str]) -> int:
    return sum(len(line) + 1 for line in lines)
