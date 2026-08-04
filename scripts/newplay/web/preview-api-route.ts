import { NextRequest, NextResponse } from "next/server";
import { auth, authDisabled, isAdminEmail } from "@/auth";
import { getDb } from "@/lib/mongodb";
import { promises as fs } from "fs";
import { execFile } from "child_process";
import path from "path";
import os from "os";

/**
 * 수정안 미리보기 빌드.
 *
 * GET  — 현재 미리보기 상태(어떤 패치가 적용돼 있는지, 언제 빌드됐는지)
 * POST — { patch: "<unified diff>" } 또는 { reset: true } 로 재빌드
 *
 * 라이브(newplay.store)에도 QA 에도 아무 영향이 없다. 빌드 결과는 이 서버의
 * ~/newplay-preview/serve 에만 남고 /preview 로만 보인다.
 * 소스 트리는 빌드 후 항상 git checkout 으로 되돌린다(스크립트가 담당).
 */
export const dynamic = "force-dynamic";

const HOME = process.env.HOME || "/home/aimed";
const BASE = path.join(HOME, "newplay-preview");
const SCRIPT = path.join(BASE, "preview-build.sh");
const STATE = path.join(BASE, "state.json");

async function readState() {
  try {
    return JSON.parse(await fs.readFile(STATE, "utf8"));
  } catch {
    return null;
  }
}

export async function GET() {
  if (!authDisabled) {
    const s = await auth();
    if (!s?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return NextResponse.json({ state: await readState() });
}

export async function POST(req: NextRequest) {
  let email = "";
  if (!authDisabled) {
    const s = await auth();
    email = String(s?.user?.email || "");
    if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    // 빌드는 서버에서 명령을 실행한다 — 관리자만.
    if (!isAdminEmail(email)) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }

  let patchFile = "";
  if (!body.reset) {
    const patch = String(body.patch || "");
    if (!patch.trim()) return NextResponse.json({ error: "patch 가 비었습니다" }, { status: 400 });
    if (patch.length > 2_000_000) return NextResponse.json({ error: "patch 가 너무 큽니다" }, { status: 400 });
    // 파일명에 사용자 입력을 쓰지 않는다.
    patchFile = path.join(os.tmpdir(), `newplay-preview-${Date.now()}.patch`);
    await fs.writeFile(patchFile, patch, "utf8");
  }

  const out = await new Promise<{ ok: boolean; stdout: string; stderr: string }>((resolve) => {
    execFile(
      "/usr/bin/env",
      ["bash", SCRIPT, ...(patchFile ? [patchFile] : [])],
      { timeout: 15 * 60 * 1000, maxBuffer: 4 * 1024 * 1024 },
      (err, stdout, stderr) => resolve({ ok: !err, stdout: String(stdout || ""), stderr: String(stderr || "") }),
    );
  });

  if (patchFile) await fs.rm(patchFile, { force: true }).catch(() => {});

  const state = await readState();

  // 누가 무엇을 미리보기로 올렸는지 남긴다 — 화면이 갑자기 바뀌면 이유를 알 수 있어야 한다.
  try {
    const db = await getDb();
    await db.collection("newplay_preview_log").insertOne({
      email, ok: out.ok, reset: !!body.reset,
      patchBytes: body.reset ? 0 : String(body.patch || "").length,
      taskId: body.taskId ? String(body.taskId) : null,
      stdout: out.stdout.slice(-2000), stderr: out.stderr.slice(-2000),
      state, created_at: new Date(),
    });
  } catch { /* 로그 실패가 빌드를 막지는 않는다 */ }

  return NextResponse.json({
    ok: out.ok,
    state,
    log: (out.stdout + "\n" + out.stderr).trim().slice(-4000),
  }, { status: out.ok ? 200 : 500 });
}
