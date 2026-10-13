import { NextRequest, NextResponse } from "next/server";
import { mkdir, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import { ObjectId } from "mongodb";
import { getDb } from "@/lib/mongodb";
import { assetDataRoot, assetUser } from "@/lib/asset-studio";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const MAX_BYTES = 100 * 1024 * 1024;
const allowed = new Set([".blend", ".glb", ".fbx", ".obj", ".png", ".jpg", ".jpeg", ".webp"]);

export async function GET(req: NextRequest) {
  if (!await assetUser(req)) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  const db = await getDb();
  const [jobs, worker] = await Promise.all([
    db.collection("projecthub_3d_jobs").find({}).sort({ created_at: -1 }).limit(30).toArray(),
    db.collection("projecthub_3d_worker").findOne({ _id: "mother" as never }),
  ]);
  const lastSeen = worker?.last_seen ? new Date(worker.last_seen).getTime() : 0;
  return NextResponse.json({ jobs, worker: { online: Date.now() - lastSeen < 60000, last_seen: worker?.last_seen || null } });
}

export async function POST(req: NextRequest) {
  const email = await assetUser(req);
  if (!email) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  const origin = req.headers.get("origin");
  if (origin && ![req.headers.get("host"), req.headers.get("x-forwarded-host")].includes(new URL(origin).host)) {
    return NextResponse.json({ error: "요청 출처가 일치하지 않습니다." }, { status: 403 });
  }
  if (Number(req.headers.get("content-length")) > MAX_BYTES + 65536) return NextResponse.json({ error: "파일은 100MB 이하로 올려 주세요." }, { status: 413 });
  let form: FormData;
  try { form = await req.formData(); } catch { return NextResponse.json({ error: "업로드 형식 오류" }, { status: 400 }); }
  const title = String(form.get("title") || "새 3D 모델").trim().slice(0, 120);
  const brief = String(form.get("brief") || "").trim().slice(0, 6000);
  const profile = form.get("profile") === "mobile" ? "mobile" : "pc";
  const demo = form.get("mode") === "demo";
  const file = form.get("file");
  if (!demo && (!(file instanceof File) || !file.size)) return NextResponse.json({ error: "모델 또는 레퍼런스 파일을 선택해 주세요." }, { status: 400 });
  const extension = file instanceof File ? path.extname(file.name).toLowerCase() : "";
  if (!demo && (!allowed.has(extension) || (file as File).size > MAX_BYTES)) return NextResponse.json({ error: "지원하지 않는 형식이거나 100MB를 초과합니다." }, { status: 400 });
  const reference = [".png", ".jpg", ".jpeg", ".webp"].includes(extension);
  const back = form.get("back");
  const backExtension = back instanceof File && back.size ? path.extname(back.name).toLowerCase() : "";
  if (backExtension && (!reference || ![".png", ".jpg", ".jpeg", ".webp"].includes(backExtension) ||
    (back as File).size + (file as File).size > MAX_BYTES)) {
    return NextResponse.json({ error: "후면은 이미지 형식이어야 하며 파일 합계는 100MB 이하입니다." }, { status: 400 });
  }
  const generate = reference && !!backExtension && !demo;
  const db = await getDb();
  const jobs = db.collection("projecthub_3d_jobs");
  if (await jobs.countDocuments({ created_by: email, status: { $in: ["queued", "running"] } }) >= 5) {
    return NextResponse.json({ error: "대기·실행 작업이 5개입니다. 완료 후 다시 요청해 주세요." }, { status: 429 });
  }
  const id = new ObjectId();
  const dir = path.join(assetDataRoot, id.toHexString());
  try {
    await mkdir(dir, { recursive: true });
    if (!demo && file instanceof File) await writeFile(path.join(dir, `input${extension}`), Buffer.from(await file.arrayBuffer()), { flag: "wx" });
    if (generate && back instanceof File) await writeFile(path.join(dir, `back${backExtension}`), Buffer.from(await back.arrayBuffer()), { flag: "wx" });
    const job = { _id: id, title: demo ? "Wind Ronin · 제작 흐름 검증 예제" : title, brief, profile,
      mode: demo ? "demo" : generate ? "image" : reference ? "reference" : "import", extension, back_extension: backExtension || null,
      status: reference && !demo && !generate ? "needs_modeling" : "queued", stage: reference && !demo && !generate ? "reference" : "queued",
      original_name: file instanceof File ? file.name.slice(0, 200) : null,
      created_by: email, created_at: new Date(), updated_at: new Date(), artifacts_ready: false };
    await jobs.insertOne(job);
    return NextResponse.json({ id: id.toHexString(), status: job.status }, { status: 201 });
  } catch (err) {
    // This directory is a newly generated ObjectId, never a user-selected path.
    await rm(dir, { recursive: true, force: true });
    console.error("asset-studio submission failed", err instanceof Error ? err.name : "error");
    return NextResponse.json({ error: "작업 저장에 실패했습니다. 다시 시도해 주세요." }, { status: 500 });
  }
}
