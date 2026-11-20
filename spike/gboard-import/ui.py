#!/usr/bin/env python3
"""Tiny uiautomator helper: ui.py dump | ui.py tap <regex> [index]"""
import re, subprocess, sys, xml.etree.ElementTree as ET
SER = "emulator-5580"
def adb(*a): return subprocess.run(["adb", "-s", SER, *a], capture_output=True, text=True).stdout
def dump():
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    xml = adb("shell", "cat", "/sdcard/ui.xml")
    return ET.fromstring(xml[xml.index("<?xml"):] if "<?xml" in xml else xml)
def nodes(root):
    for n in root.iter("node"):
        t, d = n.get("text", ""), n.get("content-desc", "")
        if t or d: yield n, t, d
def center(n):
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", n.get("bounds")))
    return (x1 + x2) // 2, (y1 + y2) // 2
if sys.argv[1] == "dump":
    for n, t, d in nodes(dump()):
        print(f"{n.get('bounds'):28} text={t!r} desc={d!r} res={n.get('resource-id','').split('/')[-1]}")
elif sys.argv[1] == "tap":
    pat = re.compile(sys.argv[2]); idx = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    hits = [n for n, t, d in nodes(dump()) if pat.search(t) or pat.search(d)]
    if len(hits) <= idx: print("NOT FOUND", sys.argv[2]); sys.exit(1)
    x, y = center(hits[idx]); adb("shell", "input", "tap", str(x), str(y)); print("tapped", x, y)
