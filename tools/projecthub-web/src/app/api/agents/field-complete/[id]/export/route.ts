import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";
import JSZip from "jszip";

export const runtime = "nodejs";

/**
 * Field-complete job 결과를 BalloonFlow Importer 호환 포맷으로 export.
 *
 * 출력 zip 내용:
 *   - Lv{NNN}_FieldComplete.json (BalloonFlow LevelJsonImporterWindow.JsonLevelData 스키마)
 *   - _manifest.json (job 메타 + per-level 점수 요약)
 *
 * Unity Editor 사용:
 *   BalloonFlow > Import Level Data From JSON → 폴더 추가 → 압축 해제한 디렉토리 선택
 */

interface FCBalloon { row: number; col: number; color: number; life: number; }
interface FCGimmick { type: string; row?: number; col?: number; cells?: unknown[]; life?: number; life_modifier?: number; size?: [number, number]; structure_id?: number; color?: number; chainGroupId?: number; target_color?: number; hidden_color?: number; }
interface FCResult {
  level_number: number;
  ok: boolean;
  score?: number;
  balloons?: FCBalloon[];
  gimmicks?: FCGimmick[];
  field_analysis?: Record<string, unknown>;
  warnings?: string[];
  normalized_purpose?: string;
  color_distribution_auto?: boolean;
}

function buildFieldMap(balloons: FCBalloon[], gimmicks: FCGimmick[], rows: number, cols: number): string {
  // BalloonFlow Importer가 designer_note[FieldMap]를 파싱.
  // 2자리 0-padding color code (1-based: c1→"01"), empty→".."
  const grid: string[][] = [];
  for (let r = 0; r < rows; r++) {
    grid.push(Array(cols).fill(".."));
  }
  for (const b of balloons) {
    if (b.row >= 0 && b.row < rows && b.col >= 0 && b.col < cols) {
      grid[b.row][b.col] = String(b.color).padStart(2, "0");
    }
  }
  // 기믹 셀도 표시 (Hidden Balloon은 hidden_color, 나머지는 type)
  for (const g of gimmicks) {
    const cells: [number, number][] = [];
    if (g.cells) {
      for (const c of g.cells) {
        if (Array.isArray(c) && c.length >= 2 && typeof c[0] === "number" && typeof c[1] === "number") {
          cells.push([c[0] as number, c[1] as number]);
        }
      }
    } else if (typeof g.row === "number" && typeof g.col === "number") {
      cells.push([g.row, g.col]);
    }
    for (const [r, c] of cells) {
      if (r >= 0 && r < rows && c >= 0 && c < cols && grid[r][c] === "..") {
        // 풍선 자리가 아니면 기믹 표시
        if (g.type === "Hidden_Balloon" && typeof g.hidden_color === "number") {
          grid[r][c] = String(g.hidden_color).padStart(2, "0");
        } else if (typeof g.color === "number") {
          grid[r][c] = String(g.color).padStart(2, "0");
        }
      }
    }
  }
  return grid.map((row) => row.join(" ")).join("\n");
}

function colorDistributionStr(color_darts: Record<string, number> | undefined): string {
  if (!color_darts) return "";
  return Object.entries(color_darts).map(([k, v]) => `${k}:${v}`).join(" ");
}

interface CsvRowMeta {
  level_number?: number; pkg?: number | string; pos?: number | string; chapter?: number | string;
  purpose_type?: string; field_rows?: number | string; field_columns?: number | string;
  total_cells?: number | string; num_colors?: number | string; rail_capacity?: number | string;
  queue_columns?: number | string; queue_rows?: number | string; dart_capacity_range?: string;
  emotion_curve?: string;
}

function toBalloonFlowFormat(result: FCResult, csvRow: CsvRowMeta) {
  const fa = (result.field_analysis || {}) as { color_darts?: Record<string, number>; total_darts?: number; total_darts_rounded?: number; metaphor_preservation_score?: number };
  const lv = result.level_number;
  const rows = Number(csvRow.field_rows ?? 0) || 0;
  const cols = Number(csvRow.field_columns ?? 0) || 0;
  const fieldMap = buildFieldMap(result.balloons || [], result.gimmicks || [], rows, cols);

  // BalloonFlow Importer camelCase 필드 — level_number 기반 자동 도출
  // pkg / pos는 CSV에 명시 있으면 그거 사용, 없으면 level_number 기반 자동
  const pkg = Number(csvRow.pkg ?? 0) || Math.floor((lv - 1) / 20) + 1;
  const pos = Number(csvRow.pos ?? 0) || ((lv - 1) % 20) + 1;
  const chapter = Number(csvRow.chapter ?? 0) || pkg;

  return {
    // BalloonFlow LevelJsonImporterWindow Legacy JsonLevelData schema (snake_case).
    // camelCase(levelId/packageId/positionInPackage) 출력은 폐기:
    //   - LevelConfig path 에서 부분 필드(levelId 만 존재, rail/gridRows/gridCols/balloons 누락) →
    //     "ROLLBACK_IMPORT_RUNTIME_LEVEL_JSON" 가드(line 514)에 걸려 return false → Legacy 로 fallback.
    //   - 추가 fields 가 있어도 JsonUtility 가 unknown keys 를 무시할 뿐이지만, 불필요한 LevelConfig 시도를
    //     사전 차단해 import 흐름 직진. (2026-05-27)
    level_number: lv,
    level_id: `BF_${String(lv).padStart(3, "0")}`,
    pkg: pkg,
    pos: pos,
    chapter: chapter,
    purpose_type: result.normalized_purpose || csvRow.purpose_type || "normal",
    target_cr: 85,
    target_attempts: 1.5,
    num_colors: Number(csvRow.num_colors ?? 0) || 0,
    color_distribution: colorDistributionStr(fa.color_darts),
    field_rows: rows,
    field_columns: cols,
    total_cells: Number(csvRow.total_cells ?? 0) || (result.balloons?.length ?? 0),
    rail_capacity: Number(csvRow.rail_capacity ?? 0) || 0,
    rail_capacity_tier: String((csvRow as { rail_capacity_tier?: string | number }).rail_capacity_tier ?? ""), // JsonLevelData L48
    queue_columns: Number(csvRow.queue_columns ?? 0) || 0,
    queue_rows: Number(csvRow.queue_rows ?? 0) || 0,
    // 기믹 카운트 (Track A/B 산출물 기준)
    ...(() => {
      const counts: Record<string, number> = {
        gimmick_hidden: 0, gimmick_chain: 0, gimmick_pinata: 0, gimmick_spawner_t: 0,
        gimmick_pin: 0, gimmick_lock_key: 0, gimmick_surprise: 0, gimmick_wall: 0,
        gimmick_spawner_o: 0, gimmick_pinata_box: 0, gimmick_ice: 0,
        gimmick_frozen_dart: 0, gimmick_curtain: 0,
      };
      // Unity 측 gimmick 통합 (2026-05-27): Pin + Barricade 가 동일 gimmick_pin 컬럼 사용.
      // (watcher 가 "Barricade" type 으로 출력해도 "Pin" alias 로도 도착할 수 있어 둘 다 매핑.)
      const TYPE_TO_COL: Record<string, string> = {
        Wooden_Board: "gimmick_pinata",
        Barricade: "gimmick_pin",
        Pin: "gimmick_pin",          // Pin/Barricade 통합 alias
        Hidden_Balloon: "gimmick_surprise",
        Iron_Wall: "gimmick_wall",
        Target_Box: "gimmick_pinata_box",
        Frozen_Layer: "gimmick_ice",
        Color_Curtain: "gimmick_curtain",
      };
      for (const g of result.gimmicks || []) {
        const col = TYPE_TO_COL[g.type];
        if (col) counts[col] = (counts[col] || 0) + (g.cells?.length ?? 1);
      }
      return counts;
    })(),
    total_darts: fa.total_darts ?? 0,
    dart_capacity_range: csvRow.dart_capacity_range || "10,20,40",
    emotion_curve: csvRow.emotion_curve || "",
    designer_note: `[Source]\nfield-complete v1.1 algorithm\nscore=${result.score?.toFixed(4)}\n\n[Accuracy]\nfield_complete_score=${result.score?.toFixed(4)}\nmetaphor=${fa.metaphor_preservation_score?.toFixed(3)}\nauto_color_dist=${result.color_distribution_auto}\n\n[FieldMap]\n${fieldMap}`,
    pixel_art_source: "",
  };
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  let jobObjId: ObjectId;
  try {
    jobObjId = new ObjectId(id);
  } catch {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  const db = await getDb();
  const job = await db.collection("pixelforge_field_complete_jobs").findOne({ _id: jobObjId });
  if (!job) return NextResponse.json({ error: "job not found" }, { status: 404 });

  const results = (job.results || []) as FCResult[];
  const csvRows = (job.csv_rows || []) as CsvRowMeta[];

  const okResults = results.filter((r) => r.ok && (r.balloons?.length ?? 0) > 0);
  if (okResults.length === 0) {
    return NextResponse.json({ error: "no ok results with balloons in this job" }, { status: 404 });
  }

  // Queue 생성 게이트: 모든 ok 레벨이 queue_data 를 보유해야 export 허용
  // (?force=1 로 우회 가능 — 기존 BuildHolders fallback 으로 동작)
  const url = new URL(req.url);
  const force = url.searchParams.get("force") === "1";
  const okLevelNums = okResults.map((r) => r.level_number);
  const designerRows = await db.collection("pixelforge_levels")
    .find({ level_number: { $in: okLevelNums }, status: { $exists: true } }, { projection: { level_number: 1, queue_data: 1 } })
    .toArray();
  const queueByLv = new Map<number, unknown>();
  for (const row of designerRows) {
    if (row.queue_data) queueByLv.set(Number(row.level_number), row.queue_data);
  }
  const missingQueue = okLevelNums.filter((lv) => !queueByLv.has(lv));
  if (!force && missingQueue.length > 0) {
    return NextResponse.json(
      {
        error: "queue_data missing",
        message: `${missingQueue.length}/${okLevelNums.length} levels have no queue_data. Run [🎲 Queue 생성] first, or call with ?force=1 to bypass.`,
        missing_levels: missingQueue.slice(0, 20),
        missing_count: missingQueue.length,
      },
      { status: 412 }, // Precondition Failed
    );
  }

  // csvRows 인덱스 매핑 (level_number 기준)
  const csvByLv: Map<number, CsvRowMeta> = new Map();
  for (const c of csvRows) {
    if (typeof c.level_number !== "undefined") {
      csvByLv.set(Number(c.level_number), c);
    }
  }

  const zip = new JSZip();
  const manifest: { job_id: string; csv_source: string; generated_at: string; queue_included: boolean; levels: { level_number: number; score: number; ok: boolean; balloons: number; gimmicks: number; queue: boolean; }[]; } = {
    job_id: id,
    csv_source: String(job.csv_source || ""),
    generated_at: new Date().toISOString(),
    queue_included: !force,
    levels: [],
  };

  for (const r of okResults) {
    const csvRow = csvByLv.get(r.level_number) || {};
    const bf = toBalloonFlowFormat(r, csvRow);
    // queue_data 가 있으면 BalloonFlow JSON 에 추가 — Unity importer 가 BuildHolders 대신 이걸 사용하도록.
    const queueData = queueByLv.get(r.level_number);
    if (queueData) {
      (bf as Record<string, unknown>).queue_data = queueData;
    }
    const fname = `Lv${String(r.level_number).padStart(3, "0")}_FieldComplete.json`;
    zip.file(fname, JSON.stringify(bf, null, 2));
    manifest.levels.push({
      level_number: r.level_number,
      score: r.score ?? 0,
      ok: r.ok,
      balloons: r.balloons?.length ?? 0,
      gimmicks: r.gimmicks?.length ?? 0,
      queue: !!queueData,
    });
  }

  zip.file("_manifest.json", JSON.stringify(manifest, null, 2));
  zip.file("README.md", `# Field-Complete Export

Job ID: ${id}
Source: ${job.csv_source}
Generated: ${manifest.generated_at}
OK levels: ${okResults.length}

## Unity Import 방법

1. 이 zip을 압축 해제
2. Unity Editor 열기
3. **BalloonFlow > Import Level Data From JSON** 메뉴
4. **폴더 추가...** → 압축 해제한 디렉토리 선택
5. ${okResults.length}개 자동 로드 → 좌측에 Lv001~LvNNN 표시
6. **저장 대상**: \`Origin\` / \`AI Extractor\` / \`Transform Extractor\` 중 선택
7. **\`<DB명>에 추가\`** 버튼 클릭

## 산출물

각 파일: BalloonFlow \`LevelJsonImporterWindow.JsonLevelData\` 스키마 (snake_case).
\`designer_note\`의 \`[FieldMap]\` 섹션에 풍선 + 기믹 위치가 인코딩됨.
`);

  const zipBuf = await zip.generateAsync({ type: "nodebuffer" });
  return new NextResponse(zipBuf as unknown as BodyInit, {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="field_complete_${id.slice(-8)}.zip"`,
    },
  });
}
