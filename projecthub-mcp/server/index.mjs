// ProjectHub Unity MCP — Tier 1 Server (Node.js, no external deps)
//
// 외부:7900 ──HTTP──> 이 서버 ──HTTP──> Unity Bridge :7901 ──> Unity Editor API
//
// 1차 슬라이스: inspect.scene.list 단일 forward + ping. 검증 후 라우터 + ICS write-through 추가.

import http from 'node:http';
import { setTimeout as wait } from 'node:timers/promises';

const MCP_PORT = parseInt(process.env.PROJECTHUB_MCP_PORT || '7900', 10);
const UNITY_BRIDGE = process.env.UNITY_BRIDGE_URL || 'http://localhost:7901';
const AUTH_TOKEN = process.env.PROJECTHUB_MCP_TOKEN || '';
const REQUEST_TIMEOUT_MS = 30_000;

// ── Forward to Unity bridge ──
async function callUnity(toolName, body, timeoutMs = REQUEST_TIMEOUT_MS) {
    const url = new URL(toolName, UNITY_BRIDGE + '/');
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: typeof body === 'string' ? body : JSON.stringify(body ?? {}),
            signal: ctrl.signal,
        });
        const text = await res.text();
        return { status: res.status, text };
    } catch (e) {
        if (e.name === 'AbortError') return { status: 504, text: JSON.stringify({ ok: false, error: { code: 'mcp.timeout', message: `Unity bridge did not respond in ${timeoutMs}ms` } }) };
        return { status: 502, text: JSON.stringify({ ok: false, error: { code: 'mcp.bridge_disconnected', message: e.message } }) };
    } finally {
        clearTimeout(t);
    }
}

// ── HTTP server ──
const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const path = url.pathname.replace(/^\/+/, '');

    // Auth
    if (AUTH_TOKEN) {
        const got = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
        if (got !== AUTH_TOKEN) {
            res.writeHead(401, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: false, error: { code: 'mcp.unauthorized' } }));
            return;
        }
    }

    if (req.method !== 'POST' && req.method !== 'GET') {
        res.writeHead(405); res.end(); return;
    }

    // Read body
    let body = '';
    for await (const chunk of req) body += chunk;

    // ── Routes ──
    if (path === 'health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, server: 'projecthub-mcp', version: '0.1.0', unity_bridge: UNITY_BRIDGE }));
        return;
    }

    // 모든 inspect.* / modify.* / validate.* / tx.* 요청은 Unity 브릿지로 forward
    // (1차 슬라이스: forward만, ICS write-through는 다음 단계)
    if (/^(inspect|modify|validate|tx|ping)\b/.test(path)) {
        const start = Date.now();
        const upstream = await callUnity(path, body);
        res.writeHead(upstream.status, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(upstream.text);
        const dt = Date.now() - start;
        console.log(`[mcp] ${req.method} ${path} → ${upstream.status} (${dt}ms)`);
        return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: false, error: { code: 'mcp.unknown_path', message: path } }));
});

server.listen(MCP_PORT, () => {
    console.log(`[mcp] listening on :${MCP_PORT} → forwarding to ${UNITY_BRIDGE}`);
    console.log(`[mcp] auth: ${AUTH_TOKEN ? 'enabled' : 'DISABLED (PROJECTHUB_MCP_TOKEN env not set)'}`);
});

// Graceful shutdown
process.on('SIGINT', () => { console.log('\n[mcp] shutting down'); server.close(() => process.exit(0)); });
process.on('SIGTERM', () => { server.close(() => process.exit(0)); });
