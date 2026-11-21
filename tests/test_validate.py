import unicodedata

from helpers import entry, group, write

from dictctl.diagnostics import has_errors
from dictctl.loader import load_dictionary
from dictctl.validate import validate_groups


def run(tmp_path):
    result = load_dictionary(tmp_path)
    assert result.issues == [], [i.format() for i in result.issues]
    issues = validate_groups(result.groups)
    return issues, "\n".join(i.format() for i in issues)


def test_clean_dictionary_has_no_issues(tmp_path):
    write(
        tmp_path,
        "company/pc/peripherals.json",
        group(entry("Corsair", ("こるせあ", "Corsair")), pos="組織"),
    )
    issues, _ = run(tmp_path)
    assert issues == []


def test_nfc_is_required(tmp_path):
    decomposed = unicodedata.normalize("NFD", "ガイド")
    write(tmp_path, "misc/nfd.json", group(entry(decomposed, ("がいど", decomposed))))
    issues, text = run(tmp_path)
    assert has_errors(issues)
    assert ".name: Unicode の NFC 正規化がされていない" in text
    assert ".surface: Unicode の NFC 正規化がされていない" in text


def test_surface_byte_limit(tmp_path):
    write(
        tmp_path,
        "misc/long.json",
        group(entry("emoji", ("えもじ", "🎉" * 76)), entry("ok", ("おーけー", "長" * 100))),
    )
    _, text = run(tmp_path)
    assert "300 バイト以内にする（304 バイト）" in text
    assert "「ok」" not in text


def test_duplicate_pair_within_file(tmp_path):
    write(tmp_path, "misc/dup.json", group(entry("a", ("あ", "亜")), entry("b", ("あ", "亜"))))
    issues, text = run(tmp_path)
    assert has_errors(issues)
    assert "読み「あ」と表記「亜」の組が重複している（entries[0]「a」.conversions[0]）" in text


def test_duplicate_url_and_tags(tmp_path):
    e = entry("a", ("あ", "亜"), tags=["x", "y", "x"])
    e["sources"] = [{"url": "https://example.com/a"}, {"url": "https://example.com/a"}]
    write(tmp_path, "misc/dup.json", group(e))
    _, text = run(tmp_path)
    assert "出典 URL が重複している" in text
    assert "タグが重複している: x" in text


def test_single_source_and_duplicate_name_are_warnings(tmp_path):
    write(
        tmp_path,
        "misc/warn.json",
        group(entry("a", ("あ", "亜"), sources=1), entry("a", ("あい", "愛"))),
    )
    issues, text = run(tmp_path)
    assert not has_errors(issues)
    assert "出典が1件だけ" in text
    assert "同じ name の語がこのファイルに既にある" in text


def test_same_pair_across_files_with_same_pos_is_allowed(tmp_path):
    write(tmp_path, "youtuber/a.json", group(entry("x", ("えっくす", "X")), pos="人名"))
    write(tmp_path, "youtuber/b.json", group(entry("x", ("えっくす", "X", "人名"))))
    issues, _ = run(tmp_path)
    assert issues == []


def test_same_pair_across_files_with_different_pos_is_error(tmp_path):
    write(tmp_path, "youtuber/a.json", group(entry("x", ("えっくす", "X")), pos="人名"))
    write(tmp_path, "youtuber/b.json", group(entry("x", ("えっくす", "X")), pos="固有名詞"))
    issues, text = run(tmp_path)
    assert sum(i.level == "error" for i in issues) == 2
    assert "品詞が違う語が他のファイルにある" in text


def test_reading_sets_differ_across_files_is_warning(tmp_path):
    write(
        tmp_path,
        "company/pc.json",
        group(entry("Corsair", ("こるせあ", "Corsair"), ("こーせあ", "Corsair"))),
    )
    write(tmp_path, "company/gaming.json", group(entry("Corsair", ("こるせあ", "Corsair"))))
    issues, text = run(tmp_path)
    assert not has_errors(issues)
    assert "同じ表記の読みの組み合わせがファイルによって違う" in text
    assert "dictionary/company/gaming.json（こるせあ）" in text
