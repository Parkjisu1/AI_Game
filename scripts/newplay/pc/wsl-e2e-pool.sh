#!/bin/bash
# wsl-e2e-pool.sh — 다계정 풀 + 로컬 지식베이스 자체 QA (WSL, newplay). 실제 Claude 계정 없이 검증 가능한 부분.
export PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH
cd ~/.hermes-newteam/watcher
set -a; . ./.env; set +a

echo "== 1) 지식베이스: 로컬 임베딩 검색"
venv/bin/python - <<'EOP'
import newplay_kb as kb
print("  health:", kb.health())
hits = kb.search("결제 승인 후 orderId 불일치로 거부되는 경로", top=3)
for h in hits:
    p = h["payload"]; print(f"  {h['score']:.3f} {p['path']}:{p['startLine']}-{p['endLine']} ({p['area']}/{p['kind']})")
assert hits, "검색 결과 없음"
EOP

echo "== 2) 토큰 CLI: 가짜 계정 등록 → 검증 → 목록"
printf 'sk-ant-oat01-bogus-qa-token-0000000000\n' | venv/bin/python claude_token_cli.py add qa-bogus@newplay.test | tail -2
venv/bin/python claude_token_cli.py list

echo "== 3) 풀 라우팅: 요청자 계정(가짜) → 인증 실패 → 폴백(로그인 없음) → 실패 사유에 두 시도가 모두 남는가"
venv/bin/python - <<'EOP'
import agent_team as AT
AT.set_actor("qa-bogus@newplay.test")
ok, out, err, acct = AT._call_claude("ping", 60, None, model="claude-sonnet-5")
print("  ok=", ok, "| account=", repr(acct)); print("  err=", err[:300])
assert not ok and "qa-bogus@newplay.test" in err and "login" in err, "라우팅/폴백 경로 불일치"
EOP

echo "== 4) 한도 문구 → 휴식 처리"
venv/bin/python - <<'EOP'
import claude_pool as CP
CP.mark_limited("qa-bogus@newplay.test")
c = [a for a, _ in CP.candidates("qa-bogus@newplay.test")]
print("  candidates after limit:", c); assert c[0] != "qa-bogus@newplay.test"
EOP

echo "== 5) 정리"
venv/bin/python claude_token_cli.py remove qa-bogus@newplay.test
echo "== 6) 서비스"
systemctl --user restart hermes-newteam; sleep 6; systemctl --user is-active hermes-newteam; tail -2 ~/.hermes-newteam/logs/watcher.log
echo E2E_POOL_OK
