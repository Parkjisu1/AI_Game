"""ops_server.py — 배포 실행기 HTTP API (컨테이너 런타임용).

웹 컨테이너에는 파이썬·docker 가 없으므로 /api/platform/apply 는 여기로 HTTP 로 넘긴다.
이 서버는 ledger_cli 와 같은 명령을 받아 platform_deploy(runtime=docker)로 실행한다.
  POST /run  {"args": ["platform-check-raw", "/tmp/x.patch"], "patch": "<diff>", "detach": false}
    - patch 가 있으면 임시 파일로 저장해 args 의 "@PATCH" 를 그 경로로 치환
    - detach=true 면 백그라운드 스레드로 돌리고 즉시 {"accepted": true} (플랫폼 배포는 웹을 재기동하므로)
  GET  /health
보안: 컨테이너 네트워크 안에서만 접근(포트 미공개). 웹이 이미 세션/토큰으로 사용자를 검증한 뒤 호출한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CLI = os.path.join(HERE, "ledger_cli.py")


def _run(args: list[str], timeout: int = 1800) -> dict:
    try:
        p = subprocess.run([PY, CLI, *args], cwd=HERE, capture_output=True, text=True, timeout=timeout)
        try:
            return json.loads(p.stdout or "{}")
        except Exception:  # noqa: BLE001
            return {"ok": False, "reason": "출력 파싱 실패", "detail": (p.stderr or p.stdout)[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"timeout {timeout}s"}


class H(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):  # 조용히
        pass

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._json(200, {"ok": True, "runtime": os.environ.get("NEWPLAY_RUNTIME", "systemd")})
        if self.path.startswith("/bundle"):
            # ?target=platform|watcher → git bundle 바이트
            target = "watcher" if "watcher" in self.path else "platform"
            tree = os.environ.get("NEWPLAY_WATCHER_TREE", "/srv/watcher") if target == "watcher" else os.environ.get("NEWPLAY_PLATFORM_TREE", "/srv/web")
            tmp = tempfile.mktemp(suffix=".bundle")
            p = subprocess.run(["git", "bundle", "create", tmp, "--all"], cwd=tree, capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                p = subprocess.run(["git", "bundle", "create", tmp, "HEAD"], cwd=tree, capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                return self._json(500, {"error": "bundle 실패", "detail": p.stderr[:300]})
            data = open(tmp, "rb").read(); os.unlink(tmp)
            self.send_response(200); self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa: BLE001
            return self._json(400, {"error": "bad json"})
        args = [str(a) for a in (body.get("args") or [])]
        if not args:
            return self._json(400, {"error": "args 필요"})
        if isinstance(body.get("patch"), str) and body["patch"]:
            fd, pf = tempfile.mkstemp(prefix="nph-", suffix=".patch"); os.close(fd)
            with open(pf, "w", encoding="utf-8") as f:
                f.write(body["patch"])
            args = [pf if a == "@PATCH" else a for a in args]
        if body.get("detach"):
            threading.Thread(target=_run, args=(args, 1800), daemon=True).start()
            return self._json(200, {"ok": True, "accepted": True})
        return self._json(200, _run(args, int(body.get("timeout") or 600)))


if __name__ == "__main__":
    port = int(os.environ.get("NEWPLAY_OPS_PORT", "8090"))
    print(f"ops server on :{port} runtime={os.environ.get('NEWPLAY_RUNTIME', 'systemd')}", flush=True)
    HTTPServer(("0.0.0.0", port), H).serve_forever()
