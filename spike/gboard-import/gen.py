#!/usr/bin/env python3
"""Generate Gboard import test zips into the given output dir."""
import random, sys, zipfile
from pathlib import Path
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
H2 = "# Gboard Dictionary version:2\n# Gboard Dictionary format:shortcut\tword\tlanguage_tag\tpos_tag\n"
H1 = "# Gboard Dictionary version:1\n"
def v2(rows): return H2 + "".join(f"{r}\t{w}\tja-JP\t{p}\n" for r, w, p in rows)
def write(name, text, inner="dictionary.txt", enc="utf-8"):
    zi = zipfile.ZipInfo(inner, date_time=(2020, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(OUT / name, "w") as z: z.writestr(zi, text.encode(enc))
BASIC = [("てすとあんそろぴっく", "テストAnthropic", "組織"),
         ("てすとじんめい", "手酢戸人名", "人名"),
         ("てすとこゆう", "テスト固有", "固有名詞"),
         ("てすとなし", "テスト品詞なし", "品詞なし"),
         ("てすとから", "テスト空品詞", "")]
write("t01_basic.zip", v2(BASIC))
write("t02_basic_again.zip", v2(BASIC))
write("t03_modified.zip", v2([("てすとあんそろぴっく", "テストAnthropic改", "組織"),   # same reading, new word
                              ("てすとじんめい", "手酢戸人名", "固有名詞"),          # same pair, new pos
                              ("てすとしんき", "テスト新規", "名詞")]))
write("t04_v1.zip", H1 + "てすとぶいわん\tテストV1\tja-JP\n")
write("t05_badline.zip", v2([("てすとばっど1", "テストBad1", "名詞")]) + "てすとこわれ\tテスト壊れ\n" + "てすとばっど3\tテストBad3\tja-JP\t名詞\n")
for i, (r, w, p) in enumerate([("テストカタカナヨミ", "テストカタカナ読み", "名詞"),
                               ("testascii", "テストASCII読み", "名詞"),
                               ("てすと2ばん", "テスト数字読み", "名詞"),
                               ("てすとゔぁー", "テストヴァー", "名詞"),
                               ("てすとえもじ", "テスト🎉絵文字", "名詞"),
                               ("てすとあぽす", "Rock'n'Roll", "名詞"),
                               ("てすとながい", "長" * 100, "名詞"),
                               ("てすとながすぎ", "超" * 101, "名詞"),
                               ("て" * 60, "テスト長い読み", "名詞"),
                               ("てすとふめい", "テスト不明品詞", "存在しない品詞"),
                               ("てすとぜんかく", "ＡＢＣテスト", "名詞")]):
    write(f"t06_{i:02d}.zip", v2([(r, w, p)]))
write("t07_crlf_bom.zip", ("﻿" + v2([("てすとくらいふ", "テストCRLF", "名詞")])).replace("\n", "\r\n"))
write("t08_noheader.zip", "てすとへっだなし\tテストヘッダなし\tja-JP\t名詞\n")
write("t09_othername.zip", v2([("てすとふぁいるめい", "テストファイル名", "名詞")]), inner="words.txt")
random.seed(42); KANA = [chr(c) for c in range(ord("ぁ"), ord("ゖ") + 1)]
for n in (1000, 10000, 50000):
    rows = [("".join(random.choices(KANA, k=6)) + "ん", f"大量{n}x{i:05d}", "名詞") for i in range(n)]
    write(f"L{n}.zip", v2(rows))
print("\n".join(sorted(p.name for p in OUT.iterdir())))
