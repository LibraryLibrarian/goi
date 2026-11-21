from datetime import date

import pytest
from helpers import entry, group, write
from typer.testing import CliRunner

from dictctl.cli import app
from dictctl.release import MAX_NOTES_CHARS, next_version, render_notes, render_tsv

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
    assert "こるせあ\tCorsair\t組織\n" in notes
    assert "削除・変更された語" not in notes


def test_render_notes_lists_removed_before_added():
    old = {("こるせあ", "Corsair", "名詞"), ("とらいあんふ", "Triumph", "固有名詞")}
    new = {("こるせあ", "Corsair", "組織"), ("とらいあんふ", "Triumph", "固有名詞")}
    notes = render_notes(old, new)
    assert "収録数: 2件" in notes
    # 品詞が変わった語は、変わる前の組が「削除・変更された語」に出る。利用者が対応する方を先に載せる
    assert notes.index("## 削除・変更された語（1件）") < notes.index("## 追加された語（1件）")
    assert "こるせあ\tCorsair\t名詞\n" in notes
    assert "こるせあ\tCorsair\t組織\n" in notes
    assert "手動で削除してください" in notes


def test_render_notes_without_changes():
    rows = {("こるせあ", "Corsair", "組織")}
    notes = render_notes(rows, rows)
    assert notes.count("なし") == 2


# --- レビュー指摘（7673641）の回帰テスト ---


def _code_blocks(notes: str) -> list[str]:
    blocks, current, fence = [], None, None
    for line in notes.split("\n"):
        if current is None and line.startswith("```"):
            fence = line[: len(line) - len(line.lstrip("`"))]
            current = []
        elif current is not None and line == fence:
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    return blocks


def test_render_notes_shows_markup_literally_in_code_block():
    surfaces = ["<br>", "&amp;", "Corsair*X*", "[link](https://example.com)", "a```b"]
    notes = render_notes(None, {("あ", s, "名詞") for s in surfaces})
    (block,) = _code_blocks(notes)
    for surface in surfaces:
        assert f"あ\t{surface}\t名詞" in block
    assert "````text" in notes  # 内容のバッククォート3つより長いフェンス


def test_render_notes_stays_within_character_budget():
    long_rows = {("あ" * 100, f"{i:05d}" + "長" * 95, "固有名詞") for i in range(2000)}
    other_rows = {("い" * 100, f"{i:05d}" + "超" * 95, "固有名詞") for i in range(2000)}
    notes = render_notes(long_rows, other_rows)
    assert len(notes) <= MAX_NOTES_CHARS
    assert notes.count("ほか") == 2
    assert "## 削除・変更された語（2000件）" in notes
    assert "## 追加された語（2000件）" in notes


def test_render_tsv_lists_everything():
    old = {("あ", f"A{i:04d}", "名詞") for i in range(1001)}
    tsv = render_tsv(old, set())
    lines = tsv.splitlines()
    assert lines[0] == "change\treading\tsurface\tpos"
    assert len(lines) == 1002
    assert "removed\tあ\tA1000\t名詞" in lines


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


def test_cli_diff_tsv_format(tmp_path):
    write(tmp_path, "company/pc.json", group(entry("Corsair", ("こるせあ", "Corsair")), pos="組織"))
    result = runner.invoke(app, ["diff", "--new", str(tmp_path), "--format", "tsv"])
    assert result.exit_code == 0
    assert result.output == "change\treading\tsurface\tpos\nadded\tこるせあ\tCorsair\t組織\n"
