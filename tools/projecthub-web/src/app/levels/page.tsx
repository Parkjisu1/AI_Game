"use client";
import { useEffect, useMemo, useState, useCallback } from "react";
import QueuePreview, { type QueueData } from "@/components/QueuePreview";

interface LevelListItem {
  _id: string;
  name: string;
  task_id?: string;
  task_title?: string;
  created_by_email?: string;
  created_at: string;
  width: number;
  height: number;
  symmetry: string;
  palette: number[];
  per_color_count: Record<string, number>;
  seed: number;
  png_filename: string;
  validation?: {
    ok: boolean;
    filled_cells: number;
    empty_cells: number;
    color_counts: Record<string, number>;
  };
  mood?: string | null;
  team_id?: string | null;
  pattern_chosen?: string | null;
  user_score?: number | null;
}

interface ListResponse {
  levels: LevelListItem[];
  page: number;
  limit: number;
  total: number;
  pages: number;
  facets: {
    symmetries: { symmetry: string; count: number }[];
    authors: string[];
    moods?: { mood: string; count: number }[];
    styles?: { style: string; count: number }[];
    widths?: { width: number; count: number }[];
    heights?: { height: number; count: number }[];
    scores?: { score: number | null; count: number }[];
  };
}

const MOOD_META: Record<string, { label: string; icon: string; color: string }> = {
  warm:   { label: "Warm",   icon: "🔥", color: "border-red-400 bg-red-50" },
  cool:   { label: "Cool",   icon: "🌊", color: "border-blue-400 bg-blue-50" },
  pastel: { label: "Pastel", icon: "🌸", color: "border-pink-400 bg-pink-50" },
  vivid:  { label: "Vivid",  icon: "⚡", color: "border-yellow-400 bg-yellow-50" },
};

const STYLE_META: Record<string, { label: string; icon: string; color: string }> = {
  kaleidoscope: { label: "Kaleidoscope", icon: "🔮", color: "border-purple-400 bg-purple-50" },
  tile:         { label: "Tile",         icon: "🧱", color: "border-orange-400 bg-orange-50" },
  organic:      { label: "Organic",      icon: "🌀", color: "border-green-400 bg-green-50" },
  motif:        { label: "Motif",        icon: "🔷", color: "border-indigo-400 bg-indigo-50" },
};

interface LevelDetail extends LevelListItem {
  cells: number[][];
}

const BALLOONFLOW_COLORS_HEX = [
  "#fc6aaf", "#50e8f6", "#8950f8", "#fed555", "#73fe66", "#fda14c",
  "#ffffff", "#414141", "#6ea8fa", "#39ae2e", "#fc5e5e", "#326bf8",
  "#3aa58b", "#e7a7fa", "#b7c7fb", "#6a4a30", "#fee3a9", "#fdb7c1",
  "#9e3d5e", "#a7dd94", "#592e7e", "#dc7881", "#d9d9e7", "#6f727f",
];
const BALLOONFLOW_COLOR_NAMES = [
  "HotPink", "Cyan", "Purple", "Yellow", "Green", "Orange",
  "White", "DarkGray", "SkyBlue", "Forest", "Red", "Blue",
  "Teal", "Lavender", "Periwinkle", "Brown", "Cream", "Pink",
  "Wine", "Mint", "Indigo", "Rose", "Silver", "Gray",
];

const SYMMETRY_LABEL: Record<string, string> = {
  "none": "무대칭",
  "2-fold-h": "좌우 대칭",
  "2-fold-v": "상하 대칭",
  "4-fold": "4-fold (상하+좌우)",
  "diagonal": "대각선",
  "4-fold-rot": "회전 대칭 (만화경)",
};

function ColorDot({ idx, count }: { idx: number; count?: number }) {
  const hex = BALLOONFLOW_COLORS_HEX[idx] || "#ff00ff";
  const name = BALLOONFLOW_COLOR_NAMES[idx] || "?";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-zinc-300 bg-white px-1.5 py-0.5 text-[10px]"
      title={`${idx}: ${name}${count !== undefined ? ` (${count})` : ""}`}
    >
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: hex }} />
      {count !== undefined && <span className="text-zinc-600">{count}</span>}
    </span>
  );
}

export default function LevelsPage() {
  const [data, setData] = useState<ListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [symmetry, setSymmetry] = useState("");
  const [mood, setMood] = useState("");
  const [style, setStyle] = useState("");
  const [unrated, setUnrated] = useState(false);
  const [widthF, setWidthF] = useState("");
  const [heightF, setHeightF] = useState("");
  const [minScore, setMinScore] = useState(0);  // 0 = 전체, 1-5 = 그 이상
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [savingId, setSavingId] = useState<string | null>(null);

  // 상세 모달
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LevelDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // A+C: BL Lv 매핑 + 동기화 상태
  const [targetLevel, setTargetLevel] = useState<string>("");
  const [downloadDifficulty, setDownloadDifficulty] = useState<string>("normal");
  const [lastSeed, setLastSeed] = useState<number | null>(null);

  // 모달 닫힐 때 매핑 초기화
  useEffect(() => {
    if (!openId) {
      setTargetLevel("");
      setLastSeed(null);
    }
  }, [openId]);

  // 다운로드 URL 빌더 — Unity Importer 호환 (PixelForge snake_case 포맷)
  const buildDownloadUrl = (id: string): string => {
    const params = new URLSearchParams();
    params.set("format", "pixelforge");  // ⭐ Unity LevelJsonImporterWindow 호환
    params.set("download", "1");
    if (targetLevel.trim()) {
      const n = parseInt(targetLevel.trim(), 10);
      if (Number.isFinite(n) && n > 0) params.set("targetLevel", String(n));
    }
    if (lastSeed != null) params.set("seed", String(lastSeed));
    return `/api/levels/${id}/export?${params.toString()}`;
  };

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("limit", "24");
      if (q) params.set("q", q);
      if (symmetry) params.set("symmetry", symmetry);
      if (mood) params.set("mood", mood);
      if (style) params.set("style", style);
      if (unrated) params.set("unrated", "1");
      if (widthF) params.set("width", widthF);
      if (heightF) params.set("height", heightF);
      if (minScore >= 1 && minScore <= 5) params.set("min_score", String(minScore));
      const r = await fetch(`/api/levels?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = (await r.json()) as ListResponse;
      setData(j);
      setErr("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, [page, q, symmetry, mood, style, unrated, widthF, heightF, minScore]);

  // 카드의 별점 입력 — 1~5 → PATCH
  const setStar = useCallback(async (id: string, score: number) => {
    setSavingId(id);
    try {
      const r = await fetch(`/api/levels/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_score: score }),
      });
      if (r.ok) {
        // 로컬 state 업데이트 (full refetch 안 하고 부분 갱신)
        setData((prev) => prev ? {
          ...prev,
          levels: prev.levels.map((l) => l._id === id ? { ...l, user_score: score } : l),
        } : prev);
      }
    } finally {
      setSavingId(null);
    }
  }, []);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  // URL hash로 #level=<id> 진입 지원
  useEffect(() => {
    const m = window.location.hash.match(/^#level=([a-f0-9]{24})/i);
    if (m) setOpenId(m[1]);
    const onHash = () => {
      const m2 = window.location.hash.match(/^#level=([a-f0-9]{24})/i);
      setOpenId(m2 ? m2[1] : null);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // 상세 fetch
  useEffect(() => {
    if (!openId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    fetch(`/api/levels/${openId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => setDetail(j))
      .catch((e) => setErr(String(e)))
      .finally(() => setDetailLoading(false));
  }, [openId]);

  const close = () => {
    setOpenId(null);
    setDetail(null);
    if (window.location.hash) {
      history.pushState("", document.title, window.location.pathname + window.location.search);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold">🧩 레벨 갤러리</h1>
          <p className="text-sm text-gray-500 mt-1 leading-relaxed">
            design/level 분과가 생성한 격자 패턴 — JSON 다운로드 → Unity import 가능
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a href="/gallery" className="text-xs text-zinc-500 hover:underline">
            ← 아트 갤러리
          </a>
          <a href="/tasks" className="text-xs text-zinc-500 hover:underline">
            태스크 보드
          </a>
        </div>
      </div>

      {/* Mood tabs */}
      {data?.facets.moods && data.facets.moods.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          <span className="self-center text-[11px] text-zinc-500">mood:</span>
          <button
            onClick={() => { setMood(""); setPage(1); }}
            className={`rounded-lg border px-3 py-1.5 text-xs ${
              mood === ""
                ? "border-zinc-800 bg-zinc-800 text-white"
                : "border-zinc-300 bg-white hover:bg-zinc-50"
            }`}
          >
            모든 mood
          </button>
          {data.facets.moods.map((m) => {
            const meta = MOOD_META[m.mood] || { label: m.mood, icon: "?", color: "" };
            const active = mood === m.mood;
            return (
              <button
                key={m.mood}
                onClick={() => { setMood(m.mood); setPage(1); }}
                className={`rounded-lg border-2 px-3 py-1.5 text-xs font-medium ${
                  active ? meta.color : "border-zinc-200 bg-white hover:bg-zinc-50"
                }`}
              >
                {meta.icon} {meta.label} <span className="ml-1 text-[10px] text-zinc-500">({m.count})</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Style tabs (batch v2) */}
      {data?.facets.styles && data.facets.styles.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          <span className="self-center text-[11px] text-zinc-500">style:</span>
          <button
            onClick={() => { setStyle(""); setPage(1); }}
            className={`rounded-lg border px-3 py-1.5 text-xs ${
              style === ""
                ? "border-zinc-800 bg-zinc-800 text-white"
                : "border-zinc-300 bg-white hover:bg-zinc-50"
            }`}
          >
            모든 style
          </button>
          {data.facets.styles.map((s) => {
            const meta = STYLE_META[s.style] || { label: s.style, icon: "?", color: "" };
            const active = style === s.style;
            return (
              <button
                key={s.style}
                onClick={() => { setStyle(s.style); setPage(1); }}
                className={`rounded-lg border-2 px-3 py-1.5 text-xs font-medium ${
                  active ? meta.color : "border-zinc-200 bg-white hover:bg-zinc-50"
                }`}
              >
                {meta.icon} {meta.label} <span className="ml-1 text-[10px] text-zinc-500">({s.count})</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="이름·task title 검색"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={symmetry}
          onChange={(e) => { setSymmetry(e.target.value); setPage(1); }}
          className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">모든 대칭</option>
          {data?.facets.symmetries.map((s) => (
            <option key={s.symmetry} value={s.symmetry}>
              {SYMMETRY_LABEL[s.symmetry] || s.symmetry} ({s.count})
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-zinc-600">
          <input
            type="checkbox"
            checked={unrated}
            onChange={(e) => { setUnrated(e.target.checked); setPage(1); }}
          />
          미평가만
        </label>
        {/* 가로 사이즈 dropdown */}
        <select
          value={widthF}
          onChange={(e) => { setWidthF(e.target.value); setPage(1); }}
          className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">가로 ─ 전체</option>
          {data?.facets.widths?.map((w) => (
            <option key={w.width} value={String(w.width)}>가로 {w.width} ({w.count})</option>
          ))}
        </select>
        {/* 세로 사이즈 dropdown */}
        <select
          value={heightF}
          onChange={(e) => { setHeightF(e.target.value); setPage(1); }}
          className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">세로 ─ 전체</option>
          {data?.facets.heights?.map((h) => (
            <option key={h.height} value={String(h.height)}>세로 {h.height} ({h.count})</option>
          ))}
        </select>
        {/* 별점 필터 */}
        <div className="flex items-center gap-1 rounded-lg border border-zinc-300 bg-white px-2 py-1">
          <span className="text-[11px] text-zinc-500">별점 ≥</span>
          {[0, 1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => { setMinScore(n); setPage(1); }}
              className={`rounded px-1.5 py-0.5 text-xs ${
                minScore === n
                  ? "bg-yellow-400 text-white font-bold"
                  : "text-zinc-500 hover:bg-yellow-50"
              }`}
              title={n === 0 ? "전체" : `${n}점 이상`}
            >
              {n === 0 ? "전체" : `${n}★`}
            </button>
          ))}
        </div>
        {data && (
          <span className="text-xs text-zinc-500">
            총 {data.total}건 · {data.page}/{data.pages || 1} 페이지
          </span>
        )}
      </div>

      {loading && <div className="py-12 text-center text-zinc-400">로딩 중...</div>}
      {err && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">에러: {err}</div>}

      {data && data.levels.length === 0 && !loading && (
        <div className="rounded-xl border border-dashed border-zinc-300 py-16 text-center text-zinc-500">
          아직 레벨이 없습니다 — Tasks 에서 [level] 태그로 첫 레벨을 만들어보세요.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data?.levels.map((lv) => (
          <div
            key={lv._id}
            className="group overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm transition hover:border-indigo-400 hover:shadow-md"
          >
            <div
              role="button"
              tabIndex={0}
              onClick={() => { setOpenId(lv._id); history.pushState("", document.title, `${window.location.pathname}#level=${lv._id}`); }}
              className="block aspect-square w-full overflow-hidden bg-zinc-100 cursor-pointer"
            >
              <img
                src={`/api/levels/image/${lv.png_filename}`}
                alt={lv.name}
                className="h-full w-full object-contain transition group-hover:scale-105"
                loading="lazy"
              />
            </div>
            <div className="space-y-1.5 p-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="truncate text-sm font-semibold">{lv.name}</h3>
                <span className="shrink-0 rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700">
                  {lv.width}×{lv.height}
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
                {lv.mood && MOOD_META[lv.mood] && (
                  <span className={`rounded border px-1 py-0.5 text-[10px] ${MOOD_META[lv.mood].color}`}>
                    {MOOD_META[lv.mood].icon}{MOOD_META[lv.mood].label}
                  </span>
                )}
                <span className="truncate">{lv.pattern_chosen || lv.symmetry}</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {(lv.palette ?? []).map((c) => (
                  <ColorDot
                    key={c}
                    idx={c}
                    count={(lv.per_color_count ?? {})[String(c)] ?? (lv.per_color_count ?? {})[c as unknown as string]}
                  />
                ))}
              </div>
              {/* 별점 입력 */}
              <div className="flex items-center gap-0.5 pt-1">
                {[1, 2, 3, 4, 5].map((n) => {
                  const filled = (lv.user_score || 0) >= n;
                  return (
                    <button
                      key={n}
                      disabled={savingId === lv._id}
                      onClick={(e) => { e.stopPropagation(); setStar(lv._id, n); }}
                      className={`text-lg leading-none transition-transform hover:scale-110 ${
                        filled ? "text-yellow-400" : "text-zinc-300 hover:text-yellow-300"
                      } disabled:opacity-50`}
                      title={`${n}점`}
                    >
                      ★
                    </button>
                  );
                })}
                {lv.user_score ? (
                  <span className="ml-1 text-[10px] text-zinc-500">{lv.user_score}/5</span>
                ) : (
                  <span className="ml-1 text-[10px] text-zinc-400">미평가</span>
                )}
              </div>
              {lv.task_title && (
                <div className="truncate text-[11px] text-zinc-400">
                  📋 {lv.task_title}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-lg border border-zinc-300 px-3 py-1 text-sm disabled:opacity-40"
          >
            ←
          </button>
          <span className="text-sm text-zinc-600">{page} / {data.pages}</span>
          <button
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            disabled={page >= data.pages}
            className="rounded-lg border border-zinc-300 px-3 py-1 text-sm disabled:opacity-40"
          >
            →
          </button>
        </div>
      )}

      {/* Detail modal */}
      {openId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={close}>
          <div
            className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {detailLoading && <div className="p-12 text-center text-zinc-400">로딩 중...</div>}
            {detail && (
              <div className="grid gap-6 p-6 md:grid-cols-[1fr_320px]">
                <div>
                  <img
                    src={`/api/levels/image/${detail.png_filename}`}
                    alt={detail.name}
                    className="w-full rounded-lg border border-zinc-200"
                  />
                </div>
                <div className="space-y-4">
                  <div>
                    <h2 className="text-lg font-bold">{detail.name}</h2>
                    <p className="text-xs text-zinc-500">
                      {new Date(detail.created_at).toLocaleString("ko-KR")}
                      {detail.created_by_email && ` · ${detail.created_by_email}`}
                    </p>
                  </div>
                  <dl className="space-y-2 text-sm">
                    <div className="flex justify-between border-b border-zinc-100 pb-1">
                      <dt className="text-zinc-500">크기</dt>
                      <dd className="font-mono">{detail.width} × {detail.height}</dd>
                    </div>
                    <div className="flex justify-between border-b border-zinc-100 pb-1">
                      <dt className="text-zinc-500">대칭</dt>
                      <dd>{SYMMETRY_LABEL[detail.symmetry] || detail.symmetry}</dd>
                    </div>
                    <div className="flex justify-between border-b border-zinc-100 pb-1">
                      <dt className="text-zinc-500">시드</dt>
                      <dd className="font-mono">{detail.seed}</dd>
                    </div>
                    {detail.validation && (
                      <>
                        <div className="flex justify-between border-b border-zinc-100 pb-1">
                          <dt className="text-zinc-500">채워진 셀</dt>
                          <dd className="font-mono">
                            {detail.validation.filled_cells} / {detail.validation.filled_cells + detail.validation.empty_cells}
                          </dd>
                        </div>
                        <div className="flex justify-between border-b border-zinc-100 pb-1">
                          <dt className="text-zinc-500">검증</dt>
                          <dd className={detail.validation.ok ? "text-emerald-600" : "text-red-600"}>
                            {detail.validation.ok ? "✓ 통과" : "✗ 실패"}
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>

                  <div>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                      Palette ({(detail.palette ?? []).length}색)
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {(detail.palette ?? []).map((c) => (
                        <ColorDot
                          key={c}
                          idx={c}
                          count={(detail.per_color_count ?? {})[String(c)] ?? (detail.per_color_count ?? {})[c as unknown as string]}
                        />
                      ))}
                    </div>
                  </div>

                  {detail.task_title && (
                    <div className="rounded-lg bg-indigo-50 p-3 text-xs">
                      <div className="text-indigo-700">📋 {detail.task_title}</div>
                      {detail.task_id && (
                        <a
                          href={`/tasks?id=${detail.task_id}`}
                          className="mt-1 inline-block text-indigo-600 underline"
                        >
                          태스크 보기 →
                        </a>
                      )}
                    </div>
                  )}

                  {/* A: BL Lv 매핑 + 다운로드 옵션 */}
                  <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2">
                    <div className="text-xs font-semibold text-zinc-700">다운로드 옵션</div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-zinc-600 w-24 shrink-0">BL Lv 매핑</label>
                      <input
                        type="number"
                        min={1}
                        max={300}
                        placeholder="(없음)"
                        value={targetLevel}
                        onChange={(e) => setTargetLevel(e.target.value)}
                        className="flex-1 px-2 py-1 text-xs border border-zinc-300 rounded font-mono"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-zinc-600 w-24 shrink-0">난이도</label>
                      <select
                        value={downloadDifficulty}
                        onChange={(e) => setDownloadDifficulty(e.target.value)}
                        className="flex-1 px-2 py-1 text-xs border border-zinc-300 rounded"
                      >
                        <option value="tutorial">Tutorial</option>
                        <option value="rest">Rest</option>
                        <option value="normal">Normal</option>
                        <option value="hard">Hard</option>
                        <option value="super_hard">Super Hard</option>
                      </select>
                    </div>
                    {lastSeed != null && (
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-zinc-600 w-24 shrink-0">seed</label>
                        <span className="font-mono text-xs text-zinc-500">{lastSeed}</span>
                        <button
                          onClick={() => setLastSeed(null)}
                          className="ml-auto text-[10px] text-zinc-400 hover:text-zinc-600"
                        >
                          (초기화)
                        </button>
                      </div>
                    )}
                    <p className="text-[10px] text-zinc-500 leading-relaxed">
                      • <b>BL Lv</b> 입력 시 → 해당 BL 레벨의 큐 기믹 (Hidden/Linked/Frozen Dart Box) 자동 적용<br/>
                      • 없으면 큐만 생성, 기믹 0<br/>
                      • 미리보기와 동일 결과 다운로드 (seed 일치)
                    </p>
                  </div>

                  <div className="flex flex-col gap-2">
                    <a
                      href={buildDownloadUrl(detail._id)}
                      className="rounded-lg bg-emerald-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-emerald-500"
                    >
                      🎈 BalloonFlow JSON 다운로드
                      {targetLevel.trim() && ` (Lv.${targetLevel.trim()} 기믹 포함)`}
                    </a>
                    <a
                      href={`/api/levels/${detail._id}?download=1`}
                      className="rounded-lg bg-indigo-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-indigo-500"
                    >
                      📥 격자 JSON 다운로드 (raw cells)
                    </a>
                    <a
                      href={`/api/levels/image/${detail.png_filename}`}
                      download={`${detail.name}.png`}
                      className="rounded-lg border border-zinc-300 px-4 py-2 text-center text-sm hover:bg-zinc-50"
                    >
                      🖼 PNG 다운로드
                    </a>
                  </div>

                  <QueuePreview
                    mode="projecthub"
                    paletteMode="balloonflow_24"
                    initialDifficulty="normal"
                    fetchQueue={async (seed, diff) => {
                      const url = new URL(
                        `/api/levels/${detail._id}/export`,
                        window.location.origin,
                      );
                      url.searchParams.set("format", "balloonflow");
                      const useDiff = diff ?? "normal";
                      url.searchParams.set("difficulty", useDiff);
                      // A+C: BL Lv 매핑 동기화
                      if (targetLevel.trim()) {
                        const n = parseInt(targetLevel.trim(), 10);
                        if (Number.isFinite(n) && n > 0) {
                          url.searchParams.set("targetLevel", String(n));
                        }
                      }
                      if (seed != null) url.searchParams.set("seed", String(seed));
                      const r = await fetch(url.toString());
                      if (!r.ok) throw new Error(`HTTP ${r.status}`);
                      const j = await r.json();
                      const m = j._pixelflow_meta;
                      // 다운로드 동기 — 미리보기에 사용된 seed/difficulty 기록
                      setLastSeed(m.seed);
                      setDownloadDifficulty(useDiff);
                      const qd: QueueData = {
                        holders: (j.holders ?? []).map((h: { color: number; magazineCount: number }) => ({
                          color: h.color, mag: h.magazineCount,
                        })),
                        queue_columns: j.queueColumns,
                        recommended_queue_columns: m.recommended_queue_columns,
                        field_analysis: m.field_analysis,
                        difficulty_score: m.difficulty_score,
                        validation: m.validation,
                        seed: m.seed,
                        difficulty: m.source_difficulty,
                        overlay: m.overlay,
                        step_c_validation: m.step_c_validation,
                        field_overlay: m.field_overlay,
                        field_gimmick_validation: m.field_gimmick_validation,
                      };
                      return qd;
                    }}
                  />

                  <details className="rounded-lg border border-zinc-200 p-2 text-xs">
                    <summary className="cursor-pointer font-medium">BalloonFlow / Unity import 가이드</summary>
                    <div className="mt-2 space-y-2 text-zinc-600">
                      <p><b>🎈 BalloonFlow JSON</b>: cells → balloons + 큐 자동생성된 완성 Level JSON. 그대로 BalloonFlow에 import 가능.</p>
                      <p>메타 오버라이드: URL에 쿼리 추가 — <code className="rounded bg-zinc-100 px-1">?format=balloonflow&amp;download=1&amp;targetLevel=10&amp;packageId=1&amp;pos=10&amp;railCapacity=40&amp;queueColumns=3&amp;difficulty=normal&amp;flipY=1</code></p>
                      <p><code className="rounded bg-zinc-100 px-1">targetLevel=N</code> 지정 시 <code className="rounded bg-zinc-100 px-1">pixelforge_levels</code>의 메타(pkg/pos/rail/queue/gimmick)를 자동 매칭. 큐는 <code className="rounded bg-zinc-100 px-1">BalloonFlow_큐생성기_명세</code>의 STEP A(70/30 분해)로 생성.</p>
                      <p><b>📥 격자 JSON</b>: raw cells (-1=empty, 0..23=color index). Unity 직접 import 또는 다른 어댑터용.</p>
                    </div>
                  </details>

                  <button
                    onClick={close}
                    className="w-full rounded-lg border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-50"
                  >
                    닫기
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
