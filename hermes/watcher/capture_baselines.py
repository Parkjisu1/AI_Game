# -*- coding: utf-8 -*-
"""연동 Unity 프로젝트 4개의 컴파일 베이스라인을 순차 캡처. 기존 에러를 '수용된 상태'로 등록해
이후 게이트가 새 에러만 차단하게 한다. (감사 원인 2 — 베이스라인이 어느 프로젝트에도 없었다)"""
import sys, time
sys.path.insert(0, "/home/aimed/.hermes/watcher")
import hermes_executor as hx
targets = [
    ("user@100.92.43.9", "C:/projects/nextpr", "NextPR"),
    ("user@100.92.43.9", "C:/projects/crewflowrotation", "CrewFlowRotation"),
    ("user@100.92.43.9", "C:/projects/buddyflow", "Buddyflow"),
    ("user@100.92.43.9", "C:/projects/balloonflow", "BalloonFlow"),
]
for host, d, sub in targets:
    t0 = time.time()
    try:
        print(f"[{sub}] {hx.capture_compile_baseline(host, d, sub)}  ({time.time()-t0:.0f}s)", flush=True)
    except Exception as e:
        print(f"[{sub}] FAILED: {e}", flush=True)
print("DONE", flush=True)
