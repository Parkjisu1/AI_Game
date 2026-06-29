#!/bin/bash
# Level 15 Correction 단독 테스트 — pixellab_auth.json 업로드 직후 한 줄로 검증.
#
# 사용:  bash ~/.hermes/watcher/test_lv15_correction.sh
#
# 동작:
#   1) Mongo에서 Level 15 image_base64 추출 → /tmp/lv15_in.png
#   2) pixellab_correction_bot.py 실행 (strength 0.1, debug 모드)
#   3) 결과 /tmp/lv15_out.png + 디버그 스크린샷 /tmp/lv15_debug/

set -u
HERMES=/home/aimed/.hermes/watcher
PY=$HERMES/venv/bin/python
BOT=$HERMES/pixellab_correction_bot.py
AUTH=$HERMES/pixellab_auth.json
DEBUG_DIR=/tmp/lv15_debug
IN=/tmp/lv15_in.png
OUT=/tmp/lv15_out.png

if [ ! -f "$AUTH" ]; then
  echo "❌ auth file missing: $AUTH"
  echo "   먼저 사용자 PC에서 pixellab_login_export.py 실행 후 scp 업로드 필요"
  exit 1
fi
echo "✓ auth file present"

mkdir -p "$DEBUG_DIR"
rm -f "$IN" "$OUT" "$DEBUG_DIR"/*

# Level 15 image extract
$PY <<EOF
import os, base64
from dotenv import load_dotenv
load_dotenv("$HERMES/.env")
from pymongo import MongoClient
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB","aigame")]
lv = db["pixelforge_levels"].find_one({"level_number": 15})
if not lv or not lv.get("image_base64"):
    print("NO LEVEL 15 IMAGE"); raise SystemExit(2)
with open("$IN", "wb") as f:
    f.write(base64.b64decode(lv["image_base64"]))
print(f"✓ wrote Lv15 image to $IN ({lv.get('field_columns')}x{lv.get('field_rows')})")
EOF

[ ! -f "$IN" ] && { echo "image extract failed"; exit 2; }

echo "=== bot run (strength=0.1, debug=$DEBUG_DIR) ==="
$PY $BOT --image "$IN" --strength 0.1 --auth "$AUTH" --output "$OUT" --debug-dir "$DEBUG_DIR"
CODE=$?

echo ""
echo "=== exit code: $CODE ==="
if [ -f "$OUT" ]; then
  SIZE=$(stat -c%s "$OUT")
  echo "✓ output PNG: $OUT ($SIZE bytes)"
fi
echo ""
echo "=== debug files ==="
ls -la "$DEBUG_DIR" 2>/dev/null
