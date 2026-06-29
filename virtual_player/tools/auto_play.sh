#!/bin/bash
# PixelFlow Auto Play — 전처리 완료 대기 → BlueStacks → 게임 → 자동 진행
set -e

PYTHON="C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe"
ADB="C:/Program Files/BlueStacks_nxt/HD-Adb.exe"
BLUESTACKS="C:/Program Files/BlueStacks_nxt/HD-Player.exe"
PACKAGE="com.loomgames.pixelflow"
ACTIVITY="com.unity3d.player.UnityPlayerActivity"
DURATION=${1:-1200}  # default 20 hours

echo "=== PixelFlow Auto Play ==="
echo "Duration: ${DURATION} minutes"

# 1. Wait for fingerprint build to finish
echo "[1/5] Waiting for fingerprint build..."
while true; do
    if ! ps aux 2>/dev/null | grep -q "build_fingerprint"; then
        # Check if python process running build_fingerprint_db.py
        if ! tasklist 2>/dev/null | grep -q "python"; then
            break
        fi
        # Check log for "Done:" marker
        if grep -q "^Done:" "E:/AI/virtual_player/data/pixelflow/logs/fingerprint_build.log" 2>/dev/null; then
            break
        fi
    fi
    sleep 30
    tail -1 "E:/AI/virtual_player/data/pixelflow/logs/fingerprint_build.log" 2>/dev/null
done
echo "  Fingerprint build complete!"

# 2. Launch BlueStacks
echo "[2/5] Launching BlueStacks..."
"$BLUESTACKS" --instance Pie64 &
sleep 40

# 3. Wait for ADB
echo "[3/5] Waiting for ADB..."
for i in $(seq 1 30); do
    if "$ADB" -s emulator-5554 shell echo ok 2>/dev/null | grep -q ok; then
        echo "  ADB connected!"
        break
    fi
    sleep 5
done

# 4. Check resolution and launch game
echo "[4/5] Setting up and launching game..."
RES=$("$ADB" -s emulator-5554 shell wm size 2>&1)
echo "  Resolution: $RES"

"$ADB" -s emulator-5554 shell am start -n "$PACKAGE/$ACTIVITY" 2>&1
sleep 20

# Verify game is running
FG=$("$ADB" -s emulator-5554 shell dumpsys window 2>&1 | grep mCurrentFocus)
echo "  Foreground: $FG"

# 5. Start smart player
echo "[5/5] Starting Smart Player (${DURATION} min)..."
cd E:/AI
"$PYTHON" -u -m virtual_player.tester.smart_player_pixelflow --duration "$DURATION" 2>&1 | tee "E:/AI/virtual_player/data/pixelflow/logs/auto_play_$(date +%Y%m%d_%H%M%S).log"
