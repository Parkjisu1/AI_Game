#!/bin/bash
# wsl-deploy-code.sh — 다계정 풀 + 로컬 임베딩 코드를 워처에 반영하고, 지식베이스 재임베딩을 시작한다.
set -e
W=~/.hermes-newteam/watcher
SRC=/mnt/c/newplay/watcher-new

# 0) Ollama: 모델을 내리지 않게 (첫 질의 6초 콜드스타트 방지)
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment=OLLAMA_KEEP_ALIVE=-1\n' | sudo tee /etc/systemd/system/ollama.service.d/keepalive.conf >/dev/null
sudo systemctl daemon-reload && sudo systemctl restart ollama
sleep 2

# 1) 코드 반영 + 컴파일 + 커밋 (배포 장치와 같은 git 트리)
cp $SRC/agent_team.py $SRC/hermes_executor.py $SRC/newplay_kb.py $SRC/claude_pool.py $SRC/claude_token_cli.py $SRC/reembed_kb.py $W/
cd $W
venv/bin/python -m py_compile agent_team.py hermes_executor.py newplay_kb.py claude_pool.py claude_token_cli.py reembed_kb.py
git add -A
git -c user.name=hermes -c user.email=hermes@newplay.local commit -q -m "다계정 Claude 풀(작업 요청자 계정으로 실행) + 로컬 bge-m3 임베딩 — OpenAI 의존 제거" || true
echo "watcher git: $(git log --oneline -1)"

# 2) env: 로컬 임베딩으로
grep -q '^NEWPLAY_EMBED_PROVIDER=' .env || printf 'NEWPLAY_EMBED_PROVIDER=ollama\nNEWPLAY_EMBED_MODEL=bge-m3\nNEWPLAY_OLLAMA_URL=http://127.0.0.1:11434\n' >> .env
sed -i 's/^NEWPLAY_KB_COLLECTION=.*/NEWPLAY_KB_COLLECTION=newplay_code_m3/' .env
grep -E '^NEWPLAY_(EMBED|KB|OLLAMA)' .env
mkdir -p ~/.hermes-newteam/claude-tokens && chmod 700 ~/.hermes-newteam/claude-tokens

# 3) 재임베딩 (백그라운드) — 7,176 청크
nohup venv/bin/python reembed_kb.py --from-collection newplay_code --to newplay_code_m3 --batch 16 > ~/.hermes-newteam/logs/reembed.log 2>&1 &
echo "reembed started pid=$!"
sleep 20; tail -2 ~/.hermes-newteam/logs/reembed.log
echo DEPLOY_CODE_OK
