import os

import pytest
from helpers import entry, group, write

from dictctl.loader import load_dictionary


def messages(result):
    return [i.format() for i in result.issues]


def test_loads_valid_files(tmp_path):
    write(
        tmp_path,
        "game/rpg/sample.json",
        group(entry("試験花子", ("しけんはなこ", "試験花子"))),
    )
    write(tmp_path, "company/it.json", group(entry("Examplia", ("えぐざんぷりあ", "Examplia"))))
    result = load_dictionary(tmp_path)
    assert result.issues == []
    assert [g.rel_path for g in result.groups] == [
        "company/it.json",
        "game/rpg/sample.json",
    ]


def test_missing_dictionary_dir(tmp_path):
    result = load_dictionary(tmp_path)
    assert result.groups == []
    assert "ディレクトリが見つからない" in messages(result)[0]


def test_empty_dictionary_dir_is_ok(tmp_path):
    (tmp_path / "dictionary").mkdir()
    result = load_dictionary(tmp_path)
    assert result.groups == [] and result.issues == []


def test_path_rules(tmp_path):
    good = group(entry("a", ("あ", "亜")))
    write(tmp_path, "top.json", good)  # 浅すぎる
    write(tmp_path, "a/b/c/deep.json", good)  # 深すぎる
    write(tmp_path, "Game/sam_ple.json", good)  # 大文字・アンダースコア
    write(tmp_path, "misc/readme.txt", "x")  # .json 以外
    result = load_dictionary(tmp_path)
    text = "\n".join(messages(result))
    assert result.groups == []
    assert "dictionary/top.json" in text and "dictionary/a/b/c/deep.json" in text
    assert "Game, sam_ple" in text
    assert ".json ファイルだけ" in text


def test_bom_and_invalid_utf8(tmp_path):
    write(tmp_path, "misc/bom.json", b"\xef\xbb\xbf{}")
    write(tmp_path, "misc/latin1.json", b'{"title": "\xff"}')
    text = "\n".join(messages(load_dictionary(tmp_path)))
    assert "BOM" in text
    assert "UTF-8 として読めない" in text


def test_json_syntax_and_duplicate_keys(tmp_path):
    write(tmp_path, "misc/syntax.json", '{"schema_version": 1,\n "title": }\n')
    write(
        tmp_path,
        "misc/dupkey.json",
        '{"schema_version": 1, "title": "a", "title": "b", "entries": []}',
    )
    write(tmp_path, "misc/array.json", "[]")
    text = "\n".join(messages(load_dictionary(tmp_path)))
    assert "2行目: JSON の構文エラー" in text
    assert "キーが重複している: title" in text
    assert "最上位はオブジェクト" in text


def test_model_errors_are_described_with_entry_name(tmp_path):
    data = group(
        entry("ok", ("おーけー", "OK")),
        entry("試験花子", ("シケン", "試験花子"), ("しけん", "試験", "謎の品詞")),
    )
    data["entries"][0]["category"] = "x"
    write(tmp_path, "misc/bad.json", data)
    text = "\n".join(messages(load_dictionary(tmp_path)))
    assert "entries[1]「試験花子」.conversions[0].reading: 読みはひらがなと「ー」だけで書く" in text
    assert "entries[1]「試験花子」.conversions[1].pos: 品詞は" in text
    assert "entries[0]「ok」.category: 定義されていない項目がある" in text


# --- レビュー指摘（bdc4478）の回帰テスト: 1ファイルの異常で全体を止めない ---


def test_huge_integer_and_deep_nesting_do_not_abort(tmp_path):
    write(tmp_path, "misc/bigint.json", '{"schema_version": ' + "1" * 4301 + "}")
    write(tmp_path, "misc/deep.json", "[" * 100000 + "]" * 100000)
    write(tmp_path, "misc/ok.json", group(entry("a", ("あ", "亜"))))
    result = load_dictionary(tmp_path)
    text = "\n".join(messages(result))
    assert "dictionary/misc/bigint.json: JSON を読み込めない" in text
    assert "dictionary/misc/deep.json: JSON を読み込めない" in text
    assert [g.rel_path for g in result.groups] == ["misc/ok.json"]


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0, reason="権限で読み取りを拒否できない環境"
)
def test_unreadable_file_does_not_abort(tmp_path):
    path = write(tmp_path, "misc/locked.json", group(entry("a", ("あ", "亜"))))
    write(tmp_path, "misc/ok.json", group(entry("b", ("い", "伊"))))
    path.chmod(0)
    try:
        result = load_dictionary(tmp_path)
    finally:
        path.chmod(0o644)
    assert "dictionary/misc/locked.json: ファイルを読めない" in "\n".join(messages(result))
    assert [g.rel_path for g in result.groups] == ["misc/ok.json"]
