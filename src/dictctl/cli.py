"""dictctl のコマンドライン。

終了コード:
  0  成功（警告だけの場合を含む）
  1  検査で問題が見つかった（validate のエラー、fmt --check・schema --check の差分、
     読み込めず整形できなかったファイル）
  2  コマンドの使い方の誤り（Typer の既定）
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from dictctl.diagnostics import has_errors
from dictctl.fmt import format_dictionary
from dictctl.loader import load_dictionary
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


def main() -> None:
    app()
