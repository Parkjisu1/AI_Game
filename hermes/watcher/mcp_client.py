"""
MCP Client — Hermes(Mother) → Unity MCP(빌드컴) 호출 모듈.

연결: SSH 터널 경유 (`projecthub-mcp-tunnel.service` systemd user 유닛이 :7900 포워딩).
인증: Bearer 토큰 (`PROJECTHUB_MCP_TOKEN` env).

장애 대응:
  - 터널 미가동 → ConnectionError → 호출자에게 그대로 (하위 워크플로우는 silent skip 결정)
  - 401 unauthorized → AuthError
  - 5xx / 4xx (auth 외) → ToolError (code + message + details)

사용:
    from mcp_client import McpClient
    cli = McpClient()
    res = cli.call("inspect.scene.list")
    print(res)  # {"build_settings": [...], ...}
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import urllib.request
import urllib.error

log = logging.getLogger("mcp-client")


class McpError(Exception):
    """MCP 호출 실패의 기반 예외."""
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


class McpAuthError(McpError):
    pass


class McpConnectionError(McpError):
    pass


class McpToolError(McpError):
    pass


class McpClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or os.environ.get("PROJECTHUB_MCP_URL", "http://localhost:7900")).rstrip("/")
        self.token = token or os.environ.get("PROJECTHUB_MCP_TOKEN", "")
        self.timeout = timeout

    def call(self, tool: str, params: dict | None = None) -> dict:
        """
        MCP 툴 호출. 성공 시 응답의 `data` 또는 전체 JSON 반환.

        Raises:
            McpAuthError(401), McpConnectionError(연결 실패), McpToolError(그 외 실패).
        """
        url = f"{self.base_url}/{tool}"
        body = json.dumps(params or {}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                status = resp.status
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            status = e.code
        except urllib.error.URLError as e:
            raise McpConnectionError("mcp.connection_failed", str(e.reason)) from e
        except TimeoutError as e:
            raise McpConnectionError("mcp.timeout", f"timed out after {self.timeout}s") from e

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise McpToolError("mcp.bad_response", f"non-JSON response (status {status})", {"body": raw[:500]}) from e

        if status == 401:
            err = payload.get("error", {}) if isinstance(payload, dict) else {}
            raise McpAuthError(err.get("code", "mcp.unauthorized"), err.get("message", "Unauthorized"), err)

        if status >= 400 or (isinstance(payload, dict) and payload.get("ok") is False):
            err = (payload.get("error") if isinstance(payload, dict) else None) or {"code": "mcp.error", "message": f"status {status}"}
            raise McpToolError(err.get("code", "mcp.error"), err.get("message", ""), err)

        # 성공 — `data` 필드가 있으면 그것만, 없으면 전체
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # 편의 래퍼 — 자주 쓸 툴들
    def health(self) -> dict:
        url = f"{self.base_url}/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def ping(self) -> dict:
        return self.call("ping")

    def inspect_scene_list(self) -> dict:
        return self.call("inspect.scene.list")


# ── 셀프 테스트 ──
if __name__ == "__main__":
    import sys
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        load_dotenv(Path.home() / ".hermes" / "watcher" / ".env")
    except ImportError:
        pass

    cli = McpClient()
    print("base_url:", cli.base_url)
    print("token:", "<set>" if cli.token else "<empty>")

    print("\n[health]")
    try:
        print(" ", cli.health())
    except Exception as e:
        print("  ERR:", e)

    print("\n[ping]")
    try:
        print(" ", cli.ping())
    except McpError as e:
        print("  MCP ERR:", e.code, e.message)

    print("\n[inspect.scene.list]")
    try:
        res = cli.inspect_scene_list()
        print(" ", json.dumps(res, indent=2, ensure_ascii=False))
    except McpError as e:
        print("  MCP ERR:", e.code, e.message)
