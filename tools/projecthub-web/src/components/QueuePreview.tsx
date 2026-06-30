"use client";
import React, { useMemo, useState } from "react";

// QueuePreview — BalloonFlow 큐 시각화 + 재생성 + 확정 + 난이도 선택
// 두 앱 (projecthub-web, pixelforge-web) 공통 사용.
//
// Props:
//   - mode: "projecthub" | "pixelforge"
//   - fetchQueue(seed, difficulty): Promise<QueueData>
//   - onConfirm?(queue): Promise<void>
//   - initialDifficulty?: 기본 선택 난이도

export type Difficulty = "tutorial" | "rest" | "normal" | "hard" | "super_hard";

const DIFFICULTY_OPTIONS: { value: Difficulty; label: string }[] = [
  { value: "tutorial",   label: "Tutorial" },
  { value: "rest",       label: "Rest" },
  { value: "normal",     label: "Normal" },
  { value: "hard",       label: "Hard" },
  { value: "super_hard", label: "Super Hard" },
];

export type QueueHolder = {
  color: number;
  mag: number;
};

// §5 STEP C QueueOverlay (큐 기믹 결과)
export type QueueOverlay = {
  hidden_ids: number[];
  linked_groups: { ids: number[]; same_color: boolean }[];
  frozen: { id: number; health: number }[];
};

export type StepCValidation = {
  applied: boolean;
  multi_gimmick_pass: boolean;
  hidden_line0_pass: boolean;
  link_n_hidden_pass: boolean;
  chain_adjacency_pass?: boolean;
  chain_cycle_pass?: boolean;
  hard_fail_reason?: string;
  intro_lv_filter?: string;
  chain_cycle_retries?: number;
};

// 필드 기믹 오버레이
export type FieldGimmickOverlay = {
  pinata_balloons: { balloonId: number; life: number }[];
  wall_cells: { row: number; col: number; areaW: number; areaH: number }[];
  hidden_balloons: number[];
  pinata_box_areas: { row: number; col: number; areaW: number; areaH: number; eggs: { color: number; count: number }[] }[];
  frozen_layer_areas: { row: number; col: number; areaW: number; areaH: number; life: number }[];
  barricade_lines: { positions: { row: number; col: number }[]; color: number; life: number }[];
};

export type FieldGimmickValidation = {
  applied: boolean;
  pinata_placed: number;
  wall_placed: number;
  hidden_balloons_placed: number;
  pinata_box_placed: number;
  frozen_layer_placed: number;
  barricade_placed: number;
  warnings: string[];
};

export type QueueData = {
  holders: QueueHolder[];
  queue_columns: number;
  recommended_queue_columns: number;
  field_analysis: {
    color_darts: Record<number, number>;
    color_depth: Record<number, number>;
    outermost_colors: number[];
    total_darts: number;
    rail_capacity: number;
  };
  difficulty_score: {
    relative_pct: number;
    grade: "easy" | "normal" | "hard" | "super_hard" | "trivial";
  };
  validation: {
    color_dart_match: boolean;
    all_mags_in_set: boolean;
    all_under_max: boolean;
    cap20_backbone_pass: boolean;
    first_rows_depth_guard: boolean;
    cap_kinds_count: number;
    cap20_ratio: number;
    avg_ammo_per_holder: number;
    holder_count: number;
    retries: number;
    decomposed_total?: number;
    hard_fail_reasons?: string[];
  };
  seed: number;
  difficulty: string;
  overlay?: QueueOverlay | null;
  step_c_validation?: StepCValidation | null;
  field_overlay?: FieldGimmickOverlay | null;
  field_gimmick_validation?: FieldGimmickValidation | null;
};

// ─── 두 팔레트 (앱마다 다름) ──────────────────────
//
// ⚠ ProjectHub vs PixelForge 색 인덱스 체계 차이:
//   - ProjectHub `pixelforge_grid_levels.cells`: 0-based, 24색 (Linear cowork batch 생성)
//   - PixelForge `pixelforge_levels.field_map`: 1-based, 28색 (PixelLab/snapToGridV2 생성)
//
// 각 caller가 본인 팔레트 모드를 paletteMode prop으로 명시.
// 동일 색상값 5 → ProjectHub mode면 Orange, PixelForge mode면 Lime — 다름.

export type PaletteMode = "balloonflow_28" | "balloonflow_24";

// 1-based 28색 (BalloonFlow PixelArtEngine.cs:15-44 — PixelForge 사용)
const PALETTE_28: Record<number, string> = {
  1: "#fc6aaf", 2: "#50e8f6", 3: "#8950f8", 4: "#fed555", 5: "#73fe66",
  6: "#fda14c", 7: "#ffffff", 8: "#414141", 9: "#6ea8fa", 10: "#39ae2e",
  11: "#fc5e5e", 12: "#326bf8", 13: "#3aa58b", 14: "#e7a7fa", 15: "#b7c7fb",
  16: "#6a4a30", 17: "#fee3a9", 18: "#fdb7c1", 19: "#9e3d5e", 20: "#a7dd94",
  21: "#592e7e", 22: "#dc7881", 23: "#d9d9e7", 24: "#6f727f", 25: "#fc38a5",
  26: "#fdb458", 27: "#890a08", 28: "#6fafb1",
};
const PALETTE_28_NAMES: Record<number, string> = {
  1:"HotPink", 2:"Cyan", 3:"Purple", 4:"Yellow", 5:"Lime", 6:"Orange", 7:"White", 8:"DarkGray",
  9:"SkyBlue", 10:"Forest", 11:"Red", 12:"Blue", 13:"Teal", 14:"Lavender", 15:"Periwinkle",
  16:"Brown", 17:"Cream", 18:"Pink", 19:"Wine", 20:"Mint", 21:"Indigo", 22:"Rose",
  23:"Silver", 24:"Gray", 25:"Magenta", 26:"PeachExt", 27:"DarkRed", 28:"CyanExt",
};

// 0-based 24색 (ProjectHub /levels page BALLOONFLOW_COLORS_HEX 동일)
const PALETTE_24: Record<number, string> = {
  0: "#fc6aaf", 1: "#50e8f6", 2: "#8950f8", 3: "#fed555", 4: "#73fe66",
  5: "#fda14c", 6: "#ffffff", 7: "#414141", 8: "#6ea8fa", 9: "#39ae2e",
  10: "#fc5e5e", 11: "#326bf8", 12: "#3aa58b", 13: "#e7a7fa", 14: "#b7c7fb",
  15: "#6a4a30", 16: "#fee3a9", 17: "#fdb7c1", 18: "#9e3d5e", 19: "#a7dd94",
  20: "#592e7e", 21: "#dc7881", 22: "#d9d9e7", 23: "#6f727f",
};
const PALETTE_24_NAMES: Record<number, string> = {
  0:"HotPink", 1:"Cyan", 2:"Purple", 3:"Yellow", 4:"Green", 5:"Orange", 6:"White", 7:"DarkGray",
  8:"SkyBlue", 9:"Forest", 10:"Red", 11:"Blue", 12:"Teal", 13:"Lavender", 14:"Periwinkle",
  15:"Brown", 16:"Cream", 17:"Pink", 18:"Wine", 19:"Mint", 20:"Indigo", 21:"Rose",
  22:"Silver", 23:"Gray",
};

function getPalette(mode: PaletteMode): { hex: Record<number, string>; name: Record<number, string> } {
  if (mode === "balloonflow_24") return { hex: PALETTE_24, name: PALETTE_24_NAMES };
  return { hex: PALETTE_28, name: PALETTE_28_NAMES };
}

// 흰/연한 배경에 검정 텍스트가 더 잘 보이는 색상 (각 팔레트별 인덱스 다름)
function isLightFor(mode: PaletteMode, id: number): boolean {
  if (mode === "balloonflow_24") {
    // 24색 0-based: 3=Yellow, 6=White, 13=Lavender, 14=Periwinkle, 16=Cream, 17=Pink, 19=Mint, 22=Silver
    return new Set([3, 6, 13, 14, 16, 17, 19, 22]).has(id);
  }
  // 28색 1-based
  return new Set([4, 7, 14, 15, 17, 18, 20, 23]).has(id);
}

const GRADE_COLOR: Record<QueueData["difficulty_score"]["grade"], string> = {
  trivial:    "#9ca3af",
  easy:       "#22c55e",
  normal:     "#3b82f6",
  hard:       "#f97316",
  super_hard: "#ef4444",
};
const GRADE_LABEL: Record<QueueData["difficulty_score"]["grade"], string> = {
  trivial: "Trivial", easy: "Easy", normal: "Normal", hard: "Hard", super_hard: "Super Hard",
};

type Props = {
  mode: "projecthub" | "pixelforge";
  fetchQueue: (seed?: number, difficulty?: Difficulty) => Promise<QueueData>;
  onConfirm?: (queue: QueueData) => Promise<void>;
  initialSeed?: number;
  initialDifficulty?: Difficulty;
  // ⚠ paletteMode 필수 — 컬러 인덱스 체계 (ProjectHub=0-based 24색, PixelForge=1-based 28색)
  paletteMode: PaletteMode;
  className?: string;
};

export default function QueuePreview({
  mode, fetchQueue, onConfirm, initialSeed, initialDifficulty, paletteMode, className,
}: Props) {
  const palette = getPalette(paletteMode);
  const colorHex = (id: number): string => palette.hex[id] ?? "#888";
  const colorName = (id: number): string => palette.name[id] ?? "?";
  const isLightColor = (id: number): boolean => isLightFor(paletteMode, id);
  const [queue, setQueue] = useState<QueueData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seedHistory, setSeedHistory] = useState<number[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [difficulty, setDifficulty] = useState<Difficulty>(initialDifficulty ?? "normal");

  const loadSeed = async (seed: number | undefined, diff: Difficulty) => {
    setLoading(true);
    setError(null);
    setConfirmed(false);
    try {
      const q = await fetchQueue(seed, diff);
      setQueue(q);
      setSeedHistory((prev) => {
        if (prev.includes(q.seed)) return prev;
        return [...prev, q.seed].slice(-8);
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (queue == null && !loading && !error) {
      void loadSeed(initialSeed, difficulty);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onRegenerate = () => {
    const newSeed = Math.floor(Math.random() * 0x7fffffff);
    void loadSeed(newSeed, difficulty);
  };

  const onChangeDifficulty = (d: Difficulty) => {
    setDifficulty(d);
    // 난이도 변경 시 즉시 재생성 (새 seed)
    const newSeed = Math.floor(Math.random() * 0x7fffffff);
    void loadSeed(newSeed, d);
  };

  const onClickHistorySeed = (s: number) => void loadSeed(s, difficulty);

  const onConfirmClick = async () => {
    if (!queue || !onConfirm) return;
    setConfirming(true);
    try {
      await onConfirm(queue);
      setConfirmed(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirming(false);
    }
  };

  const grid = useMemo(() => {
    if (!queue) return null;
    const cols = queue.queue_columns;
    const holders = queue.holders ?? [];
    const rows: QueueHolder[][] = [];
    for (let i = 0; i < holders.length; i += cols) {
      rows.push(holders.slice(i, i + cols));
    }
    return { rows, cols };
  }, [queue]);

  // 큐 기믹 lookup (overlay → holder index 기반)
  const gimmickMap = useMemo(() => {
    const m = new Map<number, { kind: "hidden" | "linked" | "frozen"; group?: number; health?: number; same_color?: boolean }>();
    if (!queue?.overlay) return m;
    queue.overlay.hidden_ids?.forEach(id => m.set(id, { kind: "hidden" }));
    queue.overlay.linked_groups?.forEach((g, gi) =>
      g.ids?.forEach(id => m.set(id, { kind: "linked", group: gi, same_color: g.same_color }))
    );
    queue.overlay.frozen?.forEach(f => m.set(f.id, { kind: "frozen", health: f.health }));
    return m;
  }, [queue]);

  return (
    <div className={`bg-slate-50 border border-slate-200 rounded-lg p-3 ${className ?? ""}`}>
      {/* 헤더: 제목 + 컨트롤 (가로 컴팩트, wrap 허용) */}
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <h3 className="text-sm font-semibold text-slate-700 shrink-0">큐 미리보기</h3>
        <div className="flex items-center gap-1.5 flex-wrap">
          <select
            value={difficulty}
            onChange={(e) => onChangeDifficulty(e.target.value as Difficulty)}
            disabled={loading}
            className="px-2 py-1 text-xs border border-slate-300 rounded bg-white disabled:opacity-50"
            title="난이도 선택 — 변경 시 자동 재생성"
          >
            {DIFFICULTY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            onClick={onRegenerate}
            disabled={loading}
            className="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 shrink-0"
            title="새 seed로 재생성"
          >
            🎲 재생성
          </button>
          {mode === "pixelforge" && onConfirm && (
            <button
              onClick={onConfirmClick}
              disabled={!queue || confirming || confirmed || loading}
              className="px-3 py-1 text-xs bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 shrink-0"
            >
              {confirmed ? "✓ 확정됨" : confirming ? "저장 중..." : "💾 확정"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-2 rounded mb-2 break-all">
          {error}
        </div>
      )}

      {loading && !queue && (
        <div className="text-xs text-slate-500 py-4">로딩 중...</div>
      )}

      {queue && (
        <>
          {/* 점수 게이지 */}
          <div className="mb-3">
            <div className="flex items-center justify-between text-xs mb-1 gap-2">
              <span className="text-slate-600 shrink-0">난이도 점수</span>
              <span
                className="font-medium text-right truncate"
                style={{ color: queue.difficulty_score?.grade ? GRADE_COLOR[queue.difficulty_score.grade] : undefined }}
              >
                {queue.difficulty_score?.relative_pct?.toFixed(0) ?? "—"}% [{queue.difficulty_score?.grade ? GRADE_LABEL[queue.difficulty_score.grade] : "—"}]
              </span>
            </div>
            <div className="h-2 bg-slate-200 rounded overflow-hidden">
              <div
                className="h-full transition-all"
                style={{
                  width: `${Math.min(100, queue.difficulty_score?.relative_pct ?? 0)}%`,
                  background: queue.difficulty_score?.grade ? GRADE_COLOR[queue.difficulty_score.grade] : undefined,
                }}
              />
            </div>
          </div>

          {/* 메타 요약 — 컴팩트, 표 줄바꿈 */}
          <div className="text-[11px] text-slate-600 mb-2 flex flex-wrap gap-x-3 gap-y-0.5">
            <span>보관함 {queue.validation?.holder_count}</span>
            <span>다트 {queue.validation?.decomposed_total ?? queue.field_analysis?.total_darts}/{queue.field_analysis?.total_darts}{queue.validation?.color_dart_match ? " ✓" : " ✗"}</span>
            <span>cap20 {((queue.validation?.cap20_ratio ?? 0) * 100).toFixed(0)}%</span>
            <span>caps {queue.validation?.cap_kinds_count}</span>
            <span>avg {queue.validation?.avg_ammo_per_holder?.toFixed(1) ?? "—"}</span>
            <span>cols {queue.queue_columns}({queue.recommended_queue_columns})</span>
            <span>retry {queue.validation?.retries}</span>
          </div>

          {/* 큐 그리드 시각화 — 가로 스크롤 + 셀 일정 너비 */}
          {grid && (
            <div className="bg-white border border-slate-200 rounded p-2 mb-3 overflow-x-auto max-w-full">
              <div className="inline-block min-w-fit">
                {grid.rows.map((row, ri) => (
                  <div key={ri} className="flex gap-1 mb-1 items-center">
                    <span className="text-[10px] text-slate-400 w-7 shrink-0 text-right pr-1 leading-6">R{ri + 1}</span>
                    {row.map((h, ci) => {
                      const idx = ri * queue.queue_columns + ci;
                      const depth = queue.field_analysis?.color_depth?.[h.color] ?? 0;
                      const gm = gimmickMap.get(idx);
                      // 기믹 라벨 + 색상 라벨
                      let gimmickBadge = "";
                      if (gm?.kind === "hidden") gimmickBadge = "❓";
                      else if (gm?.kind === "linked") gimmickBadge = `🔗${gm.group != null ? gm.group + 1 : ""}`;
                      else if (gm?.kind === "frozen") gimmickBadge = `❄${gm.health ?? ""}`;
                      const titleParts = [
                        `idx=${idx}`,
                        `color=${h.color}(${colorName(h.color)})`,
                        `cap=${h.mag}`,
                        `depth=${depth}`,
                      ];
                      if (gm) titleParts.push(`gimmick=${gm.kind}${gm.health != null ? ` H${gm.health}` : ""}${gm.same_color ? " (same)" : ""}`);
                      return (
                        <div
                          key={ci}
                          className="text-[10px] font-mono rounded border-2 shrink-0 leading-tight flex flex-col items-stretch"
                          style={{
                            background: colorHex(h.color),
                            color: isLightColor(h.color) ? "#000" : "#fff",
                            borderColor: gm?.kind === "linked" ? "#7c3aed"
                                       : gm?.kind === "frozen" ? "#0ea5e9"
                                       : gm?.kind === "hidden" ? "#f59e0b"
                                       : depth === 0 ? "#000" : "#94a3b8",
                            width: 56,
                            textAlign: "center",
                            whiteSpace: "nowrap",
                            padding: "2px 1px",
                          }}
                          title={titleParts.join(" / ")}
                        >
                          {gimmickBadge && (
                            <span className="text-[9px] leading-none mb-0.5">{gimmickBadge}</span>
                          )}
                          <span>C{h.color}×{h.mag}</span>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 색상 깊이 범례 — wrap + 작은 칩 */}
          <div className="flex items-center gap-2 text-[10px] text-slate-500 mb-2 flex-wrap">
            <span className="flex items-center gap-1 shrink-0">
              <span className="w-3 h-3 inline-block border-2 border-black" /> d0=즉시발사
            </span>
            {Object.keys(queue.field_analysis?.color_depth ?? {}).map(Number).sort((a, b) => a - b).map((c) => (
              <span key={c} className="flex items-center gap-0.5 shrink-0">
                <span
                  className="w-3 h-3 inline-block rounded-sm border border-slate-300"
                  style={{ background: colorHex(c) }}
                />
                C{c}d{queue.field_analysis?.color_depth?.[c]}({queue.field_analysis?.color_darts?.[c]})
              </span>
            ))}
          </div>

          {/* 큐 기믹 요약 */}
          {queue.overlay && (
            <div className="text-[11px] text-slate-700 mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
              <span className="font-semibold text-slate-600">큐 기믹:</span>
              {(queue.overlay.hidden_ids?.length ?? 0) > 0 && (
                <span>❓ Hidden ×{queue.overlay.hidden_ids.length}</span>
              )}
              {(queue.overlay.linked_groups?.length ?? 0) > 0 && (
                <span>🔗 Linked {queue.overlay.linked_groups.length}묶음 [{queue.overlay.linked_groups.map(g => g.ids?.length).join(",")}]</span>
              )}
              {(queue.overlay.frozen?.length ?? 0) > 0 && (
                <span>❄ Frozen ×{queue.overlay.frozen.length} (HP {queue.overlay.frozen.map(f => f.health).join(",")})</span>
              )}
              {(queue.overlay.hidden_ids?.length ?? 0) === 0 && (queue.overlay.linked_groups?.length ?? 0) === 0 && (queue.overlay.frozen?.length ?? 0) === 0 && (
                <span className="text-slate-400">없음</span>
              )}
              {queue.step_c_validation?.intro_lv_filter && (
                <span className="text-amber-600">[도입 lv: {queue.step_c_validation.intro_lv_filter}만 활성]</span>
              )}
              {queue.step_c_validation && !queue.step_c_validation.multi_gimmick_pass && (
                <span className="text-red-600">⚠ {queue.step_c_validation.hard_fail_reason}</span>
              )}
            </div>
          )}

          {/* 필드 기믹 요약 — 풍선 보드 적용 (6종) */}
          {queue.field_overlay && (
            <div className="text-[11px] text-slate-700 mb-2 flex flex-wrap gap-x-3 gap-y-0.5 border-t border-slate-200 pt-1">
              <span className="font-semibold text-slate-600">필드 기믹:</span>
              {(queue.field_overlay.pinata_balloons?.length ?? 0) > 0 && (
                <span title={`life: ${queue.field_overlay.pinata_balloons.map(p => p.life).join(",")}`}>
                  🪵 Pinata ×{queue.field_overlay.pinata_balloons.length}
                </span>
              )}
              {(queue.field_overlay.wall_cells?.length ?? 0) > 0 && (
                <span>🧱 Wall ×{queue.field_overlay.wall_cells.length}</span>
              )}
              {(queue.field_overlay.hidden_balloons?.length ?? 0) > 0 && (
                <span>👻 Hidden Balloon ×{queue.field_overlay.hidden_balloons.length}</span>
              )}
              {(queue.field_overlay.pinata_box_areas?.length ?? 0) > 0 && (
                <span title={queue.field_overlay.pinata_box_areas.map(b => `[${b.areaW}×${b.areaH}, ${b.eggs?.length}색]`).join(" ")}>
                  📦 Target Box ×{queue.field_overlay.pinata_box_areas.length}
                </span>
              )}
              {(queue.field_overlay.frozen_layer_areas?.length ?? 0) > 0 && (
                <span title={`life: ${queue.field_overlay.frozen_layer_areas.map(f => f.life).join(",")}`}>
                  ❄️ Layer ×{queue.field_overlay.frozen_layer_areas.length}
                </span>
              )}
              {(queue.field_overlay.barricade_lines?.length ?? 0) > 0 && (
                <span>🚧 Barricade ×{queue.field_overlay.barricade_lines.length}</span>
              )}
              {(queue.field_overlay.pinata_balloons?.length ?? 0) === 0 &&
               (queue.field_overlay.wall_cells?.length ?? 0) === 0 &&
               (queue.field_overlay.hidden_balloons?.length ?? 0) === 0 &&
               (queue.field_overlay.pinata_box_areas?.length ?? 0) === 0 &&
               (queue.field_overlay.frozen_layer_areas?.length ?? 0) === 0 &&
               (queue.field_overlay.barricade_lines?.length ?? 0) === 0 && (
                <span className="text-slate-400">없음</span>
              )}
            </div>
          )}

          {/* 검증 경고 */}
          {queue.validation && !queue.validation.color_dart_match && (
            <div className="text-[11px] text-red-600">⚠ Hard Rule: color_darts 1:1 mismatch</div>
          )}
          {queue.validation && !queue.validation.cap20_backbone_pass && (
            <div className="text-[11px] text-amber-600">⚠ cap20 백본 없음</div>
          )}
          {queue.validation?.hard_fail_reasons && queue.validation.hard_fail_reasons.length > 0 && (
            <div className="text-[11px] text-red-600 break-all">
              ⚠ Hard Rule {queue.validation.retries}회 fail — {queue.validation.hard_fail_reasons[queue.validation.hard_fail_reasons.length - 1]}
            </div>
          )}

          {/* Seed 히스토리 — wrap */}
          <div className="mt-3 pt-2 border-t border-slate-200 flex items-center gap-1 text-[10px] text-slate-500 flex-wrap">
            <span className="shrink-0">seed:</span>
            {seedHistory.map((s) => (
              <button
                key={s}
                onClick={() => onClickHistorySeed(s)}
                className={`px-1.5 py-0.5 rounded font-mono shrink-0 ${
                  s === queue.seed ? "bg-blue-100 text-blue-700 border border-blue-300" : "bg-slate-100 hover:bg-slate-200"
                }`}
                title={`seed ${s} 복원`}
              >
                {s}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
