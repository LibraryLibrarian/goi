from pathlib import Path

from helpers import entry, group, write
from typer.testing import CliRunner

from dictctl.cli import app
from dictctl.schema import SCHEMA_FILENAME, render_schema

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def invoke(*args: str):
    return runner.invoke(app, list(args))


def test_validate_success_with_warnings_exits_zero(tmp_path):
    write(
        tmp_path,
        "company/pc/peripherals.json",
        group(entry("Corsair", ("こるせあ", "Corsair"), sources=1)),
    )
    result = invoke("validate", "--root", str(tmp_path))
    assert result.exit_code == 0, result.output
    assert "警告: dictionary/company/pc/peripherals.json" in result.output
    assert "1 ファイル（1 語）を検証: エラー 0 件、警告 1 件" in result.output


def test_validate_errors_exit_one(tmp_path):
    write(tmp_path, "company/pc/peripherals.json", group(entry("Corsair", ("コルセア", "Corsair"))))
    write(tmp_path, "vehicle/motorcycle.json", group(entry("Triumph", ("とらいあんふ", "Triumph"))))
    result = invoke("validate", "--root", str(tmp_path))
    assert result.exit_code == 1
    assert "エラー: dictionary/company/pc/peripherals.json" in result.output
    # 壊れたファイルがあっても、他のファイルは検証される（読み込めた数/全体の数）
    assert "1/2 ファイル（1 語）を検証: エラー 1 件、警告 0 件" in result.output


def test_validate_missing_dictionary_exits_one(tmp_path):
    result = invoke("validate", "--root", str(tmp_path))
    assert result.exit_code == 1
    assert "dictionary: ディレクトリが見つからない" in result.output


def test_schema_writes_and_checks(tmp_path):
    result = invoke("schema", "--root", str(tmp_path), "--check")
    assert result.exit_code == 1
    assert "が古い" in result.output

    result = invoke("schema", "--root", str(tmp_path))
    assert result.exit_code == 0
    assert (tmp_path / "schema" / SCHEMA_FILENAME).read_text(encoding="utf-8") == render_schema()

    result = invoke("schema", "--root", str(tmp_path), "--check")
    assert result.exit_code == 0
    assert "は最新" in result.output


def test_schema_check_detects_stale_file(tmp_path):
    (tmp_path / "schema").mkdir()
    (tmp_path / "schema" / SCHEMA_FILENAME).write_text("{}\n", encoding="utf-8")
    assert invoke("schema", "--root", str(tmp_path), "--check").exit_code == 1


def test_committed_schema_passes_check():
    assert invoke("schema", "--root", str(REPO_ROOT), "--check").exit_code == 0


def test_usage_error_exits_two():
    assert invoke("validate", "--no-such-option").exit_code == 2


def test_validate_and_build_reject_bidi_override(tmp_path):
    write(
        tmp_path,
        "company/pc.json",
        group(entry("Corsair", ("こるせあ", "ABC" + chr(0x202E) + "DEF"))),
    )
    assert invoke("validate", "--root", str(tmp_path)).exit_code == 1
    assert invoke("build", "--root", str(tmp_path)).exit_code == 1
    assert not (tmp_path / "dist").exists()
