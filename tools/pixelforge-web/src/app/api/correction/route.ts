import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { promises as fs } from "fs";
import os from "os";
import path from "path";
import { randomUUID } from "crypto";
import { getDb } from "@/lib/mongodb";
import { snapImageToGridAndPaletteV2 } from "@/lib/snapToGridV2";
import { matrixToFieldMap } from "@/lib/matrixRenderer";
import { parseColorDist } from "@/lib/palette";

export const runtime = "nodejs";
export const maxDuration = 180;

// PixelLab "Pixel Art Correction" — headless Playwright bot 기반.
// Body: { level_number: number, strength?: number (0.0-1.0, default 0.1) }
//
// 흐름:
//   1) Mongo에서 image_base64 로드 → 임시 PNG
//   2) ~/.hermes/watcher/pixellab_correction_bot.py 호출 → corrected PNG
//   3) snap-to-grid V2로 corrected 이미지를 재처리 → field_map / palette 재계산
//   4) Mongo 업데이트:
//      - image_base64 (primary) ← corrected snap 결과
//      - image_base64_pre_correction ← 원본 (한 번만 백업)
//      - field_map / field_map_pipeline / palette_mapping ← 재계산값
//      - alt_meta ← correction history
//      - image_base64_alt ← 제거 ($unset)
//   5) 응답
//
// 결과: 갤러리 기본 이미지(image_base64)와 JSON(field_map) 모두 corrected 기준으로 최신화됨.

const BOT_PY = process.env.PIXELLAB_BOT_PY
  || "/home/aimed/.hermes/watcher/pixellab_correction_bot.py";
const BOT_PYTHON = process.env.PIXELLAB_BOT_PYTHON
  || "/home/aimed/.hermes/watcher/venv/bin/python";
const BOT_AUTH = process.env.PIXELLAB_BOT_AUTH
  || "/home/aimed/.hermes/watcher/pixellab_auth.json";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const level_number = Number(body.level_number);
    let strength = Number(body.strength);
    if (!Number.isFinite(strength)) strength = 0.1;
    strength = Math.max(0, Math.min(1, strength));
    if (!Number.isFinite(level_number) || level_number <= 0) {
      return NextResponse.json({ ok: false, error: "level_number 필수" }, { status: 400 });
    }

    // 1) 원본 이미지 로드
    const db = await getDb();
    const lv = await db.collection("pixelforge_levels").findOne({ level_number });
    if (!lv) return NextResponse.json({ ok: false, error: `level ${level_number} 없음` }, { status: 404 });
    const srcBase64 = (lv.image_base64 as string) || "";
    if (!srcBase64) {
      return NextResponse.json(
        { ok: false, error: "image_base64 없음 — 먼저 PixelLab 생성 필요" },
        { status: 422 },
      );
    }

    // 2) 임시 파일 (in/out)
    const tmpDir = os.tmpdir();
    const uid = randomUUID().slice(0, 8);
    const inPath = path.join(tmpDir, `pfc_${uid}_in.png`);
    const outPath = path.join(tmpDir, `pfc_${uid}_out.png`);
    await fs.writeFile(inPath, Buffer.from(srcBase64, "base64"));

    // 3) bot.py 실행
    const args = [
      BOT_PY,
      "--image", inPath,
      "--strength", String(strength),
      "--auth", BOT_AUTH,
      "--output", outPath,
      "--timeout", "120000",
    ];
    const child = spawn(BOT_PYTHON, args, { stdio: ["ignore", "pipe", "pipe"] });

    let stdoutBuf = "";
    let stderrBuf = "";
    child.stdout.on("data", (d: Buffer) => { stdoutBuf += d.toString("utf-8"); });
    child.stderr.on("data", (d: Buffer) => { stderrBuf += d.toString("utf-8"); });

    const exitCode: number = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        try { child.kill("SIGKILL"); } catch {}
        reject(new Error("bot timeout 150s"));
      }, 150_000);
      child.on("error", (e) => { clearTimeout(timer); reject(e); });
      child.on("close", (code) => { clearTimeout(timer); resolve(code ?? -1); });
    });

    try { await fs.unlink(inPath); } catch {}

    if (exitCode !== 0) {
      try { await fs.unlink(outPath); } catch {}
      return NextResponse.json(
        { ok: false, error: `bot exit ${exitCode}`, stderr: stderrBuf.split("\n").slice(-20).join("\n") },
        { status: 500 },
      );
    }

    // 4) 결과 PNG 읽기
    let outBuf: Buffer;
    try {
      outBuf = await fs.readFile(outPath);
    } catch (e) {
      return NextResponse.json(
        { ok: false, error: `output file missing: ${e instanceof Error ? e.message : e}` },
        { status: 500 },
      );
    }
    try { await fs.unlink(outPath); } catch {}
    const correctedB64 = outBuf.toString("base64");

    // 4.5) ★ Backend 검증 — 봇이 잘못된 이미지를 추출하지 않았는지 확인.
    //      이전 사고(Gallery 누적 항목 추출)의 재발을 막는 다층 안전망.
    const expectedCols = Number(lv.field_columns) || 20;
    const expectedRows = Number(lv.field_rows) || 20;
    let outMeta: { width?: number; height?: number };
    try {
      outMeta = await import("sharp").then((s) => s.default(outBuf).metadata());
    } catch (e) {
      return NextResponse.json(
        { ok: false, error: `output PNG 읽기 실패: ${e instanceof Error ? e.message : e}` },
        { status: 500 },
      );
    }
    const verify = {
      out_width: outMeta.width || 0,
      out_height: outMeta.height || 0,
      expected_width: expectedCols,
      expected_height: expectedRows,
      out_size: outBuf.length,
      identical_to_input: correctedB64 === srcBase64,
    };
    if (verify.out_width !== verify.expected_width || verify.out_height !== verify.expected_height) {
      return NextResponse.json(
        { ok: false, error: `bot returned wrong image dims: ${verify.out_width}x${verify.out_height} (expected ${verify.expected_width}x${verify.expected_height}) — likely Gallery contamination`,
          verify },
        { status: 422 },
      );
    }
    if (verify.identical_to_input) {
      return NextResponse.json(
        { ok: false, error: "bot returned image identical to input — no correction applied", verify },
        { status: 422 },
      );
    }
    if (verify.out_size < 200) {
      return NextResponse.json(
        { ok: false, error: `bot returned suspiciously small image (${verify.out_size}B)`, verify },
        { status: 422 },
      );
    }

    // 5) snap-to-grid V2 — corrected 이미지를 재처리해 field_map 갱신
    const cols = Number(lv.field_columns) || 20;
    const rows = Number(lv.field_rows) || 20;
    const paletteIds = parseColorDist(String(lv.color_distribution || ""));
    const targetColorCount = Number(lv.generated_num_colors) || Number(lv.num_colors) || 0;
    let snapped;
    try {
      snapped = await snapImageToGridAndPaletteV2(correctedB64, {
        cols, rows,
        allowedIds: paletteIds.length > 0 ? paletteIds : undefined,
        targetColorCount: targetColorCount > 0 ? targetColorCount : undefined,
      });
    } catch (e) {
      return NextResponse.json(
        { ok: false, error: `snap failed after correction: ${e instanceof Error ? e.message : e}`,
          corrected_raw_len: correctedB64.length },
        { status: 500 },
      );
    }

    // 6) Mongo 업데이트
    const nowIso = new Date().toISOString();
    const fieldMap = matrixToFieldMap(snapped.matrix);
    const generatedColors = snapped.stats.dominantColors;
    const setFields: Record<string, unknown> = {
      image_base64: snapped.base64,
      field_map: fieldMap,
      field_map_pipeline: snapped.stats.pipeline,
      palette_mapping: snapped.paletteMapping,
      alt_meta: {
        source: "pixellab_bot_correction",
        strength,
        generated_at: nowIso,
        width: cols,
        height: rows,
        snap_stats: snapped.stats,
      },
      updated_at: nowIso,
    };
    if (generatedColors.length > 0) {
      setFields.generated_colors = generatedColors.map((id) => `c${id}:1`).join(",");
      setFields.generated_num_colors = generatedColors.length;
    }
    // ★ 2단계 백업 ★
    // (1) 최초 원본 — 한 번만 백업 (한 번 만들어지면 절대 덮어쓰지 않음 = 진짜 원본 영구 보존)
    if (!lv.image_base64_pre_correction) {
      setFields.image_base64_pre_correction = srcBase64;
      setFields.field_map_pre_correction = lv.field_map || "";
      setFields.field_map_pipeline_pre_correction = lv.field_map_pipeline || "";
      setFields.palette_mapping_pre_correction = lv.palette_mapping || {};
      setFields.generated_colors_pre_correction = lv.generated_colors || "";
      setFields.generated_num_colors_pre_correction = lv.generated_num_colors || 0;
      setFields.pre_correction_backup_at = nowIso;
    }
    // (2) 직전 상태 — 매번 덮어씀 (Correction 1회 undo / "직전으로 되돌리기"용)
    //     이번 호출 직전(= 현재 lv의 값들)을 통째로 보관.
    setFields.image_base64_pre_last_correction = srcBase64;
    setFields.field_map_pre_last_correction = lv.field_map || "";
    setFields.field_map_pipeline_pre_last_correction = lv.field_map_pipeline || "";
    setFields.palette_mapping_pre_last_correction = lv.palette_mapping || {};
    setFields.generated_colors_pre_last_correction = lv.generated_colors || "";
    setFields.generated_num_colors_pre_last_correction = lv.generated_num_colors || 0;
    setFields.pre_last_correction_at = nowIso;

    await db.collection("pixelforge_levels").updateOne(
      { level_number },
      {
        $set: setFields,
        // 기존 alt가 있으면 정리 (이번 흐름에서는 alt 안 씀)
        $unset: { image_base64_alt: "", field_map_alt: "", palette_mapping_alt: "" },
      },
    );

    return NextResponse.json({
      ok: true,
      level_number,
      strength,
      image_base64_len: snapped.base64.length,
      field_map_len: fieldMap.length,
      pipeline: snapped.stats.pipeline,
      generated_colors: generatedColors,
      stderr_tail: stderrBuf.split("\n").slice(-3).join("\n"),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
