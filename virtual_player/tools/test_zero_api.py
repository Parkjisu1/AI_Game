"""
Zero-API Verification Test
============================
Simulates a full play session using recorded frames.
Monkeypatches claude_vision_classify to detect any API fallback.
"""
import sys
import os
import time
import json

# Force UTF-8 output on Windows
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

from pathlib import Path


def main():
    # ==============================================================
    # STEP 1: Monkeypatch claude_vision_classify to track calls
    # ==============================================================
    import virtual_player.adb.commands as adb_cmds

    api_call_log = []
    original_fn = adb_cmds.claude_vision_classify

    def patched_classify(*args, **kwargs):
        import traceback
        caller = traceback.extract_stack()[-2]
        info = f"{caller.filename}:{caller.lineno} in {caller.name}"
        api_call_log.append(info)
        print(f"  *** API CALL #{len(api_call_log)}: {info} ***")
        return {"screen_type": "unknown", "confidence": 0.0, "error": "BLOCKED"}

    adb_cmds.claude_vision_classify = patched_classify

    # Patch in every module that imported it directly
    import virtual_player.navigation.classifier as clf_mod
    import virtual_player.navigation.popup_handler as ph_mod
    clf_mod.claude_vision_classify = patched_classify
    ph_mod.claude_vision_classify = patched_classify

    # Patch get_device_resolution (no ADB device needed)
    adb_cmds._resolution_cache = (1080, 1920)

    def fake_resolution():
        return (1080, 1920)

    adb_cmds.get_device_resolution = fake_resolution
    import virtual_player.adb as adb_mod
    adb_mod.get_device_resolution = fake_resolution

    print("API monkeypatched - any call will be logged")
    print()

    # ==============================================================
    # STEP 2: Create VisionBrain with reference DB
    # ==============================================================
    from virtual_player.brain.vision_brain import VisionBrain

    data_base = Path("E:/AI/virtual_player/data")
    screen_types = json.loads(
        (data_base / "games/ash_n_veil/screen_types.json").read_text(encoding="utf-8")
    )
    cache_dir = data_base / "cache/ash_n_veil"
    nav_graph = data_base / "games/ash_n_veil/nav_graph.json"
    equiv_path = data_base / "games/ash_n_veil/equivalences.json"
    equivs = (
        json.loads(equiv_path.read_text(encoding="utf-8"))
        if equiv_path.exists() else {}
    )

    brain = VisionBrain(
        screen_types=screen_types,
        game_package="com.test.game",
        cache_dir=cache_dir,
        nav_graph_path=nav_graph,
        screen_equivalences=equivs,
    )

    print(f"Reference DB loaded: {brain._reference_db is not None}")
    print(f"Local vision loaded: {brain._local_vision is not None}")
    if brain._reference_db:
        print(f"Entries: {len(brain._reference_db.get_all_entries())}")
    print()

    # ==============================================================
    # STEP 3: Run full perceive->decide loop on all recorded frames
    # ==============================================================
    frames_dir = data_base / "recordings/ash_n_veil/frames"
    annotations = json.loads(
        (data_base / "recordings/ash_n_veil/annotations.json").read_text(encoding="utf-8")
    )

    # Collect unique frames in sequence order
    seen = set()
    frame_sequence = []
    for ann in annotations:
        for key in ("screenshot_before", "screenshot_after"):
            f = ann.get(key, "")
            if f and f not in seen:
                seen.add(f)
                fp = frames_dir / f
                if fp.exists():
                    frame_sequence.append(fp)

    print(f"Simulating play session: {len(frame_sequence)} frames")
    print("=" * 60)

    brain.set_target("lobby")

    total_time = 0
    decision_log = {"l0": 0, "l1": 0, "l2_bt": 0, "popup": 0}
    screens_seen = set()
    targets = ["menu_shop", "lobby", "menu_character", "quest_list", "menu_summon"]

    for i, fp in enumerate(frame_sequence):
        t0 = time.time()

        # Perceive
        state = brain.perceive(str(fp))
        screen_type = state.parsed.get("screen_type", "unknown")
        screens_seen.add(screen_type)

        # Decide
        action = brain.decide(state)

        elapsed = (time.time() - t0) * 1000
        total_time += elapsed

        # Categorize decision
        aname = action.name
        if aname.startswith("L0_"):
            decision_log["l0"] += 1
        elif aname.startswith("L1_"):
            decision_log["l1"] += 1
        elif "popup" in aname or "dismiss" in aname or "back_dismiss" in aname:
            decision_log["popup"] += 1
        else:
            decision_log["l2_bt"] += 1

        # Change target periodically
        if i % 20 == 0 and i > 0:
            brain.set_target(targets[i // 20 % len(targets)])

        # Progress
        if (i + 1) % 30 == 0:
            print(f"  ... {i+1}/{len(frame_sequence)} frames, "
                  f"avg={total_time/(i+1):.0f}ms/frame, "
                  f"api_calls={len(api_call_log)}")

    # ==============================================================
    # STEP 4: Report
    # ==============================================================
    print()
    print("=" * 60)
    print("PLAY SESSION SIMULATION COMPLETE")
    print("=" * 60)
    print(f"  Frames processed: {len(frame_sequence)}")
    print(f"  Screens seen: {len(screens_seen)} types")
    for s in sorted(screens_seen):
        print(f"    - {s}")
    print(f"  Total time: {total_time:.0f}ms")
    print(f"  Avg per frame: {total_time/len(frame_sequence):.0f}ms")
    print()
    print("Decision breakdown:")
    for k, v in decision_log.items():
        pct = 100 * v / len(frame_sequence)
        print(f"  {k}: {v} ({pct:.0f}%)")
    print()
    print(f"Brain stats: {brain.get_decision_stats()}")
    print()

    # THE KEY RESULT
    print("=" * 60)
    if len(api_call_log) == 0:
        print(f"  PASS: ZERO API CALLS across {len(frame_sequence)} frames")
        print(f"  All decisions made locally (SSIM + template match + BT)")
    else:
        print(f"  FAIL: {len(api_call_log)} API CALL(S) DETECTED!")
        print("  Callers:")
        for caller in api_call_log:
            print(f"    - {caller}")
    print("=" * 60)

    return len(api_call_log)


if __name__ == "__main__":
    sys.exit(main())
