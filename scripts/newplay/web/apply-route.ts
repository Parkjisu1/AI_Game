import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import { createHash } from "crypto";
import { promises as fsp } from "fs";
import path from "path";
import os from "os";
import { auth, isAdminEmail } from "@/auth";
import { getDb } from "@/lib/mongodb";

/**
 * /api/platform/apply — 에이전트 제안(또는 직접 올린 패치)을 적용한다.
 *
 * 왜 API 로 여는가:
 *   팀에게 SSH 를 주면 **ProjectHub(게임팀)까지 열린다** — 같은 서버, 같은 계정이기 때문이다.
 *   그래서 SSH 대신 이 경로 하나만 연다. 범위 검사는 서버 쪽(change_ledger / platform_deploy)에
 *   있고, 그 검사를 통과하지 못하면 아무것도 적용되지 않는다. 약속이 아니라 코드로 강제된다.
 *
 * 대상 (target):
 *   webstore  — 제품 코드. 허용 사용자 전원. 적용 = 커밋(서비스 무관)
 *   platform  — 플랫폼 자신. **관리자만.** 적용 = 빌드+재기동이라 실패하면
 *               되돌리기 화면 자체가 죽는다. 자동 복구가 두 겹 있지만,
 *               최악의 경우 SSH 복구를 감당할 사람만 눌러야 한다.
 *   watcher   — AI 워처(~/.hermes-newteam/watcher). **관리자만.** AI 의 역할 분배·라우팅·
 *               실행·검수 로직이 여기 있다. 적용 = py_compile+import 검사 → 재기동 →
 *               생존 확인. 웹서버 자신을 재시작하지 않으므로 **동기 응답**이 가능하다 —
 *               platform 과 달리 결과가 응답에 바로 실려 온다(폴링 불필요).
 *
 * 인증:
 *   ① 구글 로그인 세션 (브라우저)
 *   ② Bearer 토큰 (PowerShell 등 CLI) — token_mint.py 로 발급, DB 엔 sha256 해시만.
 *   토큰은 이메일로 풀리고, 권한은 **그 이메일의 등급**을 따른다. 토큰 자체엔 등급이 없다.
 *
 * 동작:
 *   GET  ?taskId=…                     → 작업의 수정안 적용 가능 여부 (변경 없음)
 *   GET  ?history=1                    → 적용 이력
 *   GET  ?bundle=1&target=platform|watcher → 소스 git bundle (관리자; SSH 없이 clone 하기 위한 것)
 *   POST {taskId}                      → 작업의 수정안 적용
 *   POST {patch, title, check?}        → 패치 직접 업로드 (platform; CLI 용). check=true 면 판정만
 *   POST {revert}                      → 되돌리기
 */

const RUNNER = path.join(os.homedir(), ".hermes-newteam", "watcher", "ledger_cli.py");
const PYTHON = path.join(os.homedir(), ".hermes-newteam", "watcher", "venv", "bin", "python");
const PLATFORM_TREE = path.join(os.homedir(), "projecthub-newteam");
const WATCHER_TREE = path.join(os.homedir(), ".hermes-newteam", "watcher");

type Target = "webstore" | "platform" | "watcher";
/** 관리자 전용 대상 — 적용이 곧 서비스 재기동이다. */
const PRIVILEGED: readonly Target[] = ["platform", "watcher"];
function parseTarget(v: unknown): Target {
  return v === "platform" || v === "watcher" ? v : "webstore";
}
function treeOf(t: Target): string {
  return t === "watcher" ? WATCHER_TREE : PLATFORM_TREE;
}

function run(args: string[], timeoutMs = 180_000): Promise<{ code: number; out: string; err: string }> {
  return new Promise((resolve) => {
    execFile(
      PYTHON,
      [RUNNER, ...args],
      { timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024, cwd: path.dirname(RUNNER) },
      (e, stdout, stderr) => {
        resolve({
          code: e ? ((e as NodeJS.ErrnoException & { code?: number }).code ?? 1) : 0,
          out: String(stdout || ""),
          err: String(stderr || ""),
        });
      },
    );
  });
}

/**
 * 요청자 이메일. 세션이 우선이고, 없으면 Bearer 토큰을 해시로 풀어 찾는다.
 * 토큰 평문은 서버 어디에도 저장돼 있지 않다 — 비교는 항상 해시로 한다.
 */
async function actorEmail(req: NextRequest): Promise<string | null> {
  const session = await auth();
  const fromSession = String(session?.user?.email || "").toLowerCase();
  if (fromSession) return fromSession;

  const m = (req.headers.get("authorization") || "").match(/^Bearer\s+(\S+)$/i);
  if (!m) return null;
  const hash = createHash("sha256").update(m[1]).digest("hex");
  try {
    const db = await getDb();
    const t = await db.collection("newplay_api_tokens").findOne({ hash, revoked: { $ne: true } });
    if (t?.email) return String(t.email).toLowerCase();
  } catch {
    return null;
  }
  return null;
}

function prefixFor(target: Target): string {
  return target === "webstore" ? "" : `${target}-`;
}

function parseJson(r: { out: string; err: string }, fallbackMsg: string) {
  try {
    return NextResponse.json(JSON.parse(r.out || "{}"));
  } catch {
    return NextResponse.json({ error: fallbackMsg, detail: (r.err || r.out).slice(0, 500) }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  const actor = await actorEmail(req);
  if (!actor) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const target = parseTarget(url.searchParams.get("target"));
  if (PRIVILEGED.includes(target) && !isAdminEmail(actor)) {
    return NextResponse.json({ error: "플랫폼·AI 워처 변경은 관리자만 가능합니다" }, { status: 403 });
  }
  const pfx = prefixFor(target);

  // 소스 번들 — SSH 없이 로컬에 clone 할 수 있게 git bundle 을 준다.
  // tarball 이 아니라 bundle 인 이유: 이력까지 가야 로컬 diff 기준(HEAD)이 서버와 맞는다.
  if (url.searchParams.get("bundle") === "1" && PRIVILEGED.includes(target)) {
    const tmp = path.join(os.tmpdir(), `newplay-hub-${Date.now()}.bundle`);
    const mk = (refs: string[]) =>
      new Promise<{ code: number; err: string }>((resolve) => {
        execFile("git", ["bundle", "create", tmp, ...refs],
          { cwd: treeOf(target), timeout: 120_000 },
          (e, _o, stderr) => resolve({ code: e ? 1 : 0, err: String(stderr || "") }));
      });
    // 브랜치 이름을 단정하지 않는다 — HEAD 만으로도 clone 은 된다.
    let r = await mk(["HEAD", "--all"]);
    if (r.code !== 0) r = await mk(["HEAD"]);
    if (r.code !== 0) {
      return NextResponse.json({ error: "bundle 생성 실패", detail: r.err.slice(0, 300) }, { status: 500 });
    }
    try {
      const buf = await fsp.readFile(tmp);
      return new NextResponse(new Uint8Array(buf), {
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Disposition": `attachment; filename="newplay-hub-${target}.bundle"`,
        },
      });
    } finally {
      fsp.unlink(tmp).catch(() => {});
    }
  }

  if (url.searchParams.get("history") === "1") {
    return parseJson(await run([`${pfx}history`]), "history 실패");
  }

  const taskId = url.searchParams.get("taskId") || "";
  if (!/^[a-f0-9]{24}$/i.test(taskId)) {
    return NextResponse.json({ error: "invalid taskId" }, { status: 400 });
  }
  return parseJson(await run([`${pfx}check`, taskId]), "판정 실패");
}

export async function POST(req: NextRequest) {
  const actor = await actorEmail(req);
  if (!actor) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const target = parseTarget(body.target);
  if (PRIVILEGED.includes(target) && !isAdminEmail(actor)) {
    return NextResponse.json({ error: "플랫폼·AI 워처 변경은 관리자만 가능합니다" }, { status: 403 });
  }
  const pfx = prefixFor(target);

  // 플랫폼 배포·되돌리기는 **동기 응답이 원리적으로 불가능하다** —
  // 배포가 이 응답을 만들고 있는 서버 자신을 재시작하기 때문이다.
  // 실측: 동기로 돌렸더니 재시작이 배포 자식 프로세스까지 죽여 커밋은 남고
  // 원장 기록·응답은 유실됐다. 그래서 systemd-run 으로 웹서버 cgroup **밖에서**
  // 돌리고 즉시 수락 응답만 준다. 결과는 원장(?history=1)을 폴링해 확인한다.
  function detach(args: string[]): Promise<{ ok: boolean; err: string }> {
    const unit = `nph-deploy-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return new Promise((resolve) => {
      execFile("systemd-run", ["--user", "--collect", `--unit=${unit}`, PYTHON, RUNNER, ...args],
        { timeout: 30_000 },
        (e, _o, stderr) => resolve({ ok: !e, err: String(stderr || "") }));
    });
  }

  if (body.revert) {
    const commit = String(body.revert);
    if (!/^[0-9a-f]{7,40}$/.test(commit)) {
      return NextResponse.json({ error: "invalid commit" }, { status: 400 });
    }
    if (target === "platform") {
      const d = await detach(["platform-rollback", commit, actor]);
      if (!d.ok) return NextResponse.json({ error: "작업 시작 실패", detail: d.err.slice(0, 300) }, { status: 500 });
      return NextResponse.json({ ok: true, accepted: true,
        note: "되돌리기가 시작됐습니다. 재빌드+재기동 동안 접속이 잠시 끊깁니다 — ?history=1 로 결과를 확인하세요." });
    }
    if (target === "watcher") {
      // 워처는 웹서버를 건드리지 않으므로 동기로 돌리고 결과를 바로 준다.
      return parseJson(await run(["watcher-rollback", commit, actor], 300_000), "되돌리기 실패");
    }
    return parseJson(await run(["revert", commit, actor], 180_000), "되돌리기 실패");
  }

  // 패치 직접 업로드 (CLI 경로). 에이전트를 거치지 않은 사람 손 패치도 같은
  // 범위 검사·자동 복구를 통과한다 — 경로가 하나라야 보장도 하나로 유지된다.
  if (typeof body.patch === "string" && body.patch.trim()) {
    if (!PRIVILEGED.includes(target)) {
      return NextResponse.json({ error: "직접 패치는 platform·watcher 대상만 지원합니다" }, { status: 400 });
    }
    if (body.patch.length > 2_000_000) {
      return NextResponse.json({ error: "패치가 너무 큽니다(2MB 제한)" }, { status: 413 });
    }
    const tmp = path.join(os.tmpdir(), `nph-${Date.now()}-${Math.random().toString(36).slice(2)}.patch`);
    await fsp.writeFile(tmp, body.patch, "utf8");
    if (body.check) {
      try {
        return parseJson(await run([`${pfx}check-raw`, tmp]), "판정 실패");
      } finally {
        fsp.unlink(tmp).catch(() => {});
      }
    }
    const title = String(body.title || "직접 업로드 패치").slice(0, 120);
    if (target === "watcher") {
      // 워처 배포는 동기 — 컴파일·import 검사·재기동·생존 확인(최대 ~2분)까지 기다려 결과를 준다.
      try {
        return parseJson(await run(["watcher-deploy-raw", tmp, title, actor], 400_000), "배포 실패");
      } finally {
        fsp.unlink(tmp).catch(() => {});
      }
    }
    // 플랫폼 배포는 분리 실행 — 임시 패치 파일은 CLI 가 읽은 뒤 스스로 지운다
    // (이 라우트는 재시작에 죽을 수 있어 청소를 맡길 수 없다).
    const d = await detach(["platform-deploy-raw", tmp, title, actor]);
    if (!d.ok) {
      fsp.unlink(tmp).catch(() => {});
      return NextResponse.json({ error: "작업 시작 실패", detail: d.err.slice(0, 300) }, { status: 500 });
    }
    return NextResponse.json({ ok: true, accepted: true, title,
      note: "배포가 시작됐습니다. 빌드+재기동 동안 접속이 잠시 끊깁니다 — ?history=1 로 결과를 확인하세요." });
  }

  const taskId = String(body.taskId || "");
  if (!/^[a-f0-9]{24}$/i.test(taskId)) {
    return NextResponse.json({ error: "invalid taskId" }, { status: 400 });
  }
  if (target === "platform") {
    // 태스크 경로도 같은 이유로 분리 실행이다 — 자기 재시작이 응답을 끊는다.
    const d = await detach(["platform-deploy", taskId, actor]);
    if (!d.ok) return NextResponse.json({ error: "작업 시작 실패", detail: d.err.slice(0, 300) }, { status: 500 });
    return NextResponse.json({ ok: true, accepted: true,
      note: "배포가 시작됐습니다. ?history=1 로 결과를 확인하세요." });
  }
  if (target === "watcher") {
    return parseJson(await run(["watcher-deploy", taskId, actor], 400_000), "배포 실패");
  }
  return parseJson(await run(["apply", taskId, actor], 180_000), "적용 실패");
}
