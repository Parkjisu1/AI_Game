"use client";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { computeImageSize, limitColors } from "@/lib/genUtils";
import { parseColorDist } from "@/lib/palette";
import { LevelRow, type Level, type ColumnDef } from "@/components/LevelRow";

const PAGE_SIZE = 30;

const COLUMNS: ColumnDef[] = [
  { key: "level_number",      label: "Level",    width: "w-16" },
  { key: "field_rows",        label: "Rows",     width: "w-16" },
  { key: "field_columns",     label: "Cols",     width: "w-16" },
  { key: "num_colors",        label: "Colors",   width: "w-20" },
  { key: "purpose_type",      label: "Purpose",  width: "w-32" },
  { key: "designer_note",     label: "Note",     width: "w-64" },
  { key: "status",            label: "Status",   width: "w-24" },
];

const STATUS_COLORS: Record<string, string> = {
  draft:     "bg-gray-100 text-gray-600",
  review:    "bg-blue-50 text-blue-600",
  generated: "bg-green-50 text-green-700",
  approved:  "bg-emerald-50 text-emerald-700",
};

export default function LevelsPage() {
  const [levels, setLevels] = useState<Level[]>([]);
  const [editing, setEditing] = useState<{ row: number; col: keyof Level } | null>(null);
  const [editVal, setEditVal] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [csvModal, setCsvModal] = useState(false);
  const [csvText, setCsvText] = useState("");
  // 시트 구조: 카테고리 헤더(1행) → 영문 헤더(2행) → 한글 헤더(3행) → 데이터(4행~)
  const [csvHeaderRow, setCsvHeaderRow] = useState<number>(2); // 1-based
  const [csvDataStartRow, setCsvDataStartRow] = useState<number>(4); // 1-based
  const [csvDetectedHeaders, setCsvDetectedHeaders] = useState<string[]>([]);
  const [selectedNums, setSelectedNums] = useState<Set<number>>(new Set());
  const [rangeInput, setRangeInput] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState("");
  const [transparentBg, setTransparentBg] = useState(false);
  const [useColorLimit, setUseColorLimit] = useState(true);
  const [maxColors, setMaxColors] = useState<number>(0); // 0 = 제한 없음
  const [expandedNum, setExpandedNum] = useState<number | null>(null);
  // 행별 색상 override (확장된 행에서 사용)
  const [rowColors, setRowColorsState] = useState<Record<number, number[]>>({});
  const [page, setPage] = useState(1);
  const inputRef = useRef<HTMLInputElement>(null);

  // 30개 페이지네이션
  const totalPages = Math.max(1, Math.ceil(levels.length / PAGE_SIZE));
  const pagedLevels = useMemo(
    () => levels.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [levels, page]
  );
  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [levels.length, page, totalPages]);

  // 단일 레벨 즉시 생성 (확장 행에서 사용)
  // 단일 레벨 생성 payload 빌드 (generateOne + generateSelected가 공유)
  function buildGenPayload(lv: Level, colorOverride?: number[]) {
    const note = String(lv.designer_note || "").trim();
    let prompt = note || "pixel art pattern";
    const motif = note.match(/\[Motif\][^:\[]*:?\s*([^\[\n]+)/);
    const shape = note.match(/\[Shape\]\s*([^\[\n]+)/);
    if (motif || shape) {
      prompt = [motif?.[1]?.trim(), shape?.[1]?.trim()].filter(Boolean).join(", ");
    }

    // 색상 결정 우선순위 (num_colors는 서버 후처리에서 처리):
    // 1. colorOverride (명시적 override)
    // 2. rowColors[lv.level_number] (확장 행에서 수동 선택)
    // 3. 시트의 color_distribution (구버전 또는 재생성 결과)
    // → num_colors만 있는 경우 빈 배열 전달 (PixelLab이 자유롭게 선택)
    //   서버의 snap-to-grid가 num_colors만큼만 남김 (주제에 맞는 dominant colors)
    let ids: number[] = [];
    if (colorOverride && colorOverride.length > 0) {
      ids = colorOverride;
    } else if (rowColors[lv.level_number] && rowColors[lv.level_number].length > 0) {
      ids = rowColors[lv.level_number];
    } else {
      ids = parseColorDist(String(lv.color_distribution || ""));
    }

    // 세션 레벨 maxColors 드롭다운 override (있으면 limit)
    if (useColorLimit && maxColors > 0 && ids.length > maxColors) {
      ids = limitColors(ids, maxColors);
    }
    const colorDist = useColorLimit ? ids.map((c) => `c${c}:1`).join(",") : "";

    const { width, height } = computeImageSize(
      Number(lv.field_columns) || 20,
      Number(lv.field_rows) || 20
    );

    return {
      level_number: lv.level_number,
      prompt,
      width,
      height,
      color_distribution: colorDist,
      level_data: lv,
      no_background: transparentBg,
      use_color_limit: useColorLimit, // 서버가 color count reduction 적용 여부 결정
    };
  }

  async function callGenerate(lv: Level, apiKey: string, colorOverride?: number[]) {
    const proKey = typeof window !== "undefined" ? localStorage.getItem("pixellab_pro_key") || "" : "";
    console.log("[callGenerate]", {
      level: lv.level_number,
      keyLen: apiKey?.length || 0,
      hasProKey: proKey.length > 0,
    });
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "x-pixellab-key": apiKey,
    };
    if (proKey) headers["x-pixellab-pro-key"] = proKey;
    const res = await fetch("/api/generate", {
      method: "POST",
      headers,
      body: JSON.stringify(buildGenPayload(lv, colorOverride)),
    });
    const data = await res.json();

    // v2 async mode — 클라이언트 폴링 (pro-poll이 snap + DB 저장까지 처리)
    if (data.ok && (data.mode === "v2_async" || data.mode === "pro_async") && data.proJobId) {
      console.log("[callGenerate] v2 job started:", data.proJobId);
      setGenProgress(`Level ${lv.level_number} 생성 중...`);
      const pollHeaders: Record<string, string> = {};
      if (proKey) pollHeaders["x-pixellab-pro-key"] = proKey;
      if (apiKey) pollHeaders["x-pixellab-key"] = apiKey;

      for (let elapsed = 0; elapsed < 120000; elapsed += 5000) {
        await new Promise((r) => setTimeout(r, 5000));
        setGenProgress(`Level ${lv.level_number} 생성 중... (${Math.round(elapsed / 1000 + 5)}초)`);
        try {
          const pollRes = await fetch(`/api/pro-poll?jobId=${encodeURIComponent(data.proJobId)}`, {
            headers: pollHeaders,
          });
          const pollData = await pollRes.json();
          if (pollData.status === "completed") {
            if (!pollData.base64) {
              return { ok: false, error: "완료되었으나 이미지 데이터 없음" };
            }
            console.log("[callGenerate] v2 completed", { base64Length: pollData.base64.length });
            // pro-poll이 이미 snap + DB 저장 완료함
            return { ok: true, mode: "v2_completed" };
          }
          if (pollData.status === "error") {
            return { ok: false, error: pollData.error };
          }
        } catch (e) {
          console.error("[callGenerate] poll fetch error:", e);
        }
      }
      return { ok: false, error: "생성 timeout (120초)" };
    }

    if (!data.ok) console.error("[callGenerate] fail:", data);
    return data;
  }

  const generateOne = useCallback(async (lv: Level) => {
    const apiKey = typeof window !== "undefined" ? localStorage.getItem("pixellab_api_key") || "" : "";
    if (!apiKey) {
      flash("우상단 ⚙️에서 PixelLab API Key 먼저 설정");
      return;
    }
    setGenerating(true);
    setGenProgress(`Level ${lv.level_number}`);
    try {
      const data = await callGenerate(lv, apiKey);
      if (data.ok) {
        flash(`Level ${lv.level_number} 생성 완료`);
        const fresh = await fetch("/api/levels").then((r) => r.json());
        if (Array.isArray(fresh)) setLevels(fresh);
      } else {
        flash(`생성 실패: ${data.error || "unknown"}`);
      }
    } catch (e) {
      flash(`오류: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setGenerating(false);
      setGenProgress("");
    }
  }, [rowColors, useColorLimit, maxColors, transparentBg]);

  async function generateSelected() {
    if (selectedNums.size === 0) return;
    const apiKey = typeof window !== "undefined" ? localStorage.getItem("pixellab_api_key") || "" : "";
    if (!apiKey) {
      flash("우상단 ⚙️에서 PixelLab API Key 먼저 설정");
      return;
    }
    const targets = levels.filter((l) => selectedNums.has(l.level_number));
    setGenerating(true);
    let success = 0, failed = 0;
    for (let i = 0; i < targets.length; i++) {
      const lv = targets[i];
      setGenProgress(`${i + 1}/${targets.length} — Level ${lv.level_number}`);
      try {
        const data = await callGenerate(lv, apiKey);
        if (data.ok) success++;
        else failed++;
      } catch {
        failed++;
      }
    }
    setGenerating(false);
    setGenProgress("");
    flash(`생성 완료: ${success}건${failed > 0 ? `, 실패 ${failed}건` : ""}`);
    // DB 갱신
    try {
      const fresh = await fetch("/api/levels").then((r) => r.json());
      if (Array.isArray(fresh)) setLevels(fresh);
    } catch {}
  }

  const toggleSelect = useCallback((num: number) => {
    setSelectedNums((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  }, []);

  const toggleExpand = useCallback((num: number) => {
    setExpandedNum((prev) => (prev === num ? null : num));
  }, []);

  const setRowColors = useCallback((num: number, ids: number[]) => {
    setRowColorsState((prev) => ({ ...prev, [num]: ids }));
  }, []);

  const clearRowColors = useCallback((num: number) => {
    setRowColorsState((prev) => {
      const n = { ...prev };
      delete n[num];
      return n;
    });
  }, []);

  function toggleSelectAll() {
    if (selectedNums.size === levels.length) {
      setSelectedNums(new Set());
    } else {
      setSelectedNums(new Set(levels.map((l) => l.level_number)));
    }
  }

  // "1-5,6,7,50-66,81-100" 형식 파싱 → level_number Set
  function parseRangeInput(input: string): number[] {
    const result = new Set<number>();
    for (const part of input.split(",")) {
      const trimmed = part.trim();
      if (!trimmed) continue;
      const rangeMatch = trimmed.match(/^(\d+)\s*[-~]\s*(\d+)$/);
      if (rangeMatch) {
        const lo = Math.min(Number(rangeMatch[1]), Number(rangeMatch[2]));
        const hi = Math.max(Number(rangeMatch[1]), Number(rangeMatch[2]));
        for (let n = lo; n <= hi; n++) result.add(n);
      } else {
        const n = Number(trimmed);
        if (Number.isFinite(n) && n > 0) result.add(n);
      }
    }
    return Array.from(result);
  }

  function applyRangeSelection(mode: "replace" | "add") {
    const parsed = parseRangeInput(rangeInput);
    if (parsed.length === 0) {
      flash("유효한 입력 필요 (예: 1-5,6,7,50-66)");
      return;
    }
    // DB에 있는 레벨만 필터
    const levelNums = new Set(levels.map((l) => l.level_number));
    const matched = parsed.filter((n) => levelNums.has(n));
    if (matched.length === 0) {
      flash(`입력한 범위에 해당하는 레벨 없음`);
      return;
    }
    setSelectedNums((prev) => {
      const next = mode === "add" ? new Set(prev) : new Set<number>();
      for (const n of matched) next.add(n);
      return next;
    });
    flash(`${matched.length}개 선택됨`);
  }

  async function deleteSelected() {
    if (selectedNums.size === 0) return;
    if (!confirm(`선택된 ${selectedNums.size}개 레벨 삭제?`)) return;
    setSaving(true);
    try {
      // 병렬 삭제
      const targets = levels.filter((l) => selectedNums.has(l.level_number));
      await Promise.all(
        targets.map((lv) => {
          const id = lv._id || String(lv.level_number);
          return fetch(`/api/levels/${id}`, { method: "DELETE" });
        })
      );
      setLevels((prev) => prev.filter((l) => !selectedNums.has(l.level_number)));
      setSelectedNums(new Set());
      flash(`${targets.length}건 삭제 완료`);
    } catch {
      flash("일부 삭제 실패");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    fetch("/api/levels")
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setLevels(data); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus();
  }, [editing]);

  const startEdit = useCallback((rowIdx: number, col: keyof Level) => {
    setEditing({ row: rowIdx, col });
    setEditVal(String(levels[rowIdx][col] ?? ""));
  }, [levels]);

  const cancelEdit = useCallback(() => setEditing(null), []);

  async function saveLevel(level: Level) {
    setSaving(true);
    try {
      const body = { ...level };
      delete body._id;
      await fetch("/api/levels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      flash("저장됨");
    } catch {
      flash("저장 실패");
    } finally {
      setSaving(false);
    }
  }

  const commitEdit = useCallback(async () => {
    if (!editing) return;
    const { row, col } = editing;
    const updated = { ...levels[row] };
    const numericCols: (keyof Level)[] = ["level_number", "field_rows", "field_columns", "num_colors"];
    updated[col] = numericCols.includes(col) ? Number(editVal) : editVal as never;
    const newLevels = levels.map((l, i) => (i === row ? updated : l));
    setLevels(newLevels);
    setEditing(null);
    await saveLevel(updated);
  }, [editing, editVal, levels]);

  const deleteLevel = useCallback(async (level: Level) => {
    if (!confirm(`Level ${level.level_number} 삭제?`)) return;
    const id = level._id || String(level.level_number);
    await fetch(`/api/levels/${id}`, { method: "DELETE" });
    setLevels((prev) => prev.filter((l) => l.level_number !== level.level_number));
    flash("삭제됨");
  }, []);

  function flash(msg: string) {
    setNotice(msg);
    setTimeout(() => setNotice(""), 2000);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") setEditing(null);
  }

  // 따옴표·콤마·탭 모두 지원하는 CSV 한 줄 파서 (RFC 4180 lite).
  function splitLine(line: string, delim: string): string[] {
    const out: string[] = [];
    let cur = "";
    let inQuote = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuote) {
        if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (ch === '"') { inQuote = false; }
        else { cur += ch; }
      } else {
        if (ch === '"') { inQuote = true; }
        else if (ch === delim) { out.push(cur); cur = ""; }
        else { cur += ch; }
      }
    }
    out.push(cur);
    return out;
  }

  // 헤더 별칭 → 표준 컬럼명 매핑 (소문자 비교)
  const HEADER_ALIASES: Record<string, string> = {
    "level": "level_number",
    "lv": "level_number",
    "lvno": "level_number",
    "lv_no": "level_number",
    "level_no": "level_number",
    "level_num": "level_number",
    "stage": "level_number",
    "stage_no": "level_number",
    "스테이지": "level_number",
    "레벨": "level_number",
    "레벨번호": "level_number",
    "rows": "field_rows",
    "row": "field_rows",
    "y": "field_rows",
    "행": "field_rows",
    "cols": "field_columns",
    "col": "field_columns",
    "columns": "field_columns",
    "x": "field_columns",
    "열": "field_columns",
    "colors": "num_colors",
    "color_count": "num_colors",
    "색상수": "num_colors",
    "color_dist": "color_distribution",
    "purpose": "purpose_type",
    "note": "designer_note",
    "notes": "designer_note",
    "memo": "designer_note",
  };

  function normalizeHeader(raw: string): string {
    const key = raw.trim().toLowerCase().replace(/[ \-\.]/g, "_");
    return HEADER_ALIASES[key] || key;
  }

  function parseCSV(
    text: string,
    headerRow: number = csvHeaderRow,
    dataStartRow: number = csvDataStartRow
  ): { rows: Level[]; headers: string[] } {
    // BOM 제거
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    // 빈 줄을 보존해야 행 번호가 시트와 일치 (라인 자체는 split 시 \r 제거만)
    const lines = text.replace(/\r\n/g, "\n").split("\n");
    // trailing 빈 줄만 제거
    while (lines.length > 0 && !lines[lines.length - 1].trim()) lines.pop();
    if (lines.length < headerRow) return { rows: [], headers: [] };

    // 구분자 자동 감지: 헤더 행을 기준으로
    const headerLine = lines[headerRow - 1] || "";
    const delim = headerLine.includes("\t") ? "\t" : ",";

    const headers = splitLine(headerLine, delim).map(normalizeHeader);

    const dataLines = lines.slice(dataStartRow - 1).filter((l) => l.trim());

    const rows = dataLines.map((line) => {
      const vals = splitLine(line, delim);
      const obj: Partial<Level> = {};
      headers.forEach((h, i) => {
        if (!h) return; // 빈 헤더 컬럼은 스킵
        // 헤더가 "(삭제됨)" 같은 특수 토큰이면 무시
        if (h.startsWith("(") || h.includes("삭제")) return;
        const v = vals[i]?.trim() ?? "";
        const numericCols = ["level_number", "field_rows", "field_columns", "num_colors"];
        if (numericCols.includes(h)) {
          (obj as Record<string, unknown>)[h] = Number(v.replace(/,/g, "")) || 0;
        } else {
          (obj as Record<string, unknown>)[h] = v;
        }
      });
      obj.status = obj.status || "draft";
      return obj as Level;
    });

    return { rows, headers };
  }

  // 인코딩 자동 감지: UTF-8(BOM) → UTF-8 strict → EUC-KR(CP949) → UTF-8 lossy
  function decodeBytes(buf: ArrayBuffer): { text: string; encoding: string } {
    const bytes = new Uint8Array(buf);
    // BOM 확인
    if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
      return { text: new TextDecoder("utf-8").decode(bytes.slice(3)), encoding: "utf-8 (BOM)" };
    }
    // strict UTF-8 시도 — 잘못된 시퀀스면 throw
    try {
      const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      return { text, encoding: "utf-8" };
    } catch {
      // EUC-KR(CP949) 시도 — 한국어 Windows 기본
      try {
        return { text: new TextDecoder("euc-kr").decode(bytes), encoding: "euc-kr" };
      } catch {
        // 최후: replacement char 허용 UTF-8
        return { text: new TextDecoder("utf-8").decode(bytes), encoding: "utf-8 lossy" };
      }
    }
  }

  function handleCsvFile(file: File) {
    const reader = new FileReader();
    reader.onload = async (e) => {
      const buf = e.target?.result as ArrayBuffer;
      if (!buf) {
        flash("파일 읽기 실패");
        return;
      }
      const { text, encoding } = decodeBytes(buf);
      setCsvText(text);
      // 미리 파싱해서 행 수 확인 → 사용자가 결과 즉시 인지
      const { rows: parsed, headers } = parseCSV(text);
      setCsvDetectedHeaders(headers);
      if (parsed.length === 0) {
        flash(`파일 읽음 (${encoding}, ${(file.size / 1024).toFixed(1)}KB) — 파싱 0건. 헤더 행 번호 확인`);
        return;
      }
      flash(`파일 읽음 (${encoding}): ${parsed.length}건 — 가져오는 중...`);
      // 자동 import (textarea 단계 생략)
      await importCsvFromText(text);
    };
    reader.onerror = () => flash("파일 읽기 실패");
    // ArrayBuffer로 읽어서 인코딩 직접 결정
    reader.readAsArrayBuffer(file);
  }

  async function importCsvFromText(text: string) {
    const { rows: parsed, headers } = parseCSV(text);
    setCsvDetectedHeaders(headers);
    if (parsed.length === 0) {
      flash(`파싱 0행 — 헤더 행(${csvHeaderRow}) / 데이터 시작 행(${csvDataStartRow}) 설정 확인`);
      return false;
    }
    // 클라이언트도 1차 검증: level_number 유효한지
    const validRows = parsed.filter((p) => Number(p.level_number) > 0);
    if (validRows.length === 0) {
      const hasLvCol = headers.includes("level_number");
      const sample = parsed.slice(0, 2).map((r) => r.level_number).join(", ");
      flash(
        hasLvCol
          ? `level_number 컬럼은 있지만 값이 양수가 아님 (예: ${sample}). 데이터 시작 행 확인`
          : `level_number 헤더 못 찾음. 인식된 헤더: ${headers.slice(0, 5).join(", ")}...`
      );
      return false;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/levels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(validRows),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.ok === false) {
        const errMsg = json.error || `HTTP ${res.status}`;
        flash(`서버 오류: ${errMsg.substring(0, 120)}`);
        console.error("[CSV import error]", json);
        return false;
      }
      const fresh = await fetch("/api/levels").then((r) => r.json());
      if (Array.isArray(fresh)) setLevels(fresh);
      setCsvModal(false);
      setCsvText("");
      const skipped = json.skipped || (parsed.length - validRows.length);
      flash(`${json.count || validRows.length}건 가져오기 완료${skipped ? ` (스킵 ${skipped})` : ""}`);
      return true;
    } catch (e) {
      flash(`가져오기 실패: ${e instanceof Error ? e.message : "unknown"}`);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function importCSV() {
    await importCsvFromText(csvText);
  }

  function addRow() {
    const maxNum = levels.length > 0 ? Math.max(...levels.map((l) => l.level_number)) : 0;
    const newLevel: Level = {
      level_number: maxNum + 1,
      field_rows: 8,
      field_columns: 8,
      num_colors: 4,
      color_distribution: "",
      purpose_type: "normal",
      designer_note: "",
      status: "draft",
    };
    setLevels((prev) => [...prev, newLevel]);
    saveLevel(newLevel);
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <h1 className="text-2xl font-bold">레벨 데이터</h1>
        <div className="flex items-center gap-3 flex-wrap">
          {notice && (
            <span className="text-sm text-green-600 font-medium">{notice}</span>
          )}
          {saving && <span className="text-sm text-gray-400">저장 중...</span>}
          {generating && <span className="text-sm text-blue-500">{genProgress}</span>}
          {selectedNums.size > 0 && (
            <>
              <button
                onClick={generateSelected}
                disabled={generating}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
              >
                🎨 이미지 생성 ({selectedNums.size})
              </button>
              <button
                onClick={deleteSelected}
                disabled={generating}
                className="px-3 py-1.5 text-sm border border-red-300 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-40 transition-colors"
              >
                선택 삭제 ({selectedNums.size})
              </button>
            </>
          )}
          <button
            onClick={() => setCsvModal(true)}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            style={{color:"#000"}}
          >
            CSV 가져오기
          </button>
          <button
            onClick={addRow}
            className="px-3 py-1.5 text-sm bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            + 레벨 추가
          </button>
        </div>
      </div>

      {/* 범위 선택 바 */}
      <div className="flex flex-wrap items-center gap-2 mb-3 px-3 py-2 bg-gray-50 rounded-lg border border-gray-200">
        <span className="text-xs font-semibold shrink-0" style={{ color: "#000" }}>🎯</span>
        <input
          type="text"
          value={rangeInput}
          onChange={(e) => setRangeInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") applyRangeSelection("replace"); }}
          placeholder="1-5,6,7,50-66,81-100"
          className="flex-1 min-w-[180px] px-2.5 py-1.5 text-xs border border-gray-300 rounded font-mono"
          style={{ color: "#000" }}
        />
        <button
          onClick={() => applyRangeSelection("replace")}
          className="px-3 py-1.5 text-xs bg-black text-white rounded hover:bg-gray-800 shrink-0"
        >
          선택
        </button>
        <button
          onClick={() => applyRangeSelection("add")}
          className="px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100 shrink-0"
          style={{ color: "#000" }}
        >
          +추가
        </button>
        <button
          onClick={toggleSelectAll}
          className="px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100 shrink-0"
          style={{ color: "#000" }}
        >
          {selectedNums.size === levels.length && levels.length > 0 ? "전체 해제" : "전체"}
        </button>
        {selectedNums.size > 0 && (
          <>
            <button
              onClick={() => setSelectedNums(new Set())}
              className="text-xs text-gray-500 hover:underline shrink-0"
            >
              해제
            </button>
            <span className="text-xs text-blue-600 font-semibold shrink-0">
              {selectedNums.size}개
            </span>
          </>
        )}
      </div>

      {/* 생성 옵션 — 항상 표시 (선택된 행이 없어도 미리 설정 가능) */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-3 px-3 py-2 bg-blue-50/40 rounded-lg border border-blue-100">
        <span className="text-xs font-semibold" style={{color:"#000"}}>🎨 생성 옵션:</span>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={useColorLimit}
            onChange={(e) => setUseColorLimit(e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-xs" style={{color:"#000"}}>색상 제한</span>
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs" style={{color:"#000"}}>최대 색:</span>
          <select
            value={maxColors}
            onChange={(e) => setMaxColors(Number(e.target.value))}
            disabled={!useColorLimit}
            className="text-xs border border-gray-300 rounded px-1.5 py-0.5 bg-white disabled:opacity-40"
            style={{color:"#000"}}
          >
            <option value={0}>제한없음</option>
            <option value={5}>5색</option>
            <option value={8}>8색</option>
            <option value={13}>13색</option>
            <option value={28}>전체 28색</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={transparentBg}
            onChange={(e) => setTransparentBg(e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-xs" style={{color:"#000"}}>투명 배경 (PNG)</span>
        </label>
        <span className="text-xs text-gray-500 ml-auto">
          크기는 레벨 행/열 비율로 자동 계산 · 픽셀-퍼펙트 (셀 1개 = 정수 픽셀)
        </span>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="w-10 px-3 py-2.5 text-center" style={{color:"#000"}}>
                <input
                  type="checkbox"
                  checked={levels.length > 0 && selectedNums.size === levels.length}
                  ref={(el) => {
                    if (el) el.indeterminate = selectedNums.size > 0 && selectedNums.size < levels.length;
                  }}
                  onChange={toggleSelectAll}
                  className="w-4 h-4 cursor-pointer"
                  aria-label="전체 선택"
                />
              </th>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={`${col.width} px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide`}
                  style={{color:"#000"}}
                >
                  {col.label}
                </th>
              ))}
              <th className="w-16 px-3 py-2.5 text-xs font-semibold" style={{color:"#000"}}></th>
            </tr>
          </thead>
          <tbody>
            {levels.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length + 2} className="px-3 py-8 text-center text-gray-400 text-sm">
                  레벨 데이터 없음 — CSV 가져오기 또는 직접 추가
                </td>
              </tr>
            )}
            {pagedLevels.map((level, localIdx) => (
              <LevelRow
                key={level.level_number}
                level={level}
                rowIdx={(page - 1) * PAGE_SIZE + localIdx}
                columns={COLUMNS}
                isSelected={selectedNums.has(level.level_number)}
                isExpanded={expandedNum === level.level_number}
                isEditingCell={editing}
                editVal={editVal}
                rowColorOverride={rowColors[level.level_number]}
                generating={generating}
                transparentBg={transparentBg}
                maxColors={maxColors}
                statusColors={STATUS_COLORS}
                onToggleSelect={toggleSelect}
                onToggleExpand={toggleExpand}
                onStartEdit={startEdit}
                onCommitEdit={commitEdit}
                onCancelEdit={cancelEdit}
                onEditValChange={setEditVal}
                onDelete={deleteLevel}
                onGenerateOne={generateOne}
                onSetRowColors={setRowColors}
                onClearRowColors={clearRowColors}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-xs text-gray-400">
        셀을 클릭하여 편집 — Enter로 저장, Esc로 취소
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1 mt-4 flex-wrap">
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

      {/* CSV Modal */}
      {csvModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-3">
          <div className="bg-white rounded-2xl p-6 w-full max-w-[600px] shadow-xl">
            <h2 className="text-lg font-bold mb-2">CSV 가져오기</h2>
            <p className="text-sm text-gray-500 mb-3">
              Google Sheets에서 <b>파일 → 다운로드 → CSV</b>로 받은 파일을 업로드하세요.
              구분자(콤마/탭)·인코딩(UTF-8/EUC-KR)은 자동 감지.
            </p>

            <div className="flex items-center gap-3 mb-3 p-2 bg-blue-50/50 border border-blue-100 rounded-lg">
              <label className="flex items-center gap-1.5 text-xs" style={{color:"#000"}}>
                헤더 행:
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={csvHeaderRow}
                  onChange={(e) => setCsvHeaderRow(Number(e.target.value) || 1)}
                  className="w-14 px-1.5 py-0.5 border border-gray-300 rounded text-center"
                />
              </label>
              <label className="flex items-center gap-1.5 text-xs" style={{color:"#000"}}>
                데이터 시작 행:
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={csvDataStartRow}
                  onChange={(e) => setCsvDataStartRow(Number(e.target.value) || 1)}
                  className="w-14 px-1.5 py-0.5 border border-gray-300 rounded text-center"
                />
              </label>
              <span className="text-xs text-gray-500">
                기본: 영문헤더 2행, 데이터 4행 (1행=카테고리, 3행=한글)
              </span>
            </div>

            {csvDetectedHeaders.length > 0 && (
              <div className="mb-3 p-2 bg-gray-50 border border-gray-200 rounded-lg">
                <div className="text-xs font-semibold mb-1" style={{color:"#000"}}>
                  감지된 헤더 ({csvDetectedHeaders.length}):
                </div>
                <div className="text-xs font-mono break-all" style={{color:"#444"}}>
                  {csvDetectedHeaders.slice(0, 12).join(" · ")}
                  {csvDetectedHeaders.length > 12 ? " ..." : ""}
                </div>
                <div className="text-xs mt-1" style={{color: csvDetectedHeaders.includes("level_number") ? "#16a34a" : "#dc2626"}}>
                  {csvDetectedHeaders.includes("level_number")
                    ? "✓ level_number 발견"
                    : "✗ level_number 못 찾음 — 헤더 행 번호 확인"}
                </div>
              </div>
            )}

            <label className="flex items-center gap-2 mb-3 px-3 py-2 border border-dashed border-gray-300 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors">
              <span className="text-xs text-gray-500">📄 CSV/TSV 파일 선택</span>
              <input
                type="file"
                accept=".csv,.tsv,text/csv,text/tab-separated-values,text/plain"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleCsvFile(f);
                }}
                className="text-xs flex-1"
              />
            </label>

            <textarea
              className="w-full h-48 border border-gray-200 rounded-lg p-3 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-blue-200"
              placeholder="또는 여기에 붙여넣기..."
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => { setCsvModal(false); setCsvText(""); }}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                취소
              </button>
              <button
                onClick={importCSV}
                disabled={saving || !csvText.trim()}
                className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40"
              >
                {saving ? "처리 중..." : "가져오기"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
