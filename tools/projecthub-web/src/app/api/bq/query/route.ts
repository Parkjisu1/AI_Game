import { NextRequest, NextResponse } from "next/server";
import { bqConfigured, getBigQuery, assertReadOnlySql } from "@/lib/bigquery";

const MAX_ROWS = 1000;
const MAX_BYTES_BILLED = 2 * 1024 * 1024 * 1024; // 2GB 상한 — 실수로 풀스캔 과금 방지

// BigQuery 읽기 전용 쿼리 실행
export async function POST(req: NextRequest) {
  if (!bqConfigured()) {
    return NextResponse.json({ error: "not_configured" }, { status: 503 });
  }
  const body = await req.json().catch(() => null);
  const sql = typeof body?.sql === "string" ? body.sql : "";
  const guard = assertReadOnlySql(sql);
  if (guard) return NextResponse.json({ error: guard }, { status: 400 });

  try {
    const bq = getBigQuery();
    const started = Date.now();
    const [job] = await bq.createQueryJob({
      query: sql,
      useLegacySql: false,
      maximumBytesBilled: String(MAX_BYTES_BILLED),
      jobTimeoutMs: 60_000,
    });
    const [rows] = await job.getQueryResults({ maxResults: MAX_ROWS });
    const [meta] = await job.getMetadata();
    const stats = (meta as { statistics?: { query?: { totalBytesProcessed?: string; totalRows?: string } } }).statistics;

    // 컬럼 추출 (첫 행 기준) + BigQuery 특수 타입(날짜 등 {value}) 평탄화
    const flat = rows.map((r) => {
      const o: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(r as Record<string, unknown>)) {
        o[k] = v !== null && typeof v === "object" && "value" in (v as object) ? (v as { value: unknown }).value : v;
      }
      return o;
    });
    const columns = flat.length > 0 ? Object.keys(flat[0]) : [];

    return NextResponse.json({
      columns,
      rows: flat,
      rowCount: flat.length,
      truncated: flat.length >= MAX_ROWS,
      bytesProcessed: Number(stats?.query?.totalBytesProcessed || 0),
      ms: Date.now() - started,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "쿼리 실행 실패";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
