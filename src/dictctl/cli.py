"""dictctl のコマンドライン。

終了コード:
  0  成功（警告だけの場合を含む）
  1  検査で問題が見つかった（validate のエラー、fmt --check・schema --check の差分、
     読み込めず整形できなかったファイル、検証エラーによる build の中止）
  2  コマンドの使い方の誤り（Typer の既定）
"""

from __future__ import annotations

import sys
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from dictctl.diagnostics import has_errors
from dictctl.export_gboard import build_packs, write_packs
from dictctl.fmt import format_dictionary
from dictctl.loader import load_dictionary
from dictctl.release import (
    DictionaryLoadError,
    dictionary_rows,
    next_version,
    render_notes,
    render_tsv,
)
from dictctl.schema import SCHEMA_FILENAME, render_schema, write_schema
from dictctl.validate import validate_groups

app = typer.Typer(
    help="goi 辞書の検証・整形・ビルドを行うツール。",
    no_args_is_help=True,
    add_completion=False,
)

RootOption = Annotated[
    Path,
    typer.Option(
        "--root",
        help="リポジトリのルート（dictionary/ と schema/ があるディレクトリ）。",
        file_okay=False,
        dir_okay=True,
    ),
]


@app.command()
def validate(root: RootOption = Path(".")) -> None:
    """dictionary/ 配下の全ファイルを検証する。"""
    result = load_dictionary(root)
    issues = sorted(result.issues + validate_groups(result.groups))
    for issue in issues:
        typer.echo(issue.format())

    errors = sum(issue.level == "error" for issue in issues)
    warnings = len(issues) - errors
    entries = sum(len(loaded.group.entries) for loaded in result.groups)
    if issues:
        typer.echo("")
    loaded = len(result.groups)
    files = f"{loaded}" if loaded == result.file_count else f"{loaded}/{result.file_count}"
    typer.echo(f"{files} ファイル（{entries} 語）を検証: エラー {errors} 件、警告 {warnings} 件")
    if has_errors(issues):
        raise typer.Exit(code=1)


@app.command()
def schema(
    root: RootOption = Path("."),
    check: Annotated[
        bool,
        typer.Option("--check", help="書き込まず、コミット済みのスキーマが最新かだけを確認する。"),
    ] = False,
) -> None:
    """Pydantic モデルから schema/group.schema.json を生成する。"""
    directory = root / "schema"
    path = directory / SCHEMA_FILENAME
    if check:
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != render_schema():
            typer.echo(f"schema/{SCHEMA_FILENAME} が古い。dictctl schema で更新する")
            raise typer.Exit(code=1)
        typer.echo(f"schema/{SCHEMA_FILENAME} は最新")
        return
    write_schema(directory)
    typer.echo(f"schema/{SCHEMA_FILENAME} を書き出した")


@app.command()
def fmt(
    root: RootOption = Path("."),
    check: Annotated[
        bool,
        typer.Option("--check", help="書き込まず、整形が必要なファイルがあるかだけを確認する。"),
    ] = False,
) -> None:
    """dictionary/ 配下のファイルを正規の形に整形する（キーの順序・語の並び順・正規化）。"""
    result = format_dictionary(root, write=not check)
    for issue in result.issues:
        typer.echo(issue.format())
    for path in result.changed:
        typer.echo(f"整形が必要: {path}" if check else f"整形した: {path}")

    if result.issues or result.changed:
        typer.echo("")
    if check:
        summary = f"{result.checked} ファイル中 {len(result.changed)} ファイルの整形が必要"
        if result.changed:
            summary += "（dictctl fmt で直せる）"
    else:
        summary = f"{result.checked} ファイル中 {len(result.changed)} ファイルを整形した"
    if result.issues:
        summary += f"、読み込めないファイル {len(result.issues)} 件"
    typer.echo(summary)
    if result.issues or (check and result.changed):
        raise typer.Exit(code=1)


class Target(StrEnum):
    gboard = "gboard"


class DiffFormat(StrEnum):
    markdown = "markdown"
    tsv = "tsv"


@app.command()
def build(
    root: RootOption = Path("."),
    target: Annotated[
        Target, typer.Option("--target", help="出力する IME の形式。")
    ] = Target.gboard,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="出力先（この下に <target>/ を作る）。省略時は <root>/dist。",
            file_okay=False,
        ),
    ] = None,
) -> None:
    """辞書を検証し、IME 向けの配布物を出力する。検証エラーがあれば出力しない。"""
    result = load_dictionary(root)
    issues = sorted(result.issues + validate_groups(result.groups))
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        for issue in errors:
            typer.echo(issue.format())
        typer.echo("")
        typer.echo(
            f"検証エラーが {len(errors)} 件あるため出力しない（dictctl validate で確認できる）"
        )
        raise typer.Exit(code=1)

    packs = build_packs(result.groups)
    out_dir = (out if out is not None else root / "dist") / target.value
    paths = write_packs(packs, out_dir)
    for pack, path in zip(packs, paths, strict=True):
        typer.echo(f"{path}: {len(pack.rows)} 件（読みと表記の組）")
    if not packs:
        typer.echo("出力する語がない")


@app.command()
def diff(
    new: Annotated[
        Path,
        typer.Option("--new", help="新しい版のリポジトリのルート。", file_okay=False),
    ] = Path("."),
    old: Annotated[
        Path | None,
        typer.Option(
            "--old",
            help="前の版のリポジトリのルート。省略すると初回のリリースとして扱う。",
            file_okay=False,
        ),
    ] = None,
    output_format: Annotated[
        DiffFormat,
        typer.Option(
            "--format",
            help="markdown: リリースノート（長いと省略する）。tsv: 全件のタブ区切り。",
        ),
    ] = DiffFormat.markdown,
) -> None:
    """前の版との差分（追加・削除・変更された語）を出力する。"""
    try:
        old_rows = dictionary_rows(old) if old is not None else None
        new_rows = dictionary_rows(new)
    except DictionaryLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    render = render_tsv if output_format is DiffFormat.tsv else render_notes
    typer.echo(render(old_rows, new_rows), nl=False)


@app.command("release-version")
def release_version(
    day: Annotated[str, typer.Option("--date", help="リリースの日付（YYYY-MM-DD、日本時間）。")],
) -> None:
    """既存のタグ（標準入力から1行に1つ）をもとに、次の版の名前を出力する。"""
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        typer.echo(f"日付の形式が正しくない: {day}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(next_version(parsed, sys.stdin.read().splitlines()))


def main() -> None:
    app()
