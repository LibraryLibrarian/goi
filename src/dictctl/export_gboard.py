"""Gboard（Android）の単語リストにインポートできる ZIP を作る。

形式は Gboard 18.6.3 の実機検証（spike/gboard-import/README.md）に基づく:
  - UTF-8（BOM なし）、改行は LF
  - 1行目 `# Gboard Dictionary version:2`
    2行目 `# Gboard Dictionary format:shortcut<TAB>word<TAB>language_tag<TAB>pos_tag`
  - 以降は1語1行で「読み<TAB>表記<TAB>ja-JP<TAB>品詞名」
  - ZIP の中身は dictionary.txt の1ファイルだけ

同じ入力からは常に同じバイト列になるようにする:
  - 行は（読み, 表記, 品詞）の順に並べ、同じ組は1行にまとめる
  - ZIP は無圧縮（STORED）にし、日時・権限などのメタデータを固定する
    （Deflate の出力は zlib の実装や版によって変わり得るため）
    無圧縮の ZIP を Gboard 18.6.3 が取り込み、変換に使えることはエミュレーターで確認済み
    （2026-11-21。deprecated の語が含まれないことも確認）
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dictctl.loader import ALL_PACK_NAME, LoadedGroup
from dictctl.models import Pos
from dictctl.validate import MAX_BYTES

HEADER = (
    "# Gboard Dictionary version:2\n"
    "# Gboard Dictionary format:shortcut\tword\tlanguage_tag\tpos_tag\n"
)
LANGUAGE_TAG = "ja-JP"
INNER_FILENAME = "dictionary.txt"
BOM = chr(0xFEFF)
ALL_PACK = ALL_PACK_NAME
# 実機検証では表記100文字は変換に出て、101文字（漢字で303バイト）は出なかった。
# 文字数とバイト数のどちらの上限かは切り分けていないため、両方を満たすことを求める。
MAX_CHARS = 100
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)  # ZIP 形式で表せる最も古い日時

Row = tuple[str, str, Pos]  # (読み, 表記, 品詞)


@dataclass(frozen=True)
class Pack:
    name: str  # "all" または最上位ディレクトリ名
    rows: list[Row]

    @property
    def filename(self) -> str:
        return f"goi-gboard-{self.name}.zip"


def collect_rows(groups: Iterable[LoadedGroup]) -> list[Row]:
    """status が active の語の（読み, 表記, 品詞）を、重複を除いて並べる。"""
    rows: set[Row] = set()
    for loaded in groups:
        for entry in loaded.group.entries:
            if entry.status != "active":
                continue
            for conv in entry.conversions:
                rows.add((conv.reading, conv.surface, loaded.group.effective_pos(conv)))
    return sorted(rows)


def build_packs(groups: list[LoadedGroup]) -> list[Pack]:
    """全件入りの配布物と、最上位ディレクトリごとの配布物を作る。語のないものは作らない。"""
    by_top: dict[str, list[LoadedGroup]] = {}
    for loaded in groups:
        top = PurePosixPath(loaded.rel_path).parts[0]
        by_top.setdefault(top, []).append(loaded)

    packs = [Pack(ALL_PACK, collect_rows(groups))]
    packs += [Pack(top, collect_rows(members)) for top, members in sorted(by_top.items())]
    return [pack for pack in packs if pack.rows]


def render_text(rows: Iterable[Row]) -> str:
    return HEADER + "".join(f"{r}\t{s}\t{LANGUAGE_TAG}\t{p}\n" for r, s, p in rows)


def render_zip(text: str) -> bytes:
    info = zipfile.ZipInfo(INNER_FILENAME, date_time=ZIP_DATE_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3  # Unix（実行環境によらず固定する）
    info.external_attr = 0o100644 << 16  # 通常ファイル、rw-r--r--
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


# --- 生成物の検査 ---

_ALLOWED_POS = set(Pos.__args__)


class GboardFormatError(ValueError):
    pass


def check_text(text: str) -> int:
    """Gboard が問題なく取り込める形かを確認し、語の行数を返す。

    Gboard は不正な行で取り込みを打ち切り、未知の品詞名の語は黙って変換に使わない
    （実機検証の結果）。そのため生成物の全行を、書き出す前に検査する。
    """
    if text.startswith(BOM):
        raise GboardFormatError("BOM が付いている")
    if "\r" in text:
        raise GboardFormatError("CR が含まれている")
    if not text.startswith(HEADER):
        raise GboardFormatError("ヘッダーが v2 形式でない")
    if not text.endswith("\n"):
        raise GboardFormatError("最終行が改行で終わっていない")

    lines = text[len(HEADER) :].split("\n")[:-1]
    seen: set[str] = set()
    for number, line in enumerate(lines, start=3):
        fields = line.split("\t")
        if len(fields) != 4:
            raise GboardFormatError(f"{number}行目: 列が4つでない")
        reading, surface, language, pos = fields
        if not reading or not surface:
            raise GboardFormatError(f"{number}行目: 読みか表記が空")
        if language != LANGUAGE_TAG:
            raise GboardFormatError(f"{number}行目: 言語タグが {LANGUAGE_TAG} でない")
        if pos not in _ALLOWED_POS:
            raise GboardFormatError(f"{number}行目: 未知の品詞名 {pos}")
        for value in (reading, surface):
            if len(value) > MAX_CHARS:
                raise GboardFormatError(f"{number}行目: {MAX_CHARS} 文字を超える")
            if len(value.encode("utf-8")) > MAX_BYTES:
                raise GboardFormatError(f"{number}行目: {MAX_BYTES} バイトを超える")
        if line in seen:
            raise GboardFormatError(f"{number}行目: 重複した行")
        seen.add(line)
    return len(lines)


def read_zip_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if names != [INNER_FILENAME]:
            raise GboardFormatError(f"ZIP の中身が {INNER_FILENAME} だけでない: {names}")
        return archive.read(INNER_FILENAME).decode("utf-8")


def write_packs(packs: list[Pack], directory: Path) -> list[Path]:
    """配布物を書き出す。前回のビルドで作られ、今回は作られない配布物は消す。"""
    filenames = [pack.filename for pack in packs]
    duplicated = sorted({name for name in filenames if filenames.count(name) > 1})
    if duplicated:
        # 同じ名前の配布物を書くと、後のものが前のものを上書きして語が欠落するため
        raise GboardFormatError("配布物の名前が重複している: " + ", ".join(duplicated))
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("goi-gboard-*.zip"):
        stale.unlink()
    written = []
    for pack in packs:
        text = render_text(pack.rows)
        check_text(text)
        data = render_zip(text)
        if read_zip_text(data) != text:
            raise GboardFormatError(f"{pack.filename}: ZIP から読み戻した内容が一致しない")
        path = directory / pack.filename
        path.write_bytes(data)
        written.append(path)
    return written
