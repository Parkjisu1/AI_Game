#!/bin/bash
# Game Screenshot Capture Script for Phase B
# Captures key game states for AI User observation data

ADB="C:/Program Files/BlueStacks_nxt/HD-Adb.exe"
SHOTS="E:/AI/projects/CleanRoomTest/screenshots"

screenshot() {
    local name="$1"
    "$ADB" -s 127.0.0.1:5555 exec-out screencap -p > "$SHOTS/$name.png"
    echo "[$(date +%H:%M:%S)] Captured: $name"
}

tap() {
    "$ADB" -s 127.0.0.1:5555 shell input tap "$1" "$2"
    sleep "${3:-1.5}"
}

swipe() {
    "$ADB" -s 127.0.0.1:5555 shell input swipe "$1" "$2" "$3" "$4" "${5:-300}"
    sleep "${6:-1.5}"
}

back() {
    "$ADB" -s 127.0.0.1:5555 shell input keyevent KEYCODE_BACK
    sleep "${1:-1.5}"
}

home() {
    "$ADB" -s 127.0.0.1:5555 shell input keyevent KEYCODE_HOME
    sleep 2
}

launch() {
    "$ADB" -s 127.0.0.1:5555 shell monkey -p "$1" -c android.intent.category.LAUNCHER 1 2>/dev/null
    sleep "${2:-8}"
}

forceStop() {
    "$ADB" -s 127.0.0.1:5555 shell am force-stop "$1"
    sleep 1
}

echo "=========================================="
echo "=== PHASE B: Game Screenshot Capture ==="
echo "=========================================="

# ============================
# 1. TAP SHIFT
# ============================
echo ""
echo "--- TAP SHIFT ---"

# Already running, capture current level select
screenshot "tapshift_01_levelselect"

# Scroll down to see earlier completed levels
swipe 400 400 400 900 500 2
screenshot "tapshift_02_early_levels"

# Scroll back up
swipe 400 900 400 400 500 2
swipe 400 900 400 400 500 2

# Tap Settings (gear icon - top right ~690, 145)
tap 690 145 2
screenshot "tapshift_03_settings"
back 1.5

# Tap PLAY to enter current level
tap 400 980 3
screenshot "tapshift_04_gameplay"

# Wait and observe the board
sleep 2
screenshot "tapshift_05_gameplay2"

# Try tapping center of board area to interact with an arrow
tap 400 600 2
screenshot "tapshift_06_after_tap"

# Try another tap
tap 300 500 2
screenshot "tapshift_07_after_tap2"

# Try another tap
tap 500 400 2
screenshot "tapshift_08_after_tap3"

# Go back to level select
back 2
screenshot "tapshift_09_back"

# If there's a popup, tap to dismiss
tap 400 800 2

# Try scrolling to see level 1 area
swipe 400 400 400 1200 800 3
swipe 400 400 400 1200 800 3
swipe 400 400 400 1200 800 3
screenshot "tapshift_10_level1_area"

# Force stop Tap Shift
forceStop "com.paxiegames.tapshift"

# ============================
# 2. MAGIC SORT
# ============================
echo ""
echo "--- MAGIC SORT ---"

launch "com.grandgames.magicsort" 10
screenshot "magicsort_01_launch"

# Wait for any popup/loading
sleep 3
screenshot "magicsort_02_main"

# Tap to dismiss any popup
tap 400 800 2

# Take another screenshot (might be after popup dismiss)
screenshot "magicsort_03_after_dismiss"

# Look for Play button and tap it
tap 400 900 3
screenshot "magicsort_04_gameplay"

# Try interacting - tap a bottle
tap 200 500 2
screenshot "magicsort_05_select"

# Tap another bottle to pour
tap 400 500 2
screenshot "magicsort_06_pour"

# Try another move
tap 300 500 2
tap 500 500 2
screenshot "magicsort_07_move2"

# Go back
back 2
screenshot "magicsort_08_back"

# Check settings if available
tap 690 145 2
screenshot "magicsort_09_settings"
back 2

# Force stop
forceStop "com.grandgames.magicsort"

# ============================
# 3. CAR MATCH
# ============================
echo ""
echo "--- CAR MATCH ---"

launch "com.grandgames.carmatch" 10
screenshot "carmatch_01_launch"

sleep 3
screenshot "carmatch_02_main"

# Dismiss any popup
tap 400 800 2
screenshot "carmatch_03_after_dismiss"

# Look for Play button
tap 400 900 3
screenshot "carmatch_04_gameplay"

# Interact - tap a car
tap 300 400 2
screenshot "carmatch_05_tap1"

tap 400 300 2
screenshot "carmatch_06_tap2"

tap 500 500 2
screenshot "carmatch_07_tap3"

tap 200 300 2
screenshot "carmatch_08_tap4"

# Check the holder area (bottom)
sleep 2
screenshot "carmatch_09_holder"

# Go back
back 2
screenshot "carmatch_10_back"

# Force stop
forceStop "com.grandgames.carmatch"

echo ""
echo "=========================================="
echo "=== Capture Complete ==="
echo "=========================================="
ls -la "$SHOTS"/*.png | wc -l
echo "screenshots captured."
