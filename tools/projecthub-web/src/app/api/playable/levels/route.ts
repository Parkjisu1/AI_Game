import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";

export const runtime = "nodejs";

/**
 * CrewFlow 플레이어블에 쓸 수 있는 레벨 목록.
 *
 * 원본은 `scripts/sync-playable.mjs` 가 구워 둔 `public/playable/levels.json` 이다.
 * 300개를 매 요청마다 파싱하지 않으려고 한 파일로 미리 접어 둔다.
 *
 * 예상 시간은 실측 기반이다 — 소프트웨어 렌더러 스모크에서 30초에 약 140개를 수거했고,
 * 실기기는 그보다 빠르다. 정확한 값이 아니라 <b>레벨끼리 비교</b>하라고 있는 숫자다.
 * (레벨 선택은 "그림"을 고르는 것이지 "몇 초에 끝나는지"를 고르는 게 아니다 —
 *  가장 작은 레벨도 320큐브라 광고 길이 안에 클리어되지 않는다.)
 */
export async function GET() {
  const file = path.join(process.cwd(), "public", "playable", "levels.json");

  if (!fs.existsSync(file)) {
    return NextResponse.json(
      {
        error: "not-synced",
        message: "public/playable 이 비어 있다. node scripts/sync-playable.mjs 를 먼저 돌릴 것.",
      },
      { status: 503 },
    );
  }

  const raw = JSON.parse(fs.readFileSync(file, "utf8")) as {
    generatedAt: string;
    count: number;
    levels: Array<{
      id: number; cubes: number; cols: number; rows: number;
      colors: number; holders: number; queueColumns: number; bytes: number;
    }>;
  };

  // 스모크 실측: 약 30초에 140개 수거 → 초당 4.7개
  const PER_SEC = 4.7;

  const levels = raw.levels.map(l => ({
    ...l,
    estimatedSeconds: Math.round(l.cubes / PER_SEC),
  }));

  return NextResponse.json({ ...raw, levels });
}
