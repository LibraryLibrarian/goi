import json
import unicodedata

from helpers import entry, group, write
from typer.testing import CliRunner

from dictctl.cli import app
from dictctl.fmt import format_group, normalize_reading, render, schema_ref

runner = CliRunner()
IDEOGRAPHIC_SPACE = chr(0x3000)


def test_schema_ref_depends_on_depth():
    assert schema_ref("vehicle/motorcycle.json") == "../../schema/group.schema.json"
    assert schema_ref("company/pc/peripherals.json") == "../../../schema/group.schema.json"


def test_normalize_reading():
    assert normalize_reading("コルセア") == "こるせあ"
    assert normalize_reading("ﾄﾗｲｱﾝﾌ") == "とらいあんふ"  # 半角カナ
    assert normalize_reading("ヴァーチャル") == "ゔぁーちゃる"
    assert normalize_reading("ヵヶ") == "ゕゖ"
    assert normalize_reading(IDEOGRAPHIC_SPACE + "こるせあ ") == "こるせあ"


def test_format_group_produces_canonical_form():
    nfd_surface = unicodedata.normalize("NFD", "ガジェット")
    raw = {
        "entries": [
            {
                "tags": ["vehicle", "british"],
                "sources": [{"note": None, "url": "https://example.com/triumph"}],
                "conversions": [{"surface": "Triumph", "reading": "トライアンフ", "pos": None}],
                "name": "Triumph" + IDEOGRAPHIC_SPACE,
            },
            {
                "name": nfd_surface,
                "conversions": [{"reading": "がじぇっと", "surface": nfd_surface}],
                "sources": [{"url": "https://example.com/gadget"}],
                "tags": [],
                "memo": "未定義のキーは残す",
            },
        ],
        "title": "テスト",
        "defaults": {},
        "schema_version": 1,
    }
    formatted = format_group(raw, "vehicle/motorcycle.json")
    assert render(formatted) == (
        json.dumps(
            {
                "$schema": "../../schema/group.schema.json",
                "schema_version": 1,
                "title": "テスト",
                "entries": [
                    {
                        "name": "ガジェット",
                        "conversions": [{"reading": "がじぇっと", "surface": "ガジェット"}],
                        "sources": [{"url": "https://example.com/gadget"}],
                        "memo": "未定義のキーは残す",
                    },
                    {
                        "name": "Triumph",
                        "conversions": [{"reading": "とらいあんふ", "surface": "Triumph"}],
                        "sources": [{"url": "https://example.com/triumph"}],
                        "tags": ["british", "vehicle"],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def test_conversion_and_source_order_inside_entry_is_kept():
    raw = group(entry("Corsair", ("こるせあ", "Corsair"), ("こーせあ", "Corsair")))
    raw["entries"][0]["sources"] = [
        {"url": "https://example.com/z"},
        {"url": "https://example.com/a"},
    ]
    formatted = format_group(raw, "company/pc/peripherals.json")
    entry_out = formatted["entries"][0]
    assert [c["reading"] for c in entry_out["conversions"]] == ["こるせあ", "こーせあ"]
    assert [s["url"] for s in entry_out["sources"]] == [
        "https://example.com/z",
        "https://example.com/a",
    ]


def test_format_is_idempotent():
    raw = group(
        entry("Triumph", ("トライアンフ", "Triumph")),
        entry("Corsair", ("コルセア", "Corsair")),
        pos="組織",
    )
    once = render(format_group(raw, "company/brands.json"))
    twice = render(format_group(json.loads(once), "company/brands.json"))
    assert once == twice


def test_cli_check_write_and_validate_roundtrip(tmp_path):
    path = write(
        tmp_path,
        "company/pc/peripherals.json",
        group(entry("Corsair", ("コルセア", "Corsair"))),
    )
    before = path.read_bytes()

    # 整形前はカタカナの読みで validate が失敗する
    assert runner.invoke(app, ["validate", "--root", str(tmp_path)]).exit_code == 1

    result = runner.invoke(app, ["fmt", "--root", str(tmp_path), "--check"])
    assert result.exit_code == 1
    assert "整形が必要: dictionary/company/pc/peripherals.json" in result.output
    assert path.read_bytes() == before  # --check は書き換えない

    result = runner.invoke(app, ["fmt", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "1 ファイル中 1 ファイルを整形した" in result.output

    assert runner.invoke(app, ["fmt", "--root", str(tmp_path), "--check"]).exit_code == 0
    assert runner.invoke(app, ["validate", "--root", str(tmp_path)]).exit_code == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["$schema"] == "../../../schema/group.schema.json"
    assert data["entries"][0]["conversions"][0]["reading"] == "こるせあ"


def test_cli_reports_unreadable_files_and_continues(tmp_path):
    write(tmp_path, "company/broken.json", '{"title": ')
    ok = write(tmp_path, "company/pc.json", group(entry("Corsair", ("コルセア", "Corsair"))))
    result = runner.invoke(app, ["fmt", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert "dictionary/company/broken.json" in result.output
    assert "読み込めないファイル 1 件" in result.output
    assert "こるせあ" in ok.read_text(encoding="utf-8")


def test_cli_missing_dictionary_is_noop(tmp_path):
    result = runner.invoke(app, ["fmt", "--root", str(tmp_path), "--check"])
    assert result.exit_code == 0
    assert "0 ファイル中 0 ファイルの整形が必要" in result.output


# --- レビュー指摘（f8b07d9）の回帰テスト ---
# fmt がデータを変えたり、validate の結果を変えたりしない


def _validate(root) -> int:
    return runner.invoke(app, ["validate", "--root", str(root)]).exit_code


def test_unknown_null_keys_in_defaults_are_kept(tmp_path):
    raw = group(entry("Corsair", ("こるせあ", "Corsair")))
    raw["defaults"] = {"typo": None, "pos": None}
    path = write(tmp_path, "company/pc.json", raw)
    assert _validate(tmp_path) == 1
    assert runner.invoke(app, ["fmt", "--root", str(tmp_path)]).exit_code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["defaults"] == {"typo": None}
    assert _validate(tmp_path) == 1  # 未定義キーは引き続き検出される


def test_source_urls_are_not_normalized(tmp_path):
    composed = "https://example.com/" + "ガ"
    decomposed = "https://example.com/" + unicodedata.normalize("NFD", "ガ")
    raw = group(entry("Corsair", ("こるせあ", "Corsair")))
    raw["entries"][0]["sources"] = [{"url": composed}, {"url": decomposed}]
    path = write(tmp_path, "company/pc.json", raw)
    assert _validate(tmp_path) == 0
    assert runner.invoke(app, ["fmt", "--root", str(tmp_path)]).exit_code == 0
    urls = [s["url"] for s in json.loads(path.read_text(encoding="utf-8"))["entries"][0]["sources"]]
    assert urls == [composed, decomposed]
    assert _validate(tmp_path) == 0


def test_schema_ref_is_not_accepted_as_json_key(tmp_path):
    raw = group(entry("Corsair", ("こるせあ", "Corsair")))
    raw["schema_ref"] = "../../schema/group.schema.json"
    write(tmp_path, "company/pc.json", raw)
    result = runner.invoke(app, ["validate", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert "schema_ref: 定義されていない項目がある" in result.output


def test_lone_surrogate_is_reported_per_file(tmp_path):
    lone_surrogate = chr(0x5C) + "ud800"  # JSON 上のエスケープ表記
    write(
        tmp_path, "company/broken.json", '{"schema_version": 1, "title": "' + lone_surrogate + '"}'
    )
    ok = write(tmp_path, "company/pc.json", group(entry("Corsair", ("コルセア", "Corsair"))))

    result = runner.invoke(app, ["fmt", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "単独のサロゲート" in result.output
    assert "こるせあ" in ok.read_text(encoding="utf-8")  # 後続のファイルは整形される

    result = runner.invoke(app, ["validate", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert "dictionary/company/broken.json: JSON に不正な Unicode" in result.output


# --- 全体レビューの指摘の回帰テスト ---


def test_fmt_does_not_write_through_symlinks(tmp_path):
    outside = tmp_path / "outside.json"
    original = '{"title": "辞書の外のファイル"}'
    outside.write_text(original, encoding="utf-8")
    write(tmp_path, "company/pc.json", group(entry("Corsair", ("コルセア", "Corsair"))))
    (tmp_path / "dictionary" / "company" / "linked.json").symlink_to(outside)

    result = runner.invoke(app, ["fmt", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert "dictionary/company/linked.json: シンボリックリンクは使えない" in result.output
    assert outside.read_text(encoding="utf-8") == original  # 辞書の外は変更しない
    assert "こるせあ" in (tmp_path / "dictionary/company/pc.json").read_text(encoding="utf-8")


def test_fmt_leaves_data_license_untouched(tmp_path):
    write(tmp_path, "company/pc.json", group(entry("Corsair", ("コルセア", "Corsair"))))
    license_path = tmp_path / "dictionary" / "LICENSE"
    license_path.write_text("CC0 1.0 Universal\n", encoding="utf-8")
    result = runner.invoke(app, ["fmt", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert license_path.read_text(encoding="utf-8") == "CC0 1.0 Universal\n"
    assert runner.invoke(app, ["validate", "--root", str(tmp_path)]).exit_code == 0


def test_file_tags_are_sorted_and_placed_after_title():
    raw = group(entry("Corsair", ("こるせあ", "Corsair")))
    raw["tags"] = ["zeta", "alpha"]
    formatted = format_group(raw, "company/pc.json")
    assert list(formatted) == ["$schema", "schema_version", "title", "tags", "entries"]
    assert formatted["tags"] == ["alpha", "zeta"]
    raw["tags"] = []
    assert "tags" not in format_group(raw, "company/pc.json")
