import { NextRequest, NextResponse } from "next/server";
import { bqConfigured, getBigQuery } from "@/lib/bigquery";

// BigQuery 메타 — 데이터셋 목록, ?dataset= 지정 시 해당 데이터셋의 테이블 목록.
export async function GET(req: NextRequest) {
  if (!bqConfigured()) {
    return NextResponse.json({ configured: false, datasets: [] });
  }
  try {
    const bq = getBigQuery();
    const dataset = req.nextUrl.searchParams.get("dataset");
    if (dataset) {
      const [tables] = await bq.dataset(dataset).getTables();
      return NextResponse.json({
        configured: true,
        tables: tables.map((t) => ({
          id: t.id,
          type: (t.metadata as { type?: string } | undefined)?.type || "TABLE",
        })),
      });
    }
    const [datasets] = await bq.getDatasets();
    return NextResponse.json({
      configured: true,
      projectId: process.env.BQ_PROJECT_ID,
      datasets: datasets.map((d) => ({ id: d.id })),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "BigQuery 오류";
    return NextResponse.json({ configured: true, error: msg }, { status: 500 });
  }
}
