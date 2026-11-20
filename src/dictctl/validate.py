"""読み込んだ辞書ファイルに対する、モデルだけでは判定できない検査。

ファイル内の検査:
  - テキストが NFC 正規化されている
  - 表記・読みが UTF-8 で300バイト以内（Gboard はそれを超える語を変換に使わない）
  - 同じファイル内で「読み＋表記」が重複しない、出典 URL・タグが語の中で重複しない
  - 出典が1件だけの語は警告
ファイルをまたぐ検査（status が active の語だけが対象。deprecated の語はビルドに含めないため）:
  - 「読み＋表記」が同じで品詞が違う組はエラー
    （両方の配布物を取り込んだ端末で、単語リストの行が増えるため）
  - 同じ表記に登録された読みの組み合わせがファイルによって違う場合は警告
    （片方だけ修正された可能性がある。同名の別人など正当な場合もある）
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from dictctl.diagnostics import Issue, error, warning
from dictctl.loader import LoadedGroup
from dictctl.models import Pos

MAX_BYTES = 300


def validate_groups(groups: list[LoadedGroup]) -> list[Issue]:
    issues: list[Issue] = []
    for loaded in groups:
        issues.extend(_check_file(loaded))
    issues.extend(_check_across_files(groups))
    return sorted(issues)


def _entry_loc(index: int, name: str) -> str:
    return f"entries[{index}]「{name}」"


def _check_file(loaded: LoadedGroup) -> list[Issue]:
    path = loaded.display_path
    group = loaded.group
    issues: list[Issue] = []

    issues.extend(_nfc(path, "title", group.title))

    seen_pairs: dict[tuple[str, str], str] = {}
    seen_names: dict[str, str] = {}
    for i, entry in enumerate(group.entries):
        loc = _entry_loc(i, entry.name)
        issues.extend(_nfc(path, f"{loc}.name", entry.name))

        if entry.name in seen_names:
            issues.append(
                warning(
                    path, loc, f"同じ name の語がこのファイルに既にある（{seen_names[entry.name]}）"
                )
            )
        else:
            seen_names[entry.name] = loc

        for j, conv in enumerate(entry.conversions):
            cloc = f"{loc}.conversions[{j}]"
            issues.extend(_nfc(path, f"{cloc}.reading", conv.reading))
            issues.extend(_nfc(path, f"{cloc}.surface", conv.surface))
            for field, value in (("reading", conv.reading), ("surface", conv.surface)):
                size = len(value.encode("utf-8"))
                if size > MAX_BYTES:
                    issues.append(
                        error(
                            path,
                            f"{cloc}.{field}",
                            f"UTF-8 で {MAX_BYTES} バイト以内にする（{size} バイト）",
                        )
                    )
            pair = (conv.reading, conv.surface)
            if pair in seen_pairs:
                issues.append(
                    error(
                        path,
                        cloc,
                        f"読み「{conv.reading}」と表記「{conv.surface}」の組が重複している"
                        f"（{seen_pairs[pair]}）",
                    )
                )
            else:
                seen_pairs[pair] = cloc

        urls: set[str] = set()
        for k, source in enumerate(entry.sources):
            sloc = f"{loc}.sources[{k}]"
            if source.url in urls:
                issues.append(error(path, sloc, f"出典 URL が重複している: {source.url}"))
            urls.add(source.url)
            if source.note is not None:
                issues.extend(_nfc(path, f"{sloc}.note", source.note))
        if len(entry.sources) == 1:
            issues.append(
                warning(path, f"{loc}.sources", "出典が1件だけ。複数あると信頼性が上がる")
            )

        duplicated_tags = sorted({t for t in entry.tags if entry.tags.count(t) > 1})
        if duplicated_tags:
            issues.append(
                error(path, f"{loc}.tags", "タグが重複している: " + ", ".join(duplicated_tags))
            )

    return issues


def _nfc(path: str, location: str, value: str) -> list[Issue]:
    if unicodedata.is_normalized("NFC", value):
        return []
    return [error(path, location, "Unicode の NFC 正規化がされていない（dictctl fmt で直せる）")]


@dataclass(frozen=True)
class _Occurrence:
    path: str
    location: str
    pos: Pos


def _check_across_files(groups: list[LoadedGroup]) -> list[Issue]:
    issues: list[Issue] = []
    by_pair: dict[tuple[str, str], list[_Occurrence]] = defaultdict(list)
    readings_by_surface: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for loaded in groups:
        for i, entry in enumerate(loaded.group.entries):
            if entry.status != "active":
                continue
            for j, conv in enumerate(entry.conversions):
                loc = f"{_entry_loc(i, entry.name)}.conversions[{j}]"
                occ = _Occurrence(loaded.display_path, loc, loaded.group.effective_pos(conv))
                by_pair[(conv.reading, conv.surface)].append(occ)
                readings_by_surface[conv.surface][loaded.display_path].add(conv.reading)

    for (reading, surface), occs in by_pair.items():
        if len({o.pos for o in occs}) <= 1:
            continue
        detail = "、".join(f"{o.path} の {o.location}（{o.pos}）" for o in occs)
        for occ in occs:
            issues.append(
                error(
                    occ.path,
                    occ.location,
                    f"読み「{reading}」と表記「{surface}」が同じで"
                    f"品詞が違う語が他のファイルにある: {detail}",
                )
            )

    for surface, per_file in readings_by_surface.items():
        if len(per_file) < 2 or len({frozenset(r) for r in per_file.values()}) == 1:
            continue
        detail = "、".join(
            f"{path}（{'・'.join(sorted(readings))}）"
            for path, readings in sorted(per_file.items())
        )
        for path in sorted(per_file):
            issues.append(
                warning(
                    path,
                    f"表記「{surface}」",
                    f"同じ表記の読みの組み合わせがファイルによって違う: {detail}",
                )
            )

    return issues
