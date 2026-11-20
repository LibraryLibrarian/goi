"""ソース・テスト・スキーマに不可視文字そのものが含まれていないことを確認する。

不可視文字は見た目で気付けず、意図しない差分や判定の違いの原因になる。
必要な場合は、文字列中でエスケープ（バックスラッシュ + uXXXX）として書く。
"""

import unicodedata
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS = sorted(
    p
    for directory in ("src", "tests", "schema")
    for p in (REPO_ROOT / directory).rglob("*")
    if p.is_file() and p.suffix in {".py", ".json"}
)
ALLOWED = {"\n", " "}
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Zs", "Zl", "Zp"}


@pytest.mark.parametrize("path", TARGETS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_invisible_characters(path):
    text = path.read_text(encoding="utf-8")
    found = sorted(
        {
            f"U+{ord(c):04X}"
            for c in text
            if c not in ALLOWED and unicodedata.category(c) in INVISIBLE_CATEGORIES
        }
    )
    assert not found, f"{path.relative_to(REPO_ROOT)} に不可視文字がある: {found}"
