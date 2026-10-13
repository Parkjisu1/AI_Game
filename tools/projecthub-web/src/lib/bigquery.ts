import { BigQuery } from "@google-cloud/bigquery";

/**
 * BigQuery 클라이언트 — clean 인스턴스(NewPlay) 데이터 페이지용.
 * 설정: .env.production
 *   BQ_PROJECT_ID       — GCP 프로젝트 ID
 *   BQ_SA_KEY_JSON      — 서비스 계정 키 JSON 전체 (한 줄, 또는 base64)
 *   (또는 표준 GOOGLE_APPLICATION_CREDENTIALS 경로)
 * 둘 다 없으면 configured=false — API는 503 not_configured 반환.
 */

let cached: BigQuery | null = null;

export function bqConfigured(): boolean {
  return Boolean(process.env.BQ_PROJECT_ID && (process.env.BQ_SA_KEY_JSON || process.env.GOOGLE_APPLICATION_CREDENTIALS));
}

export function getBigQuery(): BigQuery {
  if (cached) return cached;
  const projectId = process.env.BQ_PROJECT_ID || "";
  const raw = process.env.BQ_SA_KEY_JSON || "";
  if (raw) {
    let jsonStr = raw.trim();
    if (!jsonStr.startsWith("{")) {
      // base64 허용
      jsonStr = Buffer.from(jsonStr, "base64").toString("utf8");
    }
    const credentials = JSON.parse(jsonStr);
    cached = new BigQuery({ projectId, credentials });
  } else {
    cached = new BigQuery({ projectId });
  }
  return cached;
}

/** 읽기 전용 가드 — SELECT/WITH 단일 문만 허용 */
export function assertReadOnlySql(sql: string): string | null {
  const s = sql.trim().replace(/;\s*$/, "");
  if (!s) return "쿼리가 비어 있습니다";
  if (s.includes(";")) return "단일 문만 실행할 수 있습니다";
  const head = s.replace(/^\s*(--[^\n]*\n|\/\*[\s\S]*?\*\/)*/g, "").trim().slice(0, 12).toUpperCase();
  if (!head.startsWith("SELECT") && !head.startsWith("WITH")) {
    return "SELECT/WITH 쿼리만 실행할 수 있습니다 (읽기 전용)";
  }
  return null;
}
