#!/bin/bash
# newplay-claude-setup.sh — NewPlay AI 를 **팀원 각자의 Claude 계정**으로 돌게 만든다. (WSL, newplay 사용자)
#
#   1) 팀원 토큰 등록:   ~/bin/newplay-claude-setup.sh add <email>         (프롬프트에 토큰 붙여넣기)
#      팀원은 자기 PC 에서:  npm i -g @anthropic-ai/claude-code  →  claude setup-token  → 나온 토큰을 관리자에게 DM
#   2) 팀 공용 토큰(선택): ~/bin/newplay-claude-setup.sh add _default        (요청자 토큰이 없을 때 폴백)
#   3) 역할 전부 Claude 로: ~/bin/newplay-claude-setup.sh all-claude            (최초 1회. LiteLLM/OpenAI 역할 16개 → claude)
#   4) 상태:                 ~/bin/newplay-claude-setup.sh status
#
# 그 뒤부터: 작업을 낸 사람의 계정으로 그 작업(분류·PM·코더·검수)이 실행되고, 세션 로그에 어느 계정이 썼는지 남는다.
# 한도에 걸리면 그 계정은 30분 쉬고 팀 공용(_default)이 있으면 그걸로 이어간다. 다른 팀원 계정은 빌리지 않는다(기본).
set -e
W=~/.hermes-newteam/watcher
PY=$W/venv/bin/python
export PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH
cmd=${1:-status}

case "$cmd" in
  add)
    [ -n "$2" ] || { echo "사용: add <email|_default>"; exit 1; }
    $PY $W/claude_token_cli.py add "$2"
    ;;
  remove)
    $PY $W/claude_token_cli.py remove "$2"
    ;;
  test)
    $PY $W/claude_token_cli.py test "$2"
    ;;
  all-claude)
    # 도구가 claude 가 아닌 활성 역할을 전부 claude 로. 가벼운 역할은 sonnet, 코더·리뷰어급은 opus.
    $PY - <<'EOP'
from pymongo import MongoClient
col = MongoClient("mongodb://127.0.0.1:27018/?directConnection=true")["newteam"]["hermes_agent_roles"]
light = {"translator", "dev_pm", "data_pm", "design_pm", "sub_coder", "validator"}
n_light = n_heavy = 0
for r in col.find({"tool": {"$ne": "claude"}, "archived": {"$ne": True}}):
    name = r.get("role", "")
    model = "claude-sonnet-5" if name in light else "claude-opus-5"
    col.update_one({"_id": r["_id"]}, {"$set": {"tool": "claude", "model": model}})
    if model.endswith("sonnet-5"): n_light += 1
    else: n_heavy += 1
print(f"  claude 로 전환: sonnet {n_light}개, opus {n_heavy}개. (AI팀 화면에서 언제든 바꿀 수 있음)")
EOP
    systemctl --user restart hermes-newteam
    echo "  워처 재기동: $(sleep 3; systemctl --user is-active hermes-newteam)"
    ;;
  status)
    echo "== 등록된 Claude 계정"; $PY $W/claude_token_cli.py list
    echo "== CLI 로그인 자격(폴백)"; ( [ -f ~/.claude/.credentials.json ] && echo "  있음 (claude login 됨)" ) || echo "  없음"
    echo "== 역할 도구 분포"; $PY - <<'EOP'
from pymongo import MongoClient
col = MongoClient("mongodb://127.0.0.1:27018/?directConnection=true")["newteam"]["hermes_agent_roles"]
for d in col.aggregate([{"$match": {"archived": {"$ne": True}}}, {"$group": {"_id": {"t": "$tool", "m": "$model"}, "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]):
    print(f"  {d['_id']['t']:<8} {d['_id']['m']:<22} {d['n']}")
EOP
    echo "== 지식베이스"; curl -s http://127.0.0.1:6343/collections/newplay_code_m3 | python3 -c "import sys,json; r=json.load(sys.stdin).get('result',{}); print('  newplay_code_m3 points=', r.get('points_count'), 'status=', r.get('status'))"
    echo "== 최근 세션(계정별)"; $PY - <<'EOP'
from pymongo import MongoClient
col = MongoClient("mongodb://127.0.0.1:27018/?directConnection=true")["newteam"]["hermes_agent_sessions"]
for d in col.aggregate([{"$match": {"tool": "claude"}}, {"$sort": {"created_at": -1}}, {"$limit": 200}, {"$group": {"_id": "$account", "n": {"$sum": 1}, "fail": {"$sum": {"$cond": ["$success", 0, 1]}}}}]):
    print(f"  {(d['_id'] or '(cli-login)'):<32} 호출 {d['n']:>3}  실패 {d['fail']}")
EOP
    ;;
  *) sed -n 2,12p "$0" ;;
esac
