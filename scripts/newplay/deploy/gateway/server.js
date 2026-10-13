/**
 * NewPlay gateway — 브라우저 웹소켓 ↔ 사람의 workbench 컨테이너 PTY.
 *
 * 흐름: 웹이 발급한 티켓(HMAC, 5분) → 검증 → 사람의 컨테이너(wb-<user>) 준비 → 프로젝트 worktree 준비
 *      → `docker exec -it … tmux new -A -s <project>` 를 PTY 로 붙여 양방향 중계.
 * 원칙: 토큰은 /data/tokens/<email>.token 을 읽어 그 사람 컨테이너의 env 로만 넣는다.
 *      경계: 컨테이너·홈·토큰은 사람마다 분리된다. 저장소(/data/git)는 git worktree 를 만들어야 해서 쓰기로 공유된다
 *      — 같은 팀 안에서 서로의 작업 폴더를 고칠 수 있다는 뜻이다(설계서 §11).
 *      마지막 클라이언트가 끊긴 뒤 IDLE_MIN 분이 지나면 컨테이너를 정지한다(tmux 세션은 컨테이너 안에 남지 않으므로
 *      정지 = 세션 종료 → 세션 종료 이벤트를 Mongo work_sessions 에 기록해 learner 가 읽는다).
 */
const http = require("http");
const crypto = require("crypto");
const { execFileSync, execFile } = require("child_process");
const fs = require("fs");
const path = require("path");
const WebSocket = require("ws");
const pty = require("node-pty");
const { MongoClient } = require("mongodb");

const PORT = +(process.env.GATEWAY_PORT || 3001);
const SECRET = process.env.HERMES_INTERNAL_API_KEY || "";
const TOKEN_DIR = process.env.NEWPLAY_CLAUDE_TOKEN_DIR || "/data/tokens";
const DATA_ROOT_HOST = process.env.DATA_ROOT_HOST || "/data/newplay";   // 호스트 경로 (docker run -v 에 필요)
const DATA_ROOT_LOCAL = process.env.DATA_ROOT_LOCAL || "/data";         // 게이트웨이 컨테이너 안에서 같은 곳을 가리키는 경로
const WB_USER = process.env.WORKBENCH_USER || "1000:1000";              // 작업대 컨테이너 uid:gid (호스트 사용자와 같아야 한다)
const WB_IMAGE = process.env.WORKBENCH_IMAGE || "newplay/workbench";
const IDLE_MIN = +(process.env.WORKBENCH_IDLE_MIN || 10);
const NET = process.env.COMPOSE_NETWORK || "newplay_workbench";
const MONGO = process.env.MONGODB_URI || "mongodb://mongo:27017/newteam?directConnection=true";

// stderr 까지 잡아 둔다(기본값은 부모 로그로 새어 나가 "없는 컨테이너" 같은 잡음이 쌓인다).
const sh = (args, opts = {}) => execFileSync(args[0], args.slice(1), { encoding: "utf8", timeout: 120000, stdio: ["ignore", "pipe", "pipe"], ...opts }).trim();
// 사람 식별자: 주소 전체(도메인 포함)를 쓴다. 로컬부만 쓰면 kim@a.com 과 kim@b.com 이 같은 컨테이너·홈·토큰을 공유한다.
const safeUser = (email) => {
  const e = String(email || "").toLowerCase();
  const slug = e.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "anon";
  return slug.slice(0, 27) + "-" + crypto.createHash("sha256").update(e).digest("hex").slice(0, 12);
};

// ── 티켓 검증 (web 이 발급: base64(json).sig) — 서명·만료·재사용 방지
const usedTickets = new Map();   // sig → 만료시각. 같은 티켓으로 두 번 붙는 것을 막는다.
function verifyTicket(t) {
  if (!SECRET || !t) return null;
  const [b64, sig] = String(t).split(".");
  if (!b64 || !sig) return null;
  const want = crypto.createHmac("sha256", SECRET).update(b64).digest("hex");
  if (want.length !== sig.length || !crypto.timingSafeEqual(Buffer.from(want), Buffer.from(sig))) return null;
  let j;
  try { j = JSON.parse(Buffer.from(b64, "base64url").toString("utf8")); } catch { return null; }
  if (!j || !j.email || !j.project || Date.now() > (j.exp || 0)) return null;
  if (!/^[a-z0-9_-]{1,60}$/i.test(String(j.project))) return null;
  const now = Date.now();
  for (const [k, exp] of usedTickets) if (exp < now) usedTickets.delete(k);
  if (usedTickets.has(sig)) return null;
  usedTickets.set(sig, j.exp);
  return j;
}

// ── 컨테이너·worktree 준비
function ensureContainer(email) {
  const name = `wb-${safeUser(email)}`;
  const tokenFile = path.join(TOKEN_DIR, `${email.toLowerCase()}.token`);
  const token = fs.existsSync(tokenFile) ? fs.readFileSync(tokenFile, "utf8").trim() : "";
  const tokenHash = crypto.createHash("sha256").update(token).digest("hex");
  let state = "";
  let info;
  try { info = JSON.parse(sh(["docker", "inspect", name]))[0]; } catch { state = "none"; }
  if (info) {
    const labels = info.Config?.Labels || {};
    const networks = Object.keys(info.NetworkSettings?.Networks || {});
    if (labels["newplay.owner"] !== email.toLowerCase()
        || labels["newplay.token-sha256"] !== tokenHash
        || networks.length !== 1 || networks[0] !== NET) {
      // 토큰 교체·삭제 및 네트워크 변경은 재접속 시 반영한다. 영구 홈·작업 폴더는 보존.
      sh(["docker", "rm", "-f", name]);
      state = "none";
    } else state = info.State.Status;
  }
  if (state === "none") {
    // 개인 홈은 게이트웨이(=호스트 사용자)가 미리 만든다. docker 가 만들면 root 소유가 되어 컨테이너가 못 쓴다.
    try { fs.mkdirSync(path.join(DATA_ROOT_LOCAL, "home", safeUser(email)), { recursive: true }); } catch { /* 이미 있음 */ }
    const args = ["docker", "run", "-d", "--name", name, "--network", NET, "--restart", "no",
      "--label", `newplay.owner=${email.toLowerCase()}`, "--label", `newplay.token-sha256=${tokenHash}`,
      "--user", WB_USER,                                            // 공유 저장소를 root 소유로 만들지 않기 위해 uid 를 맞춘다
      "--memory", process.env.WORKBENCH_MEM || "6g", "--cpus", process.env.WORKBENCH_CPUS || "2",
      "-v", `${DATA_ROOT_HOST}/git:/data/git`,                       // worktree 는 여기 안에 (rw)
      "-v", `${DATA_ROOT_HOST}/home/${safeUser(email)}:/home/app`,   // 개인 홈: ~/.claude(전사·설정) 영구 보관
      "-e", `NEWPLAY_USER=${email}`,
      ...(token ? ["-e", `CLAUDE_CODE_OAUTH_TOKEN=${token}`] : []),
      WB_IMAGE, "sleep", "infinity"];
    sh(args);
  } else if (state !== "running") {
    sh(["docker", "start", name]);
  }
  return { name, hasToken: !!token };
}

// 작업 폴더는 사람×프로젝트마다 하나로 고정한다. 접속할 때마다 새로 만들면 tmux 는 옛 폴더에 붙어 있는데
// 빈 작업 폴더와 브랜치만 쌓인다(실측). 같은 사람이 다시 들어오면 하던 자리에서 이어서 일한다.
function ensureWorktree(container, email, project) {
  const user = safeUser(email);
  const origin = `/data/git/${project}/origin`;
  const wt = `/data/git/${project}/wt/u-${user}`;
  const branch = `me/${user}/${project}`;
  const script = `set -e; test -d ${origin}/.git || { echo "프로젝트 ${project} 의 원본이 없습니다"; exit 2; }
    if [ ! -e ${wt}/.git ]; then
      git -C ${origin} worktree prune || true
      git -C ${origin} worktree add -q -b ${branch} ${wt} $(git -C ${origin} symbolic-ref --short HEAD 2>/dev/null || echo main) 2>/dev/null \
        || git -C ${origin} worktree add -q ${wt} ${branch}
    fi
    echo ${wt}`;
  return { path: sh(["docker", "exec", container, "bash", "-lc", script]), branch };
}

// ── 세션 기록 (learner 가 읽는다)
let mongo;
async function col(name) { mongo = mongo || (await new MongoClient(MONGO).connect()); return mongo.db("newteam").collection(name); }
async function sessionEvent(doc) { try { (await col("work_sessions")).updateOne({ _id: doc._id }, { $set: doc }, { upsert: true }); } catch (e) { console.error("session record fail", e.message); } }

// ── 유휴 정지
const clients = new Map();   // container → Set<ws>
const idleTimers = new Map();
function touchIdle(container, email) {
  clearTimeout(idleTimers.get(container));
  if ((clients.get(container)?.size || 0) > 0) return;
  idleTimers.set(container, setTimeout(async () => {
    if ((clients.get(container)?.size || 0) > 0) return;
    try { sh(["docker", "stop", "-t", "5", container]); } catch {}
    await sessionEvent({ _id: `stop-${container}-${Date.now()}`, email, container, event: "container_stopped", at: new Date().toISOString() });
    console.log(`idle stop ${container}`);
  }, IDLE_MIN * 60 * 1000));
}

// ── 재기동 복구: 게이트웨이가 다시 뜨면 붙어 있는 사람이 하나도 없다.
// ① 열린 채로 남은 세션을 닫아 준다(안 닫으면 learner 가 영원히 처리하지 않는다) ② 살아 있는 작업대에 유휴 타이머를 건다.
async function reconcileOnBoot() {
  try {
    const c = await col("work_sessions");
    const r = await c.updateMany({ mode: "direct", ended_at: { $exists: false } },
      { $set: { ended_at: new Date().toISOString(), ended_reason: "gateway_restart" } });
    if (r.modifiedCount) console.log(`boot: 열린 세션 ${r.modifiedCount}건 닫음`);
  } catch (e) { console.error("boot session reconcile fail", e.message); }
  try {
    const names = sh(["docker", "ps", "--filter", "name=wb-", "--format", "{{.Names}}"]).split("\n").filter(Boolean);
    for (const n of names) touchIdle(n, "");
    if (names.length) console.log(`boot: 작업대 ${names.length}개에 유휴 타이머 재설정`);
  } catch { /* docker 없음 */ }
}

// ── HTTP + WS
const server = http.createServer((req, res) => {
  if (req.url.startsWith("/health")) { res.writeHead(200, { "Content-Type": "application/json" }); return res.end(JSON.stringify({ ok: true, idleMin: IDLE_MIN })); }
  res.writeHead(404); res.end();
});
const wss = new WebSocket.Server({ server, path: "/term" });

wss.on("connection", async (ws, req) => {
  const url = new URL(req.url, "http://x");
  const t = verifyTicket(url.searchParams.get("ticket"));
  if (!t) { ws.send("\r\n[gateway] 티켓이 유효하지 않습니다. 화면을 새로고침하세요.\r\n"); return ws.close(); }
  const email = String(t.email).toLowerCase(), project = String(t.project);
  const sessionId = crypto.randomBytes(6).toString("hex");
  let container;
  try {
    const c = ensureContainer(email); container = c.name;
    ws.send(`\r\n[gateway] ${container} 준비 · Claude 토큰 ${c.hasToken ? "있음" : "없음 — 관리자에게 등록 요청"}\r\n`);
    const w = ensureWorktree(container, email, project);
    ws.send(`[gateway] 작업 폴더 ${w.path} · 브랜치 ${w.branch}\r\n\r\n`);
    await sessionEvent({ _id: sessionId, email, project, mode: "direct", container, branch: w.branch, worktree: w.path, started_at: new Date().toISOString() });
    const term = pty.spawn("docker", ["exec", "-it", "-w", w.path, "-e", `NEWPLAY_SESSION=${sessionId}`, container, "tmux", "new", "-A", "-s", project],
      { name: "xterm-256color", cols: +(url.searchParams.get("cols") || 120), rows: +(url.searchParams.get("rows") || 32), env: process.env });
    if (!clients.has(container)) clients.set(container, new Set());
    clients.get(container).add(ws);
    clearTimeout(idleTimers.get(container));
    ws.isAlive = true;
    ws.on("pong", () => { ws.isAlive = true; });
    term.onData((d) => { if (ws.readyState === WebSocket.OPEN) ws.send(d); });
    term.onExit(() => { try { ws.close(); } catch {} });
    ws.on("message", (m) => {
      const s = m.toString();
      if (s.startsWith("\x1b]resize;")) { const [c, r] = s.slice(9).split(",").map(Number); if (c && r) term.resize(c, r); return; }
      term.write(s);
    });
    ws.on("close", async () => {
      try { term.kill(); } catch {}
      clients.get(container)?.delete(ws);
      await sessionEvent({ _id: sessionId, email, project, ended_at: new Date().toISOString() });
      touchIdle(container, email);
    });
  } catch (e) {
    ws.send(`\r\n[gateway] 세션 준비 실패: ${String(e.message || e).slice(0, 300)}\r\n`);
    ws.close();
  }
});

// 끊긴 것을 모르는 연결(노트북 덮기·와이파이 끊김)은 close 이벤트가 오지 않는다.
// 30초마다 두드려 보고 답이 없으면 끊어 준다 — 안 그러면 작업대가 유휴로 안 들어가고 세션이 열린 채로 남는다.
setInterval(() => {
  for (const ws of wss.clients) {
    if (ws.isAlive === false) { try { ws.terminate(); } catch { /* 이미 죽음 */ } continue; }
    ws.isAlive = false;
    try { ws.ping(); } catch { /* 무시 */ }
  }
}, 30000).unref();

server.listen(PORT, () => {
  console.log(`gateway on :${PORT} image=${WB_IMAGE} idle=${IDLE_MIN}m`);
  reconcileOnBoot();
});
