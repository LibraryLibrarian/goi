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
        "defaults": {"pos": "人名"},
        "entries": [
            {
                "name": "試験花子",
                "conversions": [{"reading": "しけんはなこ", "surface": "試験花子"}],
                "sources": [{"url": "https://example.com/hanako", "note": "公式プロフィール"}],
                "tags": ["sample-tag"],
            }
        ],
    }
    data.update(overrides)
    return data


def with_conversion(**conversion) -> dict:
    data = make_group()
    data["entries"][0]["conversions"] = [
        {"reading": "しけんはなこ", "surface": "試験花子", **conversion}
    ]
    return data


def test_valid_group_parses():
    group = GroupFile.model_validate(make_group())
    assert group.entries[0].status == "active"
    assert group.entries[0].conversions[0].reading == "しけんはなこ"


def test_schema_key_is_accepted():
    group = GroupFile.model_validate(make_group(**{"$schema": "../schema/group.schema.json"}))
    assert group.schema_ref == "../schema/group.schema.json"


def test_effective_pos_order():
    group = GroupFile.model_validate(make_group())
    assert group.effective_pos(group.entries[0].conversions[0]) == "人名"

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
    ["シケン", "shiken", "しけん はなこ", "しけん2", "", "あ" * 101],
)
def test_reading_rejects_other_characters(reading):
    with pytest.raises(ValidationError):
        GroupFile.model_validate(with_conversion(reading=reading))


@pytest.mark.parametrize(
    "surface",
    [" 試験花子", "試験花子 ", "試験\tはなこ", "試験\nはなこ", "", "長" * 101],
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


@pytest.mark.parametrize("tag", ["Sample", "sam_ple", "-sample", "サンプル"])
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
    assert committed == render_schema(), "schema が古い。dictctl.schema で再生成する"
