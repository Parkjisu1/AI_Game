"use client";
import { useEffect, useMemo, useState } from "react";
import { downloadLevelJson, levelFileName } from "@/lib/levelJson";
import { PALETTE_HEX, COLOR_NAMES, parseColorDist } from "@/lib/palette";

const PAGE_SIZE = 30;

interface AltMeta {
  source?: string;
  generated_at?: string;
  track?: "motif" | "pattern";
  raw_response?: string;
  parsed_row_count?: number;
  expected_rows?: number;
  row_lengths?: number[];
  width?: number;
  height?: number;
  pixels_per_cell?: number;
}

interface Level {
  _id?: string;
  level_number: number;
  field_rows: number;
  field_columns: number;
  image_base64?: string;
  image_base64_alt?: string;
  image_url?: string;
  designer_note?: string;
  color_distribution?: string;
  field_map?: string;
  status?: string;
  alt_meta?: AltMeta;
  [key: string]: unknown;
}

export default function GalleryPage() {
  const [levels, setLevels] = useState<Level[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalLevel, setModalLevel] = useState<Level | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [selectedNums, setSelectedNums] = useState<Set<number>>(new Set());
  const [regenerating, setRegenerating] = useState(false);
  const [regenProgress, setRegenProgress] = useState("");
  const [showAlt, setShowAlt] = useState(false); // 모달에서 alt 이미지 보기
  const [modalPalette, setModalPalette] = useState<number[]>([]);
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState(1);

  // 페이지네이션: 30개씩 보기
  const totalPages = Math.max(1, Math.ceil(levels.length / PAGE_SIZE));
  const pagedLevels = useMemo(
    () => levels.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [levels, page]
  );

  // levels가 바뀌거나 페이지가 범위 밖이 되면 1페이지로
  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [levels.length, page, totalPages]);

  function toggleSelect(num: number) {
    setSelectedNums((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedNums.size === levels.length) setSelectedNums(new Set());
    else setSelectedNums(new Set(levels.map((l) => l.level_number)));
  }

  useEffect(() => {
    fetch("/api/levels")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setLevels(data.filter((l: Level) => l.image_base64 || l.image_base64_alt));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function imgSrc(level: Level, preferAlt: boolean = false) {
    if (preferAlt && level.image_base64_alt) return `data:image/png;base64,${level.image_base64_alt}`;
    if (level.image_url) return level.image_url;
    if (level.image_base64) return `data:image/png;base64,${level.image_base64}`;
    if (level.image_base64_alt) return `data:image/png;base64,${level.image_base64_alt}`;
    return "";
  }

  function downloadImage(level: Level) {
    const src = imgSrc(level);
    if (!src) return;
    const a = document.createElement("a");
    a.href = src;
    a.download = levelFileName(level, "png");
    a.click();
  }

  function downloadJson(level: Level) {
    downloadLevelJson(level);
  }

  async function batchDownload(targets: Level[], includeJson: boolean) {
    setDownloading(true);
    for (const level of targets) {
      downloadImage(level);
      await new Promise((r) => setTimeout(r, 120));
      if (includeJson) {
        downloadJson(level);
        await new Promise((r) => setTimeout(r, 120));
      }
    }
    setDownloading(false);
  }

  async function downloadAll() {
    await batchDownload(levels, false);
  }

  async function downloadSelected() {
    const targets = levels.filter((l) => selectedNums.has(l.level_number));
    await batchDownload(targets, true);
  }

  function flash(msg: string) {
    setNotice(msg);
    setTimeout(() => setNotice(""), 2500);
  }

  async function regeneratePixelLabPalette(level: Level, paletteIds: number[]) {
    const apiKey = typeof window !== "undefined" ? localStorage.getItem("pixellab_api_key") : null;
    if (!apiKey) { flash("PixelLab API Key 먼저 설정"); return; }
    if (paletteIds.length === 0) { flash("색상을 1개 이상 선택"); return; }
    setRegenerating(true);
    setRegenProgress(`Level ${level.level_number} (PixelLab recolor)`);
    try {
      const res = await fetch("/api/regenerate-pixellab", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-pixellab-key": apiKey },
        body: JSON.stringify({ level_number: level.level_number, palette_ids: paletteIds }),
      });
      const data = await res.json();
      if (!data.ok) { flash(`실패: ${data.error}`); return; }
      flash("PixelLab 재생성 완료");
      // 갤러리 + 모달 갱신
      const fresh = await fetch("/api/levels").then((r) => r.json());
      if (Array.isArray(fresh)) {
        setLevels(fresh.filter((l: Level) => l.image_base64 || l.image_base64_alt));
        const updated = fresh.find((l: Level) => l.level_number === level.level_number);
        if (updated) {
          setModalLevel(updated);
          setShowAlt(true);
        }
      }
    } catch (e) {
      flash(`오류: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setRegenerating(false);
      setRegenProgress("");
    }
  }

  // 모달 열 때 그 레벨의 색상으로 modalPalette 초기화
  function openModal(level: Level) {
    const ids = parseColorDist(String(level.color_distribution || ""));
    setModalPalette(ids);
    setShowAlt(false);
    setModalLevel(level);
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="text-2xl font-bold">갤러리</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            생성된 레벨 이미지 {levels.length}개{selectedNums.size > 0 ? ` · 선택 ${selectedNums.size}` : ""}
          </p>
        </div>
        {levels.length > 0 && (
          <div className="flex flex-wrap gap-2 self-start sm:self-auto">
            {notice && <span className="text-xs text-green-600 self-center font-medium">{notice}</span>}
            {regenerating && <span className="text-xs text-blue-500 self-center">{regenProgress}</span>}
            <button
              onClick={toggleSelectAll}
              className="px-3 py-2 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              style={{color:"#000"}}
            >
              {selectedNums.size === levels.length ? "선택 해제" : "전체 선택"}
            </button>
            {selectedNums.size > 0 && (
              <button
                onClick={downloadSelected}
                disabled={downloading}
                className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40 transition-colors"
              >
                {downloading ? "다운로드 중..." : `선택 다운로드 (${selectedNums.size})`}
              </button>
            )}
            <button
              onClick={downloadAll}
              disabled={downloading}
              className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 transition-colors"
              style={{color:"#000"}}
            >
              {downloading ? "..." : `전체 (${levels.length})`}
            </button>
          </div>
        )}
      </div>

      {loading && (
        <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
          로딩 중...
        </div>
      )}

      {!loading && levels.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 bg-white rounded-xl border border-gray-200">
          <div className="text-4xl mb-3">🖼</div>
          <p className="text-gray-500 text-sm">생성된 이미지가 없습니다</p>
          <p className="text-gray-400 text-xs mt-1">이미지 생성 페이지에서 레벨 이미지를 만들어보세요</p>
        </div>
      )}

      {!loading && levels.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
          {pagedLevels.map((level) => {
            const isSelected = selectedNums.has(level.level_number);
            return (
            <div
              key={level.level_number}
              className={`bg-white rounded-xl border overflow-hidden hover:shadow-md transition-shadow group ${
                isSelected ? "border-black ring-2 ring-black/10" : "border-gray-200"
              }`}
            >
              {/* Image */}
              <div
                className="relative bg-gray-100 cursor-pointer overflow-hidden"
                style={{ aspectRatio: "1 / 1" }}
                onClick={() => openModal(level)}
              >
                {/* Checkbox overlay */}
                <label
                  className="absolute top-2 left-2 z-10 bg-white/90 backdrop-blur rounded-md p-1 cursor-pointer shadow-sm"
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(level.level_number)}
                    className="w-4 h-4 cursor-pointer block"
                    aria-label={`Level ${level.level_number} 선택`}
                  />
                </label>
                <img
                  src={imgSrc(level)}
                  alt={`Level ${level.level_number}`}
                  className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-200"
                  style={{ imageRendering: "pixelated" }}
                />
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
                  <span className="opacity-0 group-hover:opacity-100 text-white text-xs font-medium bg-black/60 px-2 py-1 rounded transition-opacity">
                    확대 보기
                  </span>
                </div>
              </div>

              {/* Info */}
              <div className="p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-sm">Level {level.level_number}</span>
                  <span className="text-xs text-gray-400">
                    {level.field_columns} × {level.field_rows}
                  </span>
                </div>
                {level.designer_note && (
                  <p className="text-xs text-gray-400 truncate mb-2">{level.designer_note}</p>
                )}
                <div className="flex gap-1">
                  <button
                    onClick={() => downloadImage(level)}
                    className="flex-1 text-xs py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50"
                    style={{color:"#000"}}
                  >
                    이미지
                  </button>
                  <button
                    onClick={() => downloadJson(level)}
                    className="flex-1 text-xs py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50"
                    style={{color:"#000"}}
                  >
                    JSON
                  </button>
                  <button
                    onClick={async () => {
                      if (!confirm(`Level ${level.level_number} 삭제?`)) return;
                      await fetch(`/api/levels/${level._id || level.level_number}`, { method: "DELETE" });
                      setLevels((prev) => prev.filter((l) => l.level_number !== level.level_number));
                    }}
                    className="text-xs py-1.5 px-2 border border-red-200 rounded-lg hover:bg-red-50"
                    style={{color:"#dc2626"}}
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-center gap-1 mt-6 flex-wrap">
          <button
            onClick={() => setPage(1)}
            disabled={page === 1}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-30"
            style={{ color: "#000" }}
          >
            ≪
          </button>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-30"
            style={{ color: "#000" }}
          >
            ←
          </button>
          <span className="px-3 py-1.5 text-xs" style={{ color: "#000" }}>
            {page} / {totalPages} <span className="text-gray-400">({levels.length}개)</span>
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-30"
            style={{ color: "#000" }}
          >
            →
          </button>
          <button
            onClick={() => setPage(totalPages)}
            disabled={page === totalPages}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-30"
            style={{ color: "#000" }}
          >
            ≫
          </button>
        </div>
      )}

      {/* Full-size Modal */}
      {modalLevel && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-3 sm:p-6 overflow-y-auto"
          onClick={() => setModalLevel(null)}
        >
          <div
            className="bg-white rounded-2xl overflow-hidden shadow-2xl w-full max-w-3xl my-4"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
              <div>
                <span className="font-bold">Level {modalLevel.level_number}</span>
                <span className="text-sm text-gray-400 ml-3">
                  {modalLevel.field_columns} × {modalLevel.field_rows}
                </span>
                {modalLevel.image_base64_alt && (
                  <button
                    onClick={() => setShowAlt(!showAlt)}
                    className={`ml-3 text-xs px-2 py-0.5 rounded-full border ${showAlt ? "bg-purple-100 border-purple-300 text-purple-700" : "border-gray-200 text-gray-600"}`}
                  >
                    {showAlt ? "재생성 (alt)" : "원본"}
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => downloadImage(modalLevel)}
                  className="px-3 py-1.5 text-sm bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
                >
                  다운로드
                </button>
                <button
                  onClick={() => setModalLevel(null)}
                  className="text-gray-400 hover:text-gray-600 text-xl leading-none px-2"
                >
                  ×
                </button>
              </div>
            </div>

            {/* Image */}
            <div className="p-6 bg-gray-50 flex items-center justify-center" style={{ minHeight: 360 }}>
              <img
                src={imgSrc(modalLevel, showAlt)}
                alt={`Level ${modalLevel.level_number} full`}
                className="max-w-full max-h-[50vh] object-contain rounded"
                style={{ imageRendering: "pixelated" }}
              />
            </div>

            {/* Note */}
            {modalLevel.designer_note && (
              <div className="px-5 py-3 border-t border-gray-100 text-sm text-gray-600">
                <span className="font-semibold">Note: </span>{modalLevel.designer_note}
              </div>
            )}

            {/* Palette swap UI */}
            <div className="px-5 py-4 border-t border-gray-100">
              <div className="text-xs font-bold mb-2" style={{color:"#000"}}>
                🎨 색상 팔레트 ({modalPalette.length}/28) — 클릭으로 추가/제거
              </div>
              <div className="flex flex-wrap gap-1 mb-3">
                {Object.entries(PALETTE_HEX).map(([id, hex]) => {
                  const numId = parseInt(id);
                  const isOn = modalPalette.includes(numId);
                  return (
                    <button
                      key={id}
                      onClick={() =>
                        setModalPalette((prev) =>
                          isOn ? prev.filter((c) => c !== numId) : [...prev, numId]
                        )
                      }
                      className={`w-7 h-7 rounded border-2 flex items-center justify-center text-[8px] font-bold transition-all ${
                        isOn ? "border-black scale-110 shadow" : "border-gray-200 opacity-60 hover:opacity-100"
                      }`}
                      style={{ backgroundColor: hex, color: numId === 7 || numId === 23 || numId === 17 ? "#000" : "#fff" }}
                      title={`c${id} ${COLOR_NAMES[numId] || ""}`}
                    >
                      {id}
                    </button>
                  );
                })}
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => regeneratePixelLabPalette(modalLevel, modalPalette)}
                  disabled={regenerating || modalPalette.length === 0}
                  className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40"
                  title="PixelLab으로 선택한 팔레트로 재생성"
                >
                  {regenerating ? "..." : "🪝 PixelLab 재생성"}
                </button>
                {modalLevel.image_base64_alt && (
                  <button
                    onClick={async () => {
                      if (!confirm("alt 이미지 삭제? (원본만 남음)")) return;
                      try {
                        const res = await fetch("/api/levels/clear-alt", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ level_number: modalLevel.level_number }),
                        });
                        const j = await res.json();
                        if (!j.ok) {
                          flash(`삭제 실패: ${j.error || "unknown"}`);
                          return;
                        }
                        flash("alt 삭제 완료");
                        // 갤러리 + 모달 갱신
                        const fresh = await fetch("/api/levels").then((r) => r.json());
                        if (Array.isArray(fresh)) {
                          setLevels(fresh.filter((l: Level) => l.image_base64 || l.image_base64_alt));
                          const updated = fresh.find((l: Level) => l.level_number === modalLevel.level_number);
                          if (updated) {
                            setModalLevel(updated);
                            setShowAlt(false);
                          }
                        }
                      } catch (e) {
                        flash(`오류: ${e instanceof Error ? e.message : "unknown"}`);
                      }
                    }}
                    className="text-xs text-red-600 hover:underline ml-auto self-center"
                  >
                    alt 삭제
                  </button>
                )}
              </div>

              {modalLevel.alt_meta?.source && (
                <div className="text-xs text-gray-500 mt-2">
                  alt: <b>{modalLevel.alt_meta.source}</b>
                  {modalLevel.alt_meta.track && ` · Track ${modalLevel.alt_meta.track === "motif" ? "A (모티프)" : "B (패턴)"}`}
                  {" · "}
                  {modalLevel.alt_meta.generated_at?.substring(0, 16)}
                  {typeof modalLevel.alt_meta.parsed_row_count === "number" && (
                    <> · 파싱 <b className={modalLevel.alt_meta.parsed_row_count < (modalLevel.alt_meta.expected_rows || 0) * 0.8 ? "text-red-600" : "text-green-600"}>
                      {modalLevel.alt_meta.parsed_row_count}/{modalLevel.alt_meta.expected_rows}
                    </b></>
                  )}
                </div>
              )}

              {/* 디버그: LLM raw response */}
              {modalLevel.alt_meta?.raw_response && (
                <details className="mt-2">
                  <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">
                    🔍 LLM 원문 응답 보기 ({modalLevel.alt_meta.raw_response.length} 글자)
                  </summary>
                  <pre className="mt-1 text-[10px] font-mono bg-gray-50 border border-gray-200 rounded p-2 max-h-48 overflow-auto text-gray-700 whitespace-pre-wrap">
                    {modalLevel.alt_meta.raw_response}
                  </pre>
                  {modalLevel.alt_meta.row_lengths && modalLevel.alt_meta.row_lengths.length > 0 && (
                    <div className="mt-1 text-[10px] text-gray-500">
                      각 행 길이 (첫 50개): [{modalLevel.alt_meta.row_lengths.join(", ")}]
                    </div>
                  )}
                </details>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
