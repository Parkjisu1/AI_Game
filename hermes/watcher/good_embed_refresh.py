#!/usr/bin/env python3
"""
주기 임베딩 — 헤르메스/마더가 좋은 결과로 똑똑해지게.
나쁜 결과(실패/거부/차단/저득점)는 학습 안 함 (사용자 요구: 필터링).

1) p3a_good_tagging: hermes_team_scores reviewer max → pixelforge_tasks.best_score 태깅
2) pixelforge_tasks: **best_score>=80(=Reviewer APPROVED 고득점)만** 임베딩 → 좋은 작업만 RAG 참조
3) code_base / design_base: 신규만 임베딩 (소스/기획 = ground truth, Hermes 산출물 아님 → 필터 불필요)

cron(Mother)에서 6시간마다. 로그 ~/.hermes/logs/good_embed_refresh.log
"""
import os, subprocess
from dotenv import load_dotenv

load_dotenv("/home/aimed/.hermes/watcher/.env")
PY = "/home/aimed/.hermes/watcher/venv/bin/python"
WATCHER = "/home/aimed/.hermes/watcher"
EMBED = "/home/aimed/embed_collection.py"


def run(args, timeout=1800):
    print(">>", " ".join(args), flush=True)
    try:
        r = subprocess.run([PY] + args, capture_output=True, text=True, timeout=timeout, env=os.environ.copy())
        print((r.stdout or "")[-800:], flush=True)
        if r.returncode != 0:
            print("ERR:", (r.stderr or "")[-400:], flush=True)
    except Exception as e:
        print("EXC:", e, flush=True)


def main():
    run([f"{WATCHER}/p3a_good_tagging.py"])                              # best_score 태깅
    run([EMBED, "pixelforge_tasks", "--min-best-score", "80"])          # 좋은 작업만
    run([EMBED, "code_base"])                                            # 코드 ground truth (신규)
    run([EMBED, "design_base"])                                          # 기획 ground truth (신규)
    print("good_embed_refresh done", flush=True)


if __name__ == "__main__":
    main()
