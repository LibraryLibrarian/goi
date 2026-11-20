"""辞書マスター（dictionary/ 配下の JSON）のデータモデル。

1ファイルが1グループ（例: dictionary/game/rpg/sample.json）で、
複数の語（entries）を持つ。分類はディレクトリ階層で表し、ファイル内には持たない。

ここでは構造と単一フィールドで判定できる制約だけを扱う。
NFC 正規化・バイト長・ファイルをまたぐ重複などは validate 側で検査する。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

# Gboard（Mozc 系）の品詞名のうち、goi で許可するもの。
# Gboard は未知の品詞名を黙って変換に使わないため、ここに無い値は受け付けない。
Pos = Literal["名詞", "固有名詞", "人名", "姓", "名", "組織", "地名", "品詞なし"]
DEFAULT_POS: Pos = "品詞なし"

# 読み: ひらがな（ゔ・ゕ・ゖ を含む）と長音符のみ。
READING_PATTERN = r"^[ぁ-ゖー]+$"
# 表記: 制御文字を含まず、前後が空白でない。
SURFACE_PATTERN = r"^[^\s\x00-\x1f\x7f](?:[^\x00-\x1f\x7f]*[^\s\x00-\x1f\x7f])?$"
# 一般的なテキスト項目（名前・タイトル・メモ）: 表記と同じ規則。
TEXT_PATTERN = SURFACE_PATTERN
TAG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
URL_PATTERN = r"^https://[^\s]+$"


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

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    def effective_pos(self, conversion: Conversion) -> Pos:
        """語ごとの指定 → ファイルの既定値 → 「品詞なし」の順に品詞を決める。"""
        return conversion.pos or self.defaults.pos or DEFAULT_POS
