import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dictctl.models import GroupFile
from dictctl.schema import SCHEMA_FILENAME, render_schema

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_group(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "title": "テストグループ",
        "defaults": {"pos": "組織"},
        "entries": [
            {
                "name": "Corsair",
                "conversions": [{"reading": "こるせあ", "surface": "Corsair"}],
                "sources": [{"url": "https://example.com/corsair", "note": "公式サイト"}],
                "tags": ["pc-parts"],
            }
        ],
    }
    data.update(overrides)
    return data


def with_conversion(**conversion) -> dict:
    data = make_group()
    data["entries"][0]["conversions"] = [
        {"reading": "こるせあ", "surface": "Corsair", **conversion}
    ]
    return data


def test_valid_group_parses():
    group = GroupFile.model_validate(make_group())
    assert group.entries[0].status == "active"
    assert group.entries[0].conversions[0].reading == "こるせあ"


def test_schema_key_is_accepted():
    group = GroupFile.model_validate(make_group(**{"$schema": "../schema/group.schema.json"}))
    assert group.schema_ref == "../schema/group.schema.json"


def test_effective_pos_order():
    group = GroupFile.model_validate(make_group())
    assert group.effective_pos(group.entries[0].conversions[0]) == "組織"

    explicit = GroupFile.model_validate(with_conversion(pos="固有名詞"))
    assert explicit.effective_pos(explicit.entries[0].conversions[0]) == "固有名詞"

    no_default = GroupFile.model_validate(make_group(defaults={}))
    assert no_default.effective_pos(no_default.entries[0].conversions[0]) == "品詞なし"


@pytest.mark.parametrize(
    "reading",
    ["ゔぁーちゃる", "ゕゖ", "あー"],
)
def test_reading_accepts_hiragana_and_choonpu(reading):
    GroupFile.model_validate(with_conversion(reading=reading))


@pytest.mark.parametrize(
    "reading",
    ["コルセア", "corsair", "こる せあ", "こるせあ2", "", "あ" * 101],
)
def test_reading_rejects_other_characters(reading):
    with pytest.raises(ValidationError):
        GroupFile.model_validate(with_conversion(reading=reading))


@pytest.mark.parametrize(
    "surface",
    [" Corsair", "Corsair ", "Cor\tsair", "Cor\nsair", "", "長" * 101],
)
def test_surface_rejects_whitespace_edges_and_control_chars(surface):
    with pytest.raises(ValidationError):
        GroupFile.model_validate(with_conversion(surface=surface))


def test_surface_allows_inner_space_and_symbols():
    GroupFile.model_validate(with_conversion(surface="Rock'n'Roll 🎉 ＡＢＣ"))


def test_unknown_pos_is_rejected():
    with pytest.raises(ValidationError):
        GroupFile.model_validate(with_conversion(pos="存在しない品詞"))


def test_unknown_keys_are_rejected():
    data = make_group()
    data["entries"][0]["category"] = "vtuber"
    with pytest.raises(ValidationError):
        GroupFile.model_validate(data)


def test_entry_requires_sources():
    data = make_group()
    data["entries"][0]["sources"] = []
    with pytest.raises(ValidationError):
        GroupFile.model_validate(data)


@pytest.mark.parametrize("url", ["http://example.com/", "example.com", "https://exa mple.com"])
def test_source_requires_https_url(url):
    data = make_group()
    data["entries"][0]["sources"] = [{"url": url}]
    with pytest.raises(ValidationError):
        GroupFile.model_validate(data)


@pytest.mark.parametrize("tag", ["PC-Parts", "pc_parts", "-pc", "パーツ"])
def test_tag_format(tag):
    data = make_group()
    data["entries"][0]["tags"] = [tag]
    with pytest.raises(ValidationError):
        GroupFile.model_validate(data)


def test_unsupported_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        GroupFile.model_validate(make_group(schema_version=2))


def test_committed_schema_is_up_to_date():
    committed = (REPO_ROOT / "schema" / SCHEMA_FILENAME).read_text(encoding="utf-8")
    assert committed == render_schema(), "schema が古い。dictctl schema で再生成する"


# --- レビュー指摘（03f2295）の回帰テスト ---


@pytest.mark.parametrize(
    "surface",
    ["\ufeff語", "語\ufeff", "\u0085語", "語\u200b語", "語\u2028語", "\u3000語", "語\u00a0"],
)
def test_surface_rejects_invisible_and_edge_space_chars(surface):
    with pytest.raises(ValidationError):
        GroupFile.model_validate(with_conversion(surface=surface))


@pytest.mark.parametrize("surface", ["語\u3000語", "👨\u200d👩\u200d👧", "A B"])
def test_surface_allows_inner_space_and_zwj(surface):
    GroupFile.model_validate(with_conversion(surface=surface))


@pytest.mark.parametrize(
    "url",
    [
        "https:///",
        "https://#",
        "https://example.com\x00",
        "https://localhost/",
        "https://example.com/a b",
        "https://example.com/\u200b",
    ],
)
def test_source_url_requires_host_and_no_forbidden_chars(url):
    data = make_group()
    data["entries"][0]["sources"] = [{"url": url}]
    with pytest.raises(ValidationError):
        GroupFile.model_validate(data)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://example.jp/wiki/コルセア",
        "https://example.org/a/%E3%82%B3",
        "https://example.com:8443/path?q=1#frag",
    ],
)
def test_source_url_accepts_common_forms(url):
    data = make_group()
    data["entries"][0]["sources"] = [{"url": url}]
    GroupFile.model_validate(data)


def test_schema_version_rejects_boolean():
    doc = make_group(schema_version=True)
    with pytest.raises(ValidationError):
        GroupFile.model_validate(doc)
    with pytest.raises(ValidationError):
        GroupFile.model_validate_json(json.dumps(doc))


def _patterns(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pattern":
                yield value
            else:
                yield from _patterns(value)
    elif isinstance(node, list):
        for item in node:
            yield from _patterns(item)


def test_schema_patterns_avoid_engine_dependent_shorthands():
    # \s \d \w \b は Rust・Python・ECMA で対象文字が異なるため使わない。
    patterns = list(_patterns(json.loads(render_schema())))
    assert patterns
    for pattern in patterns:
        for shorthand in (r"\s", r"\S", r"\d", r"\D", r"\w", r"\W", r"\b"):
            assert shorthand not in pattern, (pattern, shorthand)


# --- 全体レビューの指摘の回帰テスト: 方向制御文字 ---

BIDI_CONTROLS = [0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)]


@pytest.mark.parametrize("codepoint", BIDI_CONTROLS, ids=lambda c: f"U+{c:04X}")
def test_bidi_controls_are_rejected(codepoint):
    with pytest.raises(ValidationError):
        GroupFile.model_validate(with_conversion(surface="ABC" + chr(codepoint) + "DEF"))
