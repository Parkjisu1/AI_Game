"use client";
import { useEffect, useMemo, useState } from "react";
import { buildLevelJson, downloadLevelJson, levelFileName, type LevelLike } from "@/lib/levelJson";

interface Level extends LevelLike {
  _id?: string;
  level_number: number;
  field_rows: number;
  field_columns: number;
  status?: string;
  image_base64?: string;
  image_url?: string;
}

const STATUS_COLORS: Record<string, string> = {
  draft:     "bg-gray-100 text-gray-600",
  review:    "bg-blue-50 text-blue-600",
  generated: "bg-green-50 text-green-700",
  approved:  "bg-emerald-50 text-emerald-700",
};

export default function JsonVaultPage() {
  const [levels, setLevels] = useState<Level[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [showAll, setShowAll] = useState(false); // false = 이미지 생성된 레벨만
  const [openId, setOpenId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    fetch("/api/levels")
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setLevels(data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // 이미지 생성 또는 FieldMap이 채워진 레벨만 "준비됨"으로 간주
  function isReady(l: Level): boolean {
    return Boolean(l.image_base64 || l.image_url || l.field_map);
  }

  const filtered = useMemo(() => {
    return levels.filter((l) => {
      if (!showAll && !isReady(l)) return false;
      if (statusFilter !== "all" && (l.status || "draft") !== statusFilter) return false;
      if (query) {
        const q = query.toLowerCase();
        const hay = `${l.level_number} ${l.level_id || ""} ${l.designer_note || ""} ${l.purpose_type || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [levels, query, statusFilter, showAll]);

  const readyCount = useMemo(() => levels.filter(isReady).length, [levels]);

  function flash(msg: string) {
    setNotice(msg);
    setTimeout(() => setNotice(""), 1800);
  }

  async function copyJson(level: Level) {
    const text = JSON.stringify(buildLevelJson(level), null, 2);
    try {
      await navigator.clipboard.writeText(text);
      flash("JSON 복사됨");
    } catch {
      // Fallback for environments without clipboard API (older mobile browsers)
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        flash("JSON 복사됨");
      } catch {
        flash("복사 실패 — 직접 선택해 주세요");
      } finally {
        document.body.removeChild(ta);
      }
    }
  }

  async function shareJson(level: Level) {
    const text = JSON.stringify(buildLevelJson(level), null, 2);
    const fileName = levelFileName(level, "json");
    if (navigator.share && typeof File !== "undefined") {
      try {
        const file = new File([text], fileName, { type: "application/json" });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
          await navigator.share({ files: [file], title: fileName });
          return;
        }
        await navigator.share({ title: fileName, text });
        return;
      } catch {
        // 공유 취소 등 — fallback
      }
    }
    downloadLevelJson(level);
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="text-2xl font-bold">JSON 보관함</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            준비됨 {readyCount}개 · 전체 {levels.length}개 · 표시 {filtered.length}개
          </p>
        </div>
        {notice && (
          <span className="text-sm text-green-600 font-medium self-start sm:self-auto">
            {notice}
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        <label className="flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 self-start" style={{color:"#000"}}>
          <input
            type="checkbox"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-xs whitespace-nowrap">미생성 포함</span>
        </label>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="레벨 번호·노트·purpose 검색"
          className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 text-black"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg text-black bg-white"
        >
          <option value="all">전체 상태</option>
          <option value="draft">draft</option>
          <option value="review">review</option>
          <option value="generated">generated</option>
          <option value="approved">approved</option>
        </select>
      </div>

      {loading && (
        <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
          로딩 중...
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 bg-white rounded-xl border border-gray-200">
          <div className="text-4xl mb-3">📦</div>
          <p className="text-gray-500 text-sm">표시할 레벨이 없습니다</p>
          <p className="text-gray-400 text-xs mt-1">레벨 데이터 페이지에서 먼저 추가해 주세요</p>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map((level) => {
            const isOpen = openId === level.level_number;
            const status = level.status || "draft";
            return (
              <div
                key={level.level_number}
                className="bg-white rounded-xl border border-gray-200 overflow-hidden"
              >
                {/* Header row */}
                <div
                  className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => setOpenId(isOpen ? null : level.level_number)}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <span className="font-bold text-base shrink-0">
                      L{String(level.level_number).padStart(3, "0")}
                    </span>
                    <span className="text-xs text-gray-400 shrink-0">
                      {level.field_columns} × {level.field_rows}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${
                        STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {status}
                    </span>
                    {level.purpose_type && (
                      <span className="text-xs text-gray-500 truncate hidden sm:inline">
                        {level.purpose_type}
                      </span>
                    )}
                  </div>
                  <div
                    className="flex items-center gap-1.5 shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => copyJson(level)}
                      className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 active:bg-gray-100 transition-colors"
                      style={{ color: "#000" }}
                    >
                      복사
                    </button>
                    <button
                      onClick={() => shareJson(level)}
                      className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 active:bg-gray-100 transition-colors"
                      style={{ color: "#000" }}
                    >
                      공유
                    </button>
                    <button
                      onClick={() => downloadLevelJson(level)}
                      className="px-2.5 py-1.5 text-xs bg-black text-white rounded-lg hover:bg-gray-800 active:bg-gray-700 transition-colors"
                    >
                      다운로드
                    </button>
                    <button
                      onClick={() => setOpenId(isOpen ? null : level.level_number)}
                      className="px-2 py-1.5 text-xs text-gray-400"
                      aria-label="펼치기"
                    >
                      {isOpen ? "▲" : "▼"}
                    </button>
                  </div>
                </div>

                {/* Expanded JSON preview */}
                {isOpen && (
                  <div className="border-t border-gray-100 bg-gray-50 px-4 py-3">
                    <div className="text-xs text-gray-500 mb-2 font-mono">
                      {levelFileName(level, "json")}
                    </div>
                    <pre className="text-[11px] sm:text-xs font-mono bg-white border border-gray-200 rounded-lg p-3 overflow-x-auto max-h-[60vh] text-black">
{JSON.stringify(buildLevelJson(level), null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
