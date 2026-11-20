import json
from pathlib import Path


def entry(name: str, *conversions: tuple, sources: int = 2, **extra) -> dict:
    """conversions は (読み, 表記) または (読み, 表記, 品詞)。"""
    convs = []
    for conv in conversions:
        item = {"reading": conv[0], "surface": conv[1]}
        if len(conv) > 2:
            item["pos"] = conv[2]
        convs.append(item)
    srcs = [{"url": f"https://example.com/{name}/{i}"} for i in range(sources)]
    return {"name": name, "conversions": convs, "sources": srcs, **extra}


def group(*entries: dict, title: str = "テスト", pos: str | None = None) -> dict:
    data: dict = {"schema_version": 1, "title": title, "entries": list(entries)}
    if pos is not None:
        data["defaults"] = {"pos": pos}
    return data


def write(root: Path, rel: str, data: dict | str | bytes) -> Path:
    path = root / "dictionary" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path
