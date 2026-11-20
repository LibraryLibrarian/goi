#!/usr/bin/env python3
"""imp.py <zipname>: import a zip from Downloads via Gboard's JA personal dictionary screen, then report DB state."""
import subprocess, sys, time
sys.path.insert(0, "/tmp/goi-spike/tools")
import ui
DB = "/data/data/com.google.android.inputmethod.latin/databases/PersonalDictionary.db"
def texts(): return [(t, d) for _, t, d in ui.nodes(ui.dump())]
def tap(p, i=0):
    import re
    pat = re.compile(p)
    for _ in range(10):
        hits = [n for n, t, d in ui.nodes(ui.dump()) if pat.search(t) or pat.search(d)]
        if len(hits) > i:
            x, y = ui.center(hits[i]); ui.adb("shell", "input", "tap", str(x), str(y)); return
        time.sleep(0.5)
    raise SystemExit(f"NOT FOUND {p}: {texts()}")
name = sys.argv[1]
tap("^More options$"); tap("^Import$"); time.sleep(1.5)
if "Files in Downloads" not in str(texts()):
    tap("^Show roots$"); tap("^Downloads$"); time.sleep(1)
if "Clear query" in str(texts()): tap("^Clear query$")
else: tap("^Search$"); time.sleep(0.5); ui.adb("shell", "input", "text", name); ui.adb("shell", "input", "keyevent", "66"); time.sleep(1.5)
tap(f"^Preview the file {name}$"); tap(f"^{name}$", 1)
t0 = time.time(); seen = set()
while time.time() - t0 < float(sys.argv[2] if len(sys.argv) > 2 else 20):
    cur = [t or d for t, d in texts()]
    for s in cur:
        if s not in seen and any(k in s.lower() for k in ("import", "error", "fail", "インポート", "形式")): print("UI:", s); seen.add(s)
    time.sleep(1)
print(subprocess.run(["adb", "-s", ui.SER, "shell", f"sqlite3 {DB} 'select count(*), count(distinct word||char(9)||shortcut) from entry'"], capture_output=True, text=True).stdout.strip(), "(rows, distinct pairs)")
