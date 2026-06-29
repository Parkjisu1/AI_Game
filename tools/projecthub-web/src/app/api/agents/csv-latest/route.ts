import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";

export const runtime = "nodejs";

/**
 * 중앙 CSV 저장소 — 매 배치마다 업로드 X, 최신 버전 1개 참조.
 *
 * GET           : 현재 latest CSV + 버전 히스토리
 * POST          : 신규 CSV 업로드 → latest 갱신 (이전 버전은 history 에 archive)
 * GET ?version= : 특정 버전 fetch
 *
 * collection: pixelforge_csv_versions
 *   { version, label, csv_text, csv_source, uploaded_by, uploaded_at,
 *     row_count, target_levels, is_latest, archived }
 */

const COLL = "pixelforge_csv_versions";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const version = url.searchParams.get("version");
  const db = await getDb();
  const coll = db.collection(COLL);

  if (version) {
    const doc = await coll.findOne({ version });
    if (!doc) return NextResponse.json({ error: "version not found" }, { status: 404 });
    return NextResponse.json({ ...doc, _id: String(doc._id) });
  }

  // 전체 버전 히스토리 + latest 표시
  const versions = await coll.find({},
    { projection: { csv_text: 0 } }
  ).sort({ uploaded_at: -1 }).limit(50).toArray();
  const latest = versions.find((v) => v.is_latest) || versions[0] || null;
  // csv_text 는 latest 만 함께 반환 (UI 미리보기용)
  let latestFull = null;
  if (latest) {
    latestFull = await coll.findOne({ _id: latest._id });
  }
  return NextResponse.json({
    latest: latestFull ? { ...latestFull, _id: String(latestFull._id) } : null,
    history: versions.map((v) => ({ ...v, _id: String(v._id) })),
  });
}

function detectDelimiter(sampleLine: string): string {
  // 첫 비어있지 않은 line 의 separator 자동 감지: , vs ; vs \t
  const counts: Record<string, number> = {
    ",": (sampleLine.match(/,/g) || []).length,
    ";": (sampleLine.match(/;/g) || []).length,
    "\t": (sampleLine.match(/\t/g) || []).length,
  };
  const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return best[1] > 0 ? best[0] : ",";
}

function splitCsvLine(line: string, delim: string): string[] {
  // 단순 quoted-aware split (RFC 4180 의 90% 케이스)
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { cur += '"'; i++; }
      else inQuotes = !inQuotes;
    } else if (ch === delim && !inQuotes) {
      out.push(cur); cur = "";
    } else { cur += ch; }
  }
  out.push(cur);
  return out;
}

function summarizeCsv(csv: string): {
  row_count: number; target_levels: number[]; columns: number;
  header_rows: number; delimiter: string; data_start: number;
  diag: string;
} {
  // BOM 제거
  const cleaned = csv.replace(/^﻿/, "");
  const allLines = cleaned.split(/\r?\n/);
  const lines = allLines.filter((l) => l.trim().length > 0);
  if (lines.length === 0) {
    return { row_count: 0, target_levels: [], columns: 0,
             header_rows: 0, delimiter: ",", data_start: 0,
             diag: "빈 파일 또는 모든 줄이 공백" };
  }
  // delimiter 자동 감지 (첫 5줄 중 가장 길이 긴 줄로)
  const sampleLine = lines.slice(0, 5).sort((a, b) => b.length - a.length)[0] || lines[0];
  const delim = detectDelimiter(sampleLine);

  // data start 자동 감지: column[0] 이 양의 정수인 첫 줄 (단, 처음 50줄 내).
  let dataStart = -1;
  for (let i = 0; i < Math.min(lines.length, 50); i++) {
    const cols = splitCsvLine(lines[i], delim);
    const firstCell = (cols[0] || "").trim().replace(/^"|"$/g, "");
    const n = Number(firstCell);
    if (Number.isFinite(n) && n > 0 && firstCell.match(/^\d+$/)) {
      dataStart = i; break;
    }
  }
  if (dataStart < 0) {
    return { row_count: 0, target_levels: [], columns: lines[0]?.split(delim).length || 0,
             header_rows: lines.length, delimiter: delim, data_start: -1,
             diag: `데이터 행 찾지 못함 (50줄 스캔). delimiter='${delim === "\t" ? "\\t" : delim}'. 첫 컬럼이 양의 정수인 행이 없음.` };
  }

  const dataLines = lines.slice(dataStart);
  const target_levels: number[] = [];
  for (const line of dataLines) {
    const cols = splitCsvLine(line, delim);
    const firstCell = (cols[0] || "").trim().replace(/^"|"$/g, "");
    const lv = Number(firstCell);
    if (Number.isFinite(lv) && lv > 0) target_levels.push(lv);
  }
  // columns: header 마지막 줄 또는 첫 데이터 줄
  const headerSampleLine = dataStart > 0 ? lines[dataStart - 1] : lines[dataStart];
  const columns = splitCsvLine(headerSampleLine, delim).length;
  return {
    row_count: target_levels.length, target_levels, columns,
    header_rows: dataStart, delimiter: delim, data_start: dataStart,
    diag: `OK · delim='${delim === "\t" ? "\\t" : delim}' · header ${dataStart}행 · data ${target_levels.length}건`,
  };
}

export async function POST(req: NextRequest) {
  const session = await auth();
  const email = session?.user?.email || "";
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; }
  catch { return NextResponse.json({ error: "invalid json" }, { status: 400 }); }

  // BOM 제거 (서버 단에서도 보장)
  const csvText = String(body.csv_text || "").replace(/^﻿/, "");
  const label = String(body.label || "").substring(0, 128);
  const csvSource = String(body.csv_source || "manual upload");

  if (!csvText.trim()) {
    return NextResponse.json({ error: "csv_text 필요" }, { status: 400 });
  }
  if (csvText.length > 5_000_000) {
    return NextResponse.json({ error: "csv_text too large (max 5MB)" }, { status: 400 });
  }

  const summary = summarizeCsv(csvText);
  if (summary.row_count === 0) {
    // 첫 5줄 미리보기 — 형식 진단 표시
    const previewLines = csvText.split(/\r?\n/).slice(0, 5);
    return NextResponse.json({
      error: `CSV 파싱 0건 — ${summary.diag}`,
      detail: {
        delimiter: summary.delimiter === "\t" ? "\\t" : summary.delimiter,
        first_5_lines: previewLines,
        hint: "지원 형식: 1행 이상의 헤더 → 첫 컬럼이 양의 정수인 행부터 데이터로 인식. CSV 인코딩 UTF-8 권장 (Excel 저장 시 'CSV UTF-8' 선택).",
      },
      preview: csvText.substring(0, 500),
    }, { status: 400 });
  }

  const db = await getDb();
  const coll = db.collection(COLL);

  // 기존 latest → archived 로 demote
  await coll.updateMany({ is_latest: true }, { $set: { is_latest: false } });

  const now = new Date().toISOString();
  const versionStr = `v${(new Date()).getTime()}`;
  const inserted = await coll.insertOne({
    version: versionStr,
    label: label || `CSV ${now.slice(0, 19)}`,
    csv_text: csvText,
    csv_source: csvSource,
    uploaded_by: email.toLowerCase(),
    uploaded_at: now,
    row_count: summary.row_count,
    target_levels: summary.target_levels,
    columns: summary.columns,
    delimiter: summary.delimiter,
    header_rows: summary.header_rows,
    is_latest: true,
  });

  return NextResponse.json({
    ok: true,
    version: versionStr,
    _id: String(inserted.insertedId),
    row_count: summary.row_count,
    target_levels: summary.target_levels,
    delimiter: summary.delimiter === "\t" ? "\\t" : summary.delimiter,
    header_rows: summary.header_rows,
    diag: summary.diag,
  });
}
