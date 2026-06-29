// 레벨 데이터 → Unity Importer가 읽는 JSON 형식 변환
// Gallery 페이지와 JSON Vault 페이지에서 공유하는 로직.

import { computeImageSize } from "./genUtils";

export interface LevelLike {
  level_number?: number | string;
  level_id?: string;
  pkg?: number | string;
  pos?: number | string;
  chapter?: number | string;
  purpose_type?: string;
  target_cr?: number | string;
  target_attempts?: number | string;
  num_colors?: number | string;
  color_distribution?: string;
  field_rows?: number | string;
  field_columns?: number | string;
  total_cells?: number | string;
  rail_capacity?: number | string;
  rail_capacity_tier?: string;
  queue_columns?: number | string;
  queue_rows?: number | string;
  gimmick_hidden?: number | string;
  gimmick_chain?: number | string;
  gimmick_pinata?: number | string;
  gimmick_spawner_t?: number | string;
  gimmick_pin?: number | string;
  gimmick_lock_key?: number | string;
  gimmick_surprise?: number | string;
  gimmick_wall?: number | string;
  gimmick_spawner_o?: number | string;
  gimmick_pinata_box?: number | string;
  gimmick_ice?: number | string;
  gimmick_frozen_dart?: number | string;
  gimmick_curtain?: number | string;
  total_darts?: number | string;
  dart_capacity_range?: string;
  emotion_curve?: string;
  designer_note?: string;
  field_map?: string;
  [key: string]: unknown;
}

const n = (v: unknown, d: number) => parseInt(String(v)) || d;
const f = (v: unknown, d: number) => parseFloat(String(v)) || d;
const s = (v: unknown, d: string) => String(v ?? d);

export function buildLevelJson(level: LevelLike) {
  const lvNum = n(level.level_number, 1);
  const cols = n(level.field_columns, 20);
  const rows = n(level.field_rows, 20);
  const dim = computeImageSize(cols, rows);

  return {
    level_number: lvNum,
    // Unity importer가 셀 그리드를 정확히 알 수 있도록 픽셀 메타 추가
    image_width: dim.width,
    image_height: dim.height,
    pixels_per_cell: dim.pixelsPerCell,
    level_id: s(level.level_id, `BF_${String(lvNum).padStart(3, "0")}`),
    pkg: n(level.pkg, 1),
    pos: n(level.pos, 1),
    chapter: n(level.chapter, 1),
    purpose_type: s(level.purpose_type, ""),
    target_cr: n(level.target_cr, 60),
    target_attempts: f(level.target_attempts, 1.8),
    num_colors: n(level.num_colors, 4),
    color_distribution: s(level.color_distribution, ""),
    field_rows: rows,
    field_columns: cols,
    total_cells: n(level.total_cells, 0),
    rail_capacity: n(level.rail_capacity, 160),
    rail_capacity_tier: s(level.rail_capacity_tier, ""),
    queue_columns: n(level.queue_columns, 2),
    queue_rows: n(level.queue_rows, 20),
    gimmick_hidden: n(level.gimmick_hidden, 0),
    gimmick_chain: n(level.gimmick_chain, 0),
    gimmick_pinata: n(level.gimmick_pinata, 0),
    gimmick_spawner_t: n(level.gimmick_spawner_t, 0),
    gimmick_pin: n(level.gimmick_pin, 0),
    gimmick_lock_key: n(level.gimmick_lock_key, 0),
    gimmick_surprise: n(level.gimmick_surprise, 0),
    gimmick_wall: n(level.gimmick_wall, 0),
    gimmick_spawner_o: n(level.gimmick_spawner_o, 0),
    gimmick_pinata_box: n(level.gimmick_pinata_box, 0),
    gimmick_ice: n(level.gimmick_ice, 0),
    gimmick_frozen_dart: n(level.gimmick_frozen_dart, 0),
    gimmick_curtain: n(level.gimmick_curtain, 0),
    total_darts: n(level.total_darts, 0),
    dart_capacity_range: s(level.dart_capacity_range, ""),
    emotion_curve: s(level.emotion_curve, ""),
    designer_note: (() => {
      let note = s(level.designer_note, "");
      const fmIdx = note.indexOf("[FieldMap]");
      if (fmIdx >= 0) note = note.substring(0, fmIdx).trim();
      const fm = s(level.field_map, "");
      return fm ? note + "\n[FieldMap]\n" + fm : note;
    })(),
    pixel_art_source: `level_${String(lvNum).padStart(3, "0")}_${cols}x${rows}.png`,
  };
}

export function levelFileName(level: LevelLike, ext: "json" | "png") {
  const lvNum = n(level.level_number, 1);
  const cols = n(level.field_columns, 20);
  const rows = n(level.field_rows, 20);
  return `level_${String(lvNum).padStart(3, "0")}_${cols}x${rows}.${ext}`;
}

export function downloadLevelJson(level: LevelLike) {
  const data = buildLevelJson(level);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = levelFileName(level, "json");
  a.click();
  URL.revokeObjectURL(a.href);
}
