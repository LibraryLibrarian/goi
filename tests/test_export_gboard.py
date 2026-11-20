import io
import zipfile

import pytest
from helpers import entry, group, write
from typer.testing import CliRunner

from dictctl.cli import app
from dictctl.export_gboard import (
    BOM,
    HEADER,
    GboardFormatError,
    build_packs,
    check_text,
    read_zip_text,
    render_text,
    render_zip,
    write_packs,
)
from dictctl.loader import load_dictionary

runner = CliRunner()


def load(tmp_path):
    result = load_dictionary(tmp_path)
    assert result.issues == []
    return result.groups


def make_dictionary(tmp_path):
    write(
        tmp_path,
        "company/pc/peripherals.json",
        group(
            entry("Corsair", ("こるせあ", "Corsair"), ("こーせあ", "Corsair")),
            entry("Old", ("おーるど", "Old"), status="deprecated"),
            pos="組織",
        ),
    )
    write(tmp_path, "company/misc.json", group(entry("Corsair", ("こるせあ", "Corsair", "組織"))))
    write(tmp_path, "vehicle/motorcycle.json", group(entry("Triumph", ("とらいあんふ", "Triumph"))))


def test_packs_rows_are_sorted_deduplicated_and_skip_deprecated(tmp_path):
    make_dictionary(tmp_path)
    packs = {p.name: p for p in build_packs(load(tmp_path))}
    assert list(packs) == ["all", "company", "vehicle"]
    # コードポイント順（「ー」U+30FC はひらがなより後）。2ファイルにある語は1行にまとまる
    assert packs["company"].rows == [
        ("こるせあ", "Corsair", "組織"),
        ("こーせあ", "Corsair", "組織"),
    ]
    assert packs["vehicle"].rows == [("とらいあんふ", "Triumph", "品詞なし")]
    assert len(packs["all"].rows) == 3
    assert packs["all"].filename == "goi-gboard-all.zip"


def test_pack_without_active_entries_is_not_built(tmp_path):
    write(
        tmp_path, "company/old.json", group(entry("Old", ("おーるど", "Old"), status="deprecated"))
    )
    assert build_packs(load(tmp_path)) == []


def test_render_text_matches_gboard_v2_format():
    text = render_text([("こるせあ", "Corsair", "組織"), ("とらいあんふ", "Triumph", "品詞なし")])
    assert text == (
        "# Gboard Dictionary version:2\n"
        "# Gboard Dictionary format:shortcut\tword\tlanguage_tag\tpos_tag\n"
        "こるせあ\tCorsair\tja-JP\t組織\n"
        "とらいあんふ\tTriumph\tja-JP\t品詞なし\n"
    )
    assert check_text(text) == 2


def test_zip_is_deterministic_and_minimal():
    text = render_text([("こるせあ", "Corsair", "組織")])
    first, second = render_zip(text), render_zip(text)
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        (info,) = archive.infolist()
        assert info.filename == "dictionary.txt"
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
    assert read_zip_text(first) == text


@pytest.mark.parametrize(
    "text",
    [
        BOM + HEADER,
        HEADER.replace("\n", "\r\n"),
        "# Gboard Dictionary version:1\n",
        HEADER + "こるせあ\tCorsair\tja-JP\n",  # 3列
        HEADER + "こるせあ\tCorsair\tja-JP\t謎\n",  # 未知の品詞名
        HEADER + "こるせあ\tCorsair\ten\t組織\n",  # 言語タグ
        HEADER + "こるせあ\t" + "🎉" * 76 + "\tja-JP\t組織\n",  # 300 バイト超
        HEADER + "こるせあ\tCorsair\tja-JP\t組織\n" * 2,  # 重複行
        HEADER + "こるせあ\tCorsair\tja-JP\t組織",  # 末尾の改行なし
    ],
)
def test_check_text_rejects_inputs_gboard_would_mishandle(text):
    with pytest.raises(GboardFormatError):
        check_text(text)


def test_write_packs_removes_stale_packs(tmp_path):
    make_dictionary(tmp_path)
    out = tmp_path / "dist" / "gboard"
    out.mkdir(parents=True)
    (out / "goi-gboard-removed.zip").write_bytes(b"old")
    (out / "keep-me.txt").write_text("unrelated")
    paths = write_packs(build_packs(load(tmp_path)), out)
    assert sorted(p.name for p in out.iterdir()) == [
        "goi-gboard-all.zip",
        "goi-gboard-company.zip",
        "goi-gboard-vehicle.zip",
        "keep-me.txt",
    ]
    assert len(paths) == 3


def test_cli_build_writes_packs_under_root(tmp_path):
    make_dictionary(tmp_path)
    result = runner.invoke(app, ["build", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    zip_path = tmp_path / "dist" / "gboard" / "goi-gboard-all.zip"
    assert "goi-gboard-all.zip: 3 件（読みと表記の組）" in result.output
    first = zip_path.read_bytes()
    assert runner.invoke(app, ["build", "--root", str(tmp_path)]).exit_code == 0
    assert zip_path.read_bytes() == first  # 再ビルドしても同じバイト列


def test_cli_build_refuses_on_validation_errors(tmp_path):
    write(tmp_path, "company/pc.json", group(entry("Corsair", ("コルセア", "Corsair"))))
    result = runner.invoke(app, ["build", "--root", str(tmp_path), "--out", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "検証エラーが 1 件あるため出力しない" in result.output
    assert not (tmp_path / "out").exists()


# --- レビュー指摘（e8251b0）の回帰テスト ---


def test_top_level_all_is_reserved(tmp_path):
    write(tmp_path, "all/a.json", group(entry("Triumph", ("とらいあんふ", "Triumph"))))
    write(tmp_path, "company/b.json", group(entry("Corsair", ("こるせあ", "Corsair"))))
    result = runner.invoke(app, ["build", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert (
        "最上位のディレクトリ名 all は全件入りの配布物の名前に使うため予約されている"
        in result.output
    )
    assert not (tmp_path / "dist").exists()


def test_write_packs_refuses_duplicate_filenames(tmp_path):
    from dictctl.export_gboard import Pack

    packs = [Pack("all", [("あ", "A", "名詞")]), Pack("all", [("い", "I", "名詞")])]
    with pytest.raises(GboardFormatError, match="配布物の名前が重複"):
        write_packs(packs, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_check_text_enforces_character_limit_too():
    assert check_text(render_text([("あ", "A" * 100, "品詞なし")])) == 1
    with pytest.raises(GboardFormatError, match="100 文字"):
        check_text(render_text([("あ", "A" * 101, "品詞なし")]))
