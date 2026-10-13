"use client";

import { useState } from "react";

type DesignerItem = { color: number; action: string; count: number; note: string };
type Variant = {
  name: string;
  instances: { size: [number, number]; pos: [number, number]; hp: number; color: number }[];
  validation: { color_darts: Record<string, number>; total: number; violations: number[][] } | null;
  auto_fix_clean: boolean;
  designer_needed: DesignerItem[];
  preview_b64: string;
};

const GIMMICKS = ["Wooden", "Hidden", "IronWall", "Ice", "Barricade", "TargetBox"]; // Snake 후속

export default function GimmickPage() {
  const [level, setLevel] = useState("34");
  const [gimmick, setGimmick] = useState("Wooden");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [variants, setVariants] = useState<Variant[]>([]);
  const [committing, setCommitting] = useState<number | null>(null);
  const [result, setResult] = useState<string>("");
  const [useVision, setUseVision] = useState(false);
  const [vision, setVision] = useState<{ metaphor?: string; regions_used?: number; error?: string } | null>(null);

  async function genVariants() {
    setError(""); setVariants([]); setResult(""); setVision(null); setLoading(true);
    try {
      const r = await fetch("/pixelforge/api/gimmick/variants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level_number: Number(level), gimmick_type: gimmick, use_vision: useVision }),
      });
      const data = await r.json();
      if (!data.ok) { setError(data.error || "실패"); return; }
      setVariants(data.variants);
      setVision(data.vision || null);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function commit(idx: number) {
    if (!confirm(`${variants[idx].name} 으로 확정하고 JSON 제작할까요?`)) return;
    setCommitting(idx); setResult("");
    try {
      const v = variants[idx];
      const r = await fetch("/pixelforge/api/gimmick/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // 선택안을 직접 전달 (vision 비결정성 안전 — index 재생성 회피)
        body: JSON.stringify({
          level_number: Number(level), gimmick_type: gimmick,
          variant: { name: v.name, instances: v.instances },
        }),
      });
      const data = await r.json();
      if (!data.ok) { setResult("❌ " + (data.error || "실패")); return; }
      const dn = (data.designer_needed || []) as DesignerItem[];
      setResult(
        `✅ "${data.chosen}" 확정·저장 완료 — 풍선 ${data.merged.balloons.length}개 + 기믹 ${data.merged.gimmicks.length}개. ` +
        `10배수 ${data.clean ? "CLEAN ✓" : "✗"}` +
        (dn.length ? ` · 디자이너 수동 필요 ${dn.length}건: ${dn.map((d) => d.note).join(" / ")}` : ""),
      );
    } catch (e) {
      setResult("❌ " + String((e as Error)?.message || e));
    } finally {
      setCommitting(null);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto", color: "#111" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>기믹 배치 (Gimmick Placement)</h1>
      <p style={{ color: "#666", fontSize: 13, marginBottom: 16 }}>
        완성보드 + 기믹 → 4안 생성 → 택1 → 10배수 자동보정 → JSON 제작. (완성보드 있는 레벨만 가능)
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 20, flexWrap: "wrap" }}>
        <label style={{ fontSize: 13 }}>레벨</label>
        <input value={level} onChange={(e) => setLevel(e.target.value)} style={{ width: 70, padding: "6px 8px", border: "1px solid #ccc", borderRadius: 6 }} />
        <label style={{ fontSize: 13 }}>기믹</label>
        <select value={gimmick} onChange={(e) => setGimmick(e.target.value)} style={{ padding: "6px 8px", border: "1px solid #ccc", borderRadius: 6 }}>
          {GIMMICKS.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 4 }} title="AI vision으로 머리/몸통 등 의미 영역 인식 (느림). 끄면 휴리스틱">
          <input type="checkbox" checked={useVision} onChange={(e) => setUseVision(e.target.checked)} /> AI vision
        </label>
        <button onClick={genVariants} disabled={loading}
          style={{ padding: "7px 16px", background: "#111", color: "#fff", borderRadius: 6, fontSize: 13, opacity: loading ? 0.5 : 1 }}>
          {loading ? "생성 중..." : "4안 생성"}
        </button>
      </div>

      {vision && (vision.metaphor || vision.error) && (
        <div style={{ fontSize: 12, color: "#555", marginBottom: 12 }}>
          🔍 vision: {vision.metaphor ? `${vision.metaphor} (의미영역 ${vision.regions_used}개 인식)` : `실패 → 휴리스틱 fallback (${vision.error})`}
        </div>
      )}
      {error && <div style={{ color: "#c00", marginBottom: 16, fontSize: 14 }}>⚠ {error}</div>}
      {result && <div style={{ background: "#f0f9f0", border: "1px solid #bcdfbc", padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 13 }}>{result}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {variants.map((v, i) => {
          const clean = v.validation && v.validation.violations.length === 0;
          return (
            <div key={i} style={{ border: "1px solid #ddd", borderRadius: 10, overflow: "hidden", background: "#fff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "#fafafa", borderBottom: "1px solid #eee" }}>
                <strong style={{ fontSize: 14 }}>{v.name}</strong>
                <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 99, background: clean ? "#e6f7e6" : (v.auto_fix_clean ? "#fff7e0" : "#fdecec"), color: clean ? "#1a7f1a" : (v.auto_fix_clean ? "#9a7000" : "#c0392b") }}>
                  {clean ? "10배수 ✓" : v.auto_fix_clean ? "auto-fix 시 ✓" : "디자이너 필요"}
                </span>
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`data:image/png;base64,${v.preview_b64}`} alt={v.name} style={{ width: "100%", display: "block", imageRendering: "pixelated" }} />
              <div style={{ padding: "8px 12px", fontSize: 12, color: "#555" }}>
                기믹 {v.instances.length}개 · 총darts {v.validation?.total ?? "-"}
                {v.designer_needed.length > 0 && (
                  <div style={{ color: "#b06000", marginTop: 4 }}>수동: {v.designer_needed.map((d) => d.note).join(" / ")}</div>
                )}
              </div>
              <button onClick={() => commit(i)} disabled={committing !== null}
                style={{ width: "100%", padding: "9px 0", background: "#2563eb", color: "#fff", fontSize: 13, opacity: committing !== null ? 0.5 : 1 }}>
                {committing === i ? "제작 중..." : "이 안으로 확정 → JSON 제작"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
