"""辞書マスター（dictionary/ 配下の JSON）のデータモデル。

1ファイルが1グループ（例: dictionary/company/pc/peripherals.json）で、
複数の語（entries）を持つ。分類はディレクトリ階層で表し、ファイル内には持たない。

ここでは構造と単一フィールドで判定できる制約だけを扱う。
NFC 正規化・バイト長・ファイルをまたぐ重複などは validate 側で検査する。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1

# Gboard（Mozc 系）の品詞名のうち、goi で許可するもの。
# Gboard は未知の品詞名を黙って変換に使わないため、ここに無い値は受け付けない。
Pos = Literal["名詞", "固有名詞", "人名", "姓", "名", "組織", "地名", "品詞なし"]
DEFAULT_POS: Pos = "品詞なし"

# 正規表現は pydantic-core（Rust）と JSON Schema（ECMA）の両方で同じ意味になるよう、
# \s・\d・\w などエンジンで意味が変わる略記を使わず、文字を明示的に列挙する。

# どこにも含めてはいけない文字: C0/C1 制御文字、ゼロ幅スペース、方向制御（LRM・RLM・ALM、
# 埋め込み・上書き・分離の各制御文字）、行・段落区切り、単語結合子、BOM。
# 絵文字の結合に使う ZWJ（U+200D）は許可する。
FORBIDDEN_RANGES = (
    (0x0000, 0x001F),
    (0x007F, 0x009F),
    (0x061C, 0x061C),
    (0x200B, 0x200B),
    (0x200E, 0x200F),
    (0x2028, 0x2029),
    (0x202A, 0x202E),
    (0x2060, 0x2060),
    (0x2066, 0x2069),
    (0xFEFF, 0xFEFF),
)
# 先頭・末尾に置いてはいけない空白（文字列の内側では許可する）。
EDGE_SPACE_RANGES = (
    (0x0020, 0x0020),
    (0x00A0, 0x00A0),
    (0x1680, 0x1680),
    (0x2000, 0x200A),
    (0x202F, 0x202F),
    (0x205F, 0x205F),
    (0x3000, 0x3000),
)
EDGE_SPACE_CHARS = "".join(chr(c) for lo, hi in EDGE_SPACE_RANGES for c in range(lo, hi + 1))

_BACKSLASH = chr(0x5C)


def _char_class(ranges: tuple[tuple[int, int], ...]) -> str:
    """文字クラスの中身を「バックスラッシュ + uXXXX」のエスケープで作る。

    ソースや生成したスキーマに不可視文字そのものを書かないため、文字ではなく
    エスケープで表す（pydantic-core と ECMA のどちらも同じ意味に解釈する）。
    """
    parts = []
    for lo, hi in ranges:
        part = f"{_BACKSLASH}u{lo:04x}"
        if hi != lo:
            part += f"-{_BACKSLASH}u{hi:04x}"
        parts.append(part)
    return "".join(parts)


_FORBIDDEN = _char_class(FORBIDDEN_RANGES)
_EDGE_SPACE = _char_class(EDGE_SPACE_RANGES)

# 読み: ひらがな（ゔ・ゕ・ゖ を含む）と長音符のみ。
READING_PATTERN = r"^[ぁ-ゖー]+$"
# 表記: 禁止文字を含まず、前後が空白でない。
SURFACE_PATTERN = (
    rf"^[^{_FORBIDDEN}{_EDGE_SPACE}](?:[^{_FORBIDDEN}]*[^{_FORBIDDEN}{_EDGE_SPACE}])?$"
)
# 一般的なテキスト項目（名前・タイトル・メモ）: 表記と同じ規則。
TEXT_PATTERN = SURFACE_PATTERN
TAG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
# https のみ。ホスト名は ASCII でドットを1つ以上含む（国際化ドメインは punycode で書く）。
# パス以降は非 ASCII を許可する（日本語版 Wikipedia の URL などをそのまま書けるように）が、
# 空白と禁止文字は許可しない。
URL_PATTERN = (
    r"^https://[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
    r"(?::[0-9]{1,5})?"
    rf"(?:[/?#][^{_FORBIDDEN}{_EDGE_SPACE}]*)?$"
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Conversion(_Model):
    """読みと変換結果（表記）の組。"""

    reading: str = Field(
        pattern=READING_PATTERN,
        max_length=100,
        description="読み。ひらがなと長音符（ー）のみ。",
    )
    surface: str = Field(
        pattern=SURFACE_PATTERN,
        max_length=100,
        description="変換結果（表記）。UTF-8 で300バイト以内。",
    )
    pos: Pos | None = Field(
        default=None,
        description="品詞。省略時はファイルの defaults.pos、それも無ければ「品詞なし」。",
    )


class Source(_Model):
    """語の実在や読みを確認できる出典。"""

    url: str = Field(pattern=URL_PATTERN, max_length=2000, description="出典の URL（https）。")
    note: str | None = Field(
        default=None,
        pattern=TEXT_PATTERN,
        max_length=200,
        description="補足（例: 読みの確認箇所）。",
    )


class Entry(_Model):
    """1つの語（エンティティ）。複数の読み・表記を持てる。"""

    name: str = Field(pattern=TEXT_PATTERN, max_length=100, description="代表名称。")
    conversions: list[Conversion] = Field(min_length=1)
    sources: list[Source] = Field(min_length=1, description="出典。最低1件。")
    tags: list[Annotated[str, Field(pattern=TAG_PATTERN, max_length=50)]] = Field(
        default_factory=list,
        description="分類・検索用のタグ（英小文字・数字・ハイフン）。",
    )
    status: Literal["active", "deprecated"] = Field(
        default="active",
        description="deprecated の語はビルドに含めない。",
    )


class Defaults(_Model):
    """ファイル内の語に共通する既定値。"""

    pos: Pos | None = None


class GroupFile(_Model):
    """dictionary/ 配下の1ファイル。"""

    schema_ref: str | None = Field(default=None, alias="$schema")
    schema_version: Literal[1]
    title: str = Field(pattern=TEXT_PATTERN, max_length=100, description="グループの表示名。")
    defaults: Defaults = Field(default_factory=Defaults)
    entries: list[Entry] = Field(min_length=1)

    # $schema だけを受け付ける（内部名の schema_ref は JSON のキーとして使えない）
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _reject_bool(cls, value: object) -> object:
        # Python では True == 1 のため、Literal[1] だけでは JSON の true が通ってしまう。
        if isinstance(value, bool):
            raise ValueError("schema_version には整数を指定する")
        return value

    def effective_pos(self, conversion: Conversion) -> Pos:
        """語ごとの指定 → ファイルの既定値 → 「品詞なし」の順に品詞を決める。"""
        return conversion.pos or self.defaults.pos or DEFAULT_POS
