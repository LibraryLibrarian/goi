#!/bin/bash
# timed.sh <zip> <expected_total>: import and time until mozc+DB counts settle
E=emulator-5580; DB=/data/data/com.google.android.inputmethod.latin/databases/PersonalDictionary.db
python3 -I /tmp/goi-spike/tools/imp.py "$1" 0 >/dev/null
start=$(date +%s); prev=-1; stable=0
while true; do
  n=$(adb -s $E shell "sqlite3 $DB 'select count(*) from entry'" | tr -d '\r')
  m=$(adb -s $E shell "stat -c %s /data/data/com.google.android.inputmethod.latin/.mozc/user_dictionary.db" | tr -d '\r')
  echo "t=$(( $(date +%s)-start ))s rows=$n mozc_bytes=$m"
  if [ "$n" = "$prev" ] && [ "$n" -ge "$2" ]; then stable=$((stable+1)); else stable=0; fi
  [ $stable -ge 3 ] && break; prev=$n; sleep 3
  [ $(( $(date +%s)-start )) -gt 900 ] && { echo TIMEOUT; break; }
done
