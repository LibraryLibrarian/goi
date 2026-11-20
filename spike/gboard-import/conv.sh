#!/bin/bash
# conv.sh <romaji> <outpng>: clear composing text, type romaji, expand candidates, screenshot
E=emulator-5580
for i in $(seq 1 40); do adb -s $E shell input keyevent 67; done
adb -s $E shell input text "$1"; sleep 2
adb -s $E shell input tap 1019 1574   # expand candidate chevron (849,1312 *1.2)
sleep 1.5; adb -s $E exec-out screencap -p > "$2"
adb -s $E shell input keyevent 4      # BACK to collapse
