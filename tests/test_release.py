from datetime import date

import pytest
from helpers import entry, group, write
from typer.testing import CliRunner

import dictctl.release as release
from dictctl.cli import app
from dictctl.release import next_version, render_notes

runner = CliRunner()


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ([], "v2026.12.01"),
        (["v2026.11.30", "v2026.12.02"], "v2026.12.01"),
        (["v2026.12.01"], "v2026.12.01.2"),
        (["v2026.12.01", "v2026.12.01.2"], "v2026.12.01.3"),
        (["v2026.12.01.3", "v2026.12.01"], "v2026.12.01.4"),  # 順不同
        (["v2026.12.01-rc", "2026.12.01", "x"], "v2026.12.01"),  # 形式の違うタグは無視
    ],
)
def test_next_version(tags, expected):
    assert next_version(date(2026, 12, 1), tags) == expected


def test_render_notes_initial_release():
    notes = render_notes(None, {("こるせあ", "Corsair", "組織")})
    assert "初回のリリースです。" in notes
    assert "## 追加された語（1件）" in notes
    assert "| こるせあ | Corsair | 組織 |" in notes
    assert "削除・変更された語" not in notes


def test_render_notes_lists_added_and_removed_rows():
    old = {("こるせあ", "Corsair", "名詞"), ("とらいあんふ", "Triumph", "固有名詞")}
    new = {("こるせあ", "Corsair", "組織"), ("とらいあんふ", "Triumph", "固有名詞")}
    notes = render_notes(old, new)
    assert "収録数: 2件" in notes
    assert "## 追加された語（1件）" in notes
    assert "| こるせあ | Corsair | 組織 |" in notes
    # 品詞が変わった語は、変わる前の組が「削除・変更された語」に出る
    assert "## 削除・変更された語（1件）" in notes
    assert "| こるせあ | Corsair | 名詞 |" in notes
    assert "手動で削除してください" in notes


def test_render_notes_without_changes():
    rows = {("こるせあ", "Corsair", "組織")}
    notes = render_notes(rows, rows)
    assert notes.count("なし") == 2


def test_render_notes_escapes_table_separators():
    notes = render_notes(None, {("あ", "A|B", "名詞")})
    assert "| あ | A\\|B | 名詞 |" in notes


def test_render_notes_truncates_long_tables(monkeypatch):
    monkeypatch.setattr(release, "MAX_ROWS_PER_SECTION", 2)
    rows = {("あ", "A", "名詞"), ("い", "I", "名詞"), ("う", "U", "名詞")}
    notes = render_notes(None, rows)
    assert "| う | U | 名詞 |" not in notes
    assert "ほか1件" in notes


def test_cli_diff_between_two_roots(tmp_path):
    old_root, new_root = tmp_path / "old", tmp_path / "new"
    write(old_root, "company/pc.json", group(entry("Corsair", ("こるせあ", "Corsair")), pos="名詞"))
    write(
        new_root,
        "company/pc.json",
        group(
            entry("Corsair", ("こるせあ", "Corsair")),
            entry("Triumph", ("とらいあんふ", "Triumph")),
            pos="組織",
        ),
    )
    result = runner.invoke(app, ["diff", "--old", str(old_root), "--new", str(new_root)])
    assert result.exit_code == 0, result.output
    assert "## 追加された語（2件）" in result.output
    assert "## 削除・変更された語（1件）" in result.output


def test_cli_diff_fails_on_invalid_dictionary(tmp_path):
    write(tmp_path, "company/pc.json", group(entry("Corsair", ("コルセア", "Corsair"))))
    result = runner.invoke(app, ["diff", "--new", str(tmp_path)])
    assert result.exit_code == 1


def test_cli_release_version_reads_tags_from_stdin():
    result = runner.invoke(app, ["release-version", "--date", "2026-12-01"], input="v2026.12.01\n")
    assert result.exit_code == 0
    assert result.output == "v2026.12.01.2\n"


def test_cli_release_version_rejects_bad_date():
    assert runner.invoke(app, ["release-version", "--date", "2026/12/01"], input="").exit_code == 2
