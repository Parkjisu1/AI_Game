#!/bin/bash
# wsl-verify.sh — 컷오버 전 새 장비 자체 검증 (WSL 내부에서)
pkill -f "http.server 3999" 2>/dev/null || true
T="$1"
echo "== services"; systemctl --user is-active projecthub-newteam hermes-newteam | tr '\n' ' '; systemctl is-active mongod qdrant | tr '\n' ' '; echo
echo "== web login"; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/login
echo "== api token auth (watcher history)"; curl -s -m 30 -H "Authorization: Bearer $T" "http://127.0.0.1:3000/api/platform/apply?history=1&target=watcher" | cut -c1-160; echo
echo "== api token auth (platform history)"; curl -s -m 30 -H "Authorization: Bearer $T" "http://127.0.0.1:3000/api/platform/apply?history=1&target=platform" | cut -c1-120; echo
echo "== watcher-check-raw via ledger_cli (scope guard)"; printf 'diff --git a/token_mint.py b/token_mint.py\n--- a/token_mint.py\n+++ b/token_mint.py\n@@ -1,1 +1,2 @@\n #!/usr/bin/env python3\n+# x\n' > /tmp/t.patch
cd ~/.hermes-newteam/watcher && venv/bin/python ledger_cli.py watcher-check-raw /tmp/t.patch | cut -c1-160; echo
echo "== kb search smoke"; curl -s http://127.0.0.1:6343/collections/newplay_code | jq -c '{status:.result.status, points:.result.points_count}'
echo "== claude cli auth"; claude --version 2>/dev/null | head -1; [ -n "$ANTHROPIC_API_KEY" ] && echo "ANTHROPIC_API_KEY set" || echo "no anthropic key yet (team key pending)"
echo "== env keys empty?"; grep -E "^(OPENAI_API_KEY|ANTHROPIC_API_KEY)=" ~/.hermes-newteam/watcher/.env | sed 's/=.\+/=<set>/; s/=$/=<empty>/'
