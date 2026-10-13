"use client";
import { useState } from "react";

interface Lv {
  level_number: number;
  field_columns?: number;
  field_rows?: number;
  image_base64?: string;
}

interface Props {
  level: Lv;
  onClose: () => void;
  onComplete: () => Promise<void> | void;
}

// PixelLab Pixel Art Correction — 이미지 + strength 슬라이더만.
// 서버측 headless 봇이 PixelLab 웹 UI를 자동 조작 → 결과를 image_base64_alt에 저장.
export function CorrectionMini({ level, onClose, onComplete }: Props) {
  const [strength, setStrength] = useState(0.1);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [err, setErr] = useState("");

  async function run() {
    setRunning(true);
    setErr("");
    setProgress("PixelLab 봇 실행 중… (헤드리스 브라우저, 약 30~90초)");
    try {
      const res = await fetch("/pixelforge/api/correction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level_number: level.level_number, strength }),
      });
      const data = await res.json();
      if (!data.ok) {
        const detail = data.stderr ? `\n${String(data.stderr).slice(-300)}` : "";
        setErr(`실패: ${data.error}${detail}`);
        setRunning(false);
        return;
      }
      await onComplete();
      onClose();
    } catch (e) {
      setErr(`오류: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRunning(false);
    }
  }

  const src = level.image_base64 ? `data:image/png;base64,${level.image_base64}` : "";

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl p-5 w-full max-w-sm shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-base" style={{ color: "#000" }}>
            🩹 Correction — Lv {level.level_number}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none px-2">×</button>
        </div>

        {src && (
          <div className="mb-3 flex justify-center">
            <img
              src={src}
              alt={`Lv ${level.level_number}`}
              className="rounded border border-gray-200"
              style={{ width: 200, height: 200, objectFit: "contain", imageRendering: "pixelated" }}
            />
          </div>
        )}

        <label className="block mb-3 text-sm" style={{ color: "#000" }}>
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium">Correction strength</span>
            <span className="text-cyan-600 font-bold">{strength.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={strength}
            onChange={(e) => setStrength(Number(e.target.value))}
            disabled={running}
            className="w-full accent-emerald-500"
          />
          <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
            <span>Subtle</span><span>Strong</span>
          </div>
        </label>

        {err && (
          <pre className="mb-2 text-xs text-red-600 whitespace-pre-wrap max-h-32 overflow-auto bg-red-50 rounded p-2">
            {err}
          </pre>
        )}
        {running && <div className="mb-2 text-xs text-blue-600">{progress}</div>}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={running}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded disabled:opacity-40"
            style={{ color: "#000" }}
          >
            취소
          </button>
          <button
            onClick={run}
            disabled={running || !src}
            className="px-4 py-1.5 text-sm bg-emerald-500 text-black rounded font-medium hover:bg-emerald-400 disabled:opacity-40"
          >
            {running ? "…" : "Generate"}
          </button>
        </div>
      </div>
    </div>
  );
}
