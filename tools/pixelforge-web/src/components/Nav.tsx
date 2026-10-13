"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const links = [
  { href: "/", label: "대시보드" },
  { href: "/levels", label: "레벨 데이터" },
  { href: "/gallery", label: "갤러리" },
  { href: "/json-vault", label: "JSON 보관함" },
];

function maskKey(key: string): string {
  if (!key) return "";
  if (key.length <= 8) return "***";
  return "***" + key.slice(-6);
}

export default function Nav() {
  const pathname = usePathname();
  const [showSettings, setShowSettings] = useState(false);
  // 입력 state (항상 빈 값으로 시작 — 사용자가 새로 입력하는 용도)
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [proKeyInput, setProKeyInput] = useState("");
  const [storedApiKey, setStoredApiKey] = useState("");
  const [storedProKey, setStoredProKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [balance, setBalance] = useState("--");
  const [saveNotice, setSaveNotice] = useState("");
  // style 레퍼런스 슬롯: default(공통 fallback) + character/background/structure(유형별)
  const STYLE_SLOTS: { key: string; label: string; desc: string }[] = [
    { key: "default", label: "공통 (기본 fallback)", desc: "유형별 슬롯이 비면 이걸 사용" },
    { key: "character", label: "캐릭터 모티프", desc: "Animal·Character·Food·Object" },
    { key: "background", label: "배경 모티프", desc: "Nature·Seasonal·Art" },
    { key: "structure", label: "선형·반복 구조", desc: "Geometric·Symbol·Abstract" },
  ];
  const [styleB64, setStyleB64] = useState<Record<string, string>>({}); // slot → full base64
  const [styleUploading, setStyleUploading] = useState<string>(""); // 업로드 중인 slot

  useEffect(() => {
    const stored = localStorage.getItem("pixellab_api_key");
    if (stored) { setStoredApiKey(stored); setSaved(true); fetchBalance(stored); }
    const pro = localStorage.getItem("pixellab_pro_key");
    if (pro) setStoredProKey(pro);
  }, []);

  useEffect(() => {
    if (showSettings) {
      setApiKeyInput("");
      setProKeyInput("");
      setSaveNotice("");
      loadStyleSlots(); // 4개 슬롯 전체 base64 로드 (미리보기)
    }
  }, [showSettings]);

  function slotUrl(slot: string, qs = ""): string {
    const params = new URLSearchParams(qs);
    if (slot !== "default") params.set("type", slot);
    const s = params.toString();
    return s ? `/pixelforge/api/style-image?${s}` : "/pixelforge/api/style-image";
  }

  async function loadStyleSlots() {
    const out: Record<string, string> = {};
    await Promise.all(["default", "character", "background", "structure"].map(async (slot) => {
      try {
        const j = await fetch(slotUrl(slot, "full=1")).then((r) => r.json());
        if (j.ok && j.hasImage) out[slot] = j.base64 || "";
      } catch { /* ignore */ }
    }));
    setStyleB64(out);
  }

  // PixelLab /balance 공식 스키마 (openapi.json 확인):
  // { credits: { type: "usd", usd: number }, subscription: { type: "generations", generations: number, total: number } }
  function extractBalance(obj: unknown): string | null {
    if (!obj || typeof obj !== "object") return null;
    const o = obj as Record<string, unknown>;

    // 명시적 에러
    if (typeof o.detail === "string") return `err: ${o.detail.substring(0, 40)}`;
    if (typeof o.error === "string") return `err: ${o.error.substring(0, 40)}`;

    const subscription = o.subscription as { generations?: number; total?: number } | undefined;
    const credits = o.credits as { usd?: number } | undefined;

    const subGen = typeof subscription?.generations === "number" ? subscription.generations : null;
    const subTotal = typeof subscription?.total === "number" ? subscription.total : null;
    const usd = typeof credits?.usd === "number" ? credits.usd : null;

    // 무료 generation 남아 있으면 우선 표시
    if (subGen !== null && subGen > 0) {
      return subTotal ? `${subGen}/${subTotal}` : `${subGen} gen`;
    }
    // 없으면 USD credits
    if (usd !== null) {
      return `$${usd.toFixed(2)}`;
    }
    // generations 0인데 credits도 없음 → 그대로 0 표시
    if (subGen === 0) return `0/${subTotal || 0}`;

    return null;
  }

  function fetchBalance(key?: string) {
    const k = key || localStorage.getItem("pixellab_api_key");
    if (!k) { setBalance("--"); return; }
    fetch("/pixelforge/api/generate", { headers: { "x-pixellab-key": k } })
      .then((r) => r.json())
      .then((data) => {
        console.log("[balance] raw response:", JSON.stringify(data).substring(0, 400));
        const result = extractBalance(data);
        if (result) {
          setBalance(result);
        } else {
          setBalance("?");
          console.warn("[balance] unknown format — keys:", Object.keys(data || {}));
        }
      })
      .catch((e) => {
        setBalance("err");
        console.error("[balance] fetch error:", e);
      });
  }

  function saveKey() {
    const newPix = apiKeyInput.trim();
    const newPro = proKeyInput.trim();
    const changes: string[] = [];
    if (newPix) {
      localStorage.setItem("pixellab_api_key", newPix);
      setStoredApiKey(newPix);
      setSaved(true);
      fetchBalance(newPix);
      changes.push(`Free ${maskKey(newPix)}`);
    }
    if (newPro) {
      localStorage.setItem("pixellab_pro_key", newPro);
      setStoredProKey(newPro);
      changes.push(`Pro ${maskKey(newPro)}`);
    }
    if (changes.length === 0) {
      setSaveNotice("입력값 없음 — 변경 사항 없음");
      setTimeout(() => setSaveNotice(""), 2500);
      return;
    }
    setApiKeyInput("");
    setProKeyInput("");
    setSaveNotice(`✓ 저장됨 — ${changes.join(" · ")}`);
    setTimeout(() => setSaveNotice(""), 3500);
  }

  async function uploadStyleImage(file: File, slot: string) {
    setStyleUploading(slot);
    try {
      const reader = new FileReader();
      const dataUrl = await new Promise<string>((resolve, reject) => {
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error("읽기 실패"));
        reader.readAsDataURL(file);
      });
      const img = new window.Image();
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error("이미지 로드 실패"));
        img.src = dataUrl;
      });
      const base64 = dataUrl.split(",")[1] || dataUrl;
      const res = await fetch(slotUrl(slot), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base64, width: img.width, height: img.height }),
      });
      const j = await res.json();
      if (j.ok) {
        setStyleB64((p) => ({ ...p, [slot]: base64 }));
        setSaveNotice(`✓ ${slot} 레퍼런스 업로드됨 (${img.width}×${img.height})`);
        setTimeout(() => setSaveNotice(""), 3000);
      } else {
        setSaveNotice(`업로드 실패: ${j.error}`);
      }
    } catch (e) {
      setSaveNotice(`오류: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setStyleUploading("");
    }
  }

  async function deleteStyleImage(slot: string) {
    if (!confirm(`${slot} 레퍼런스 삭제?`)) return;
    await fetch(slotUrl(slot), { method: "DELETE" });
    setStyleB64((p) => { const n = { ...p }; delete n[slot]; return n; });
    setSaveNotice(`${slot} 레퍼런스 삭제됨`);
    setTimeout(() => setSaveNotice(""), 2500);
  }

  function clearPixelLabKey() {
    if (!confirm("PixelLab API Key 삭제?")) return;
    localStorage.removeItem("pixellab_api_key");
    setStoredApiKey("");
    setApiKeyInput("");
    setSaved(false);
    setBalance("--");
    setSaveNotice("PixelLab Key 삭제됨");
    setTimeout(() => setSaveNotice(""), 2500);
  }

  return (
    <>
      <nav className="border-b border-gray-200 bg-white sticky top-0 z-30">
        <div className="px-4 sm:px-6 py-3 flex items-center gap-3 sm:gap-8">
          <Link href="/" className="shrink-0">
            {/* 모바일: IG 그라데이션 워드마크 / 데스크탑: 기존 검정 로고 */}
            <span className="md:hidden text-2xl font-extrabold italic tracking-tight bg-gradient-to-tr from-fuchsia-600 via-pink-500 to-amber-400 bg-clip-text text-transparent">
              PixelForge
            </span>
            <span className="hidden md:inline text-lg font-bold text-black tracking-tight">
              PixelForge
            </span>
          </Link>

          {/* Desktop links */}
          <div className="hidden md:flex gap-1">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                style={{ color: pathname === l.href ? "#ffffff" : "#000000" }}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  pathname === l.href ? "bg-black" : "hover:bg-gray-100"
                }`}
              >
                {l.label}
              </Link>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <a
              href="/tasks"
              className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
              style={{color:"#000"}}
            >
              📊 ProjectHub
            </a>
            <button
              onClick={() => fetchBalance()}
              className="text-xs text-black hidden sm:inline hover:text-blue-600 transition-colors"
              title="잔액 새로고침"
            >
              Credits: {balance} 🔄
            </button>
            <button
              onClick={() => setShowSettings(true)}
              className={`text-xs px-2.5 sm:px-3 py-1.5 rounded-lg border transition-colors ${
                saved
                  ? "border-gray-200 text-black hover:bg-gray-50"
                  : "border-red-300 text-red-600 bg-red-50 hover:bg-red-100"
              }`}
            >
              {saved ? "⚙️" : "⚠️ Key"}
              <span className="hidden sm:inline ml-1">{saved ? "설정" : "필요"}</span>
            </button>
          </div>
        </div>
      </nav>

      {/* 설정 모달 */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => setShowSettings(false)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-[480px] p-6 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-black mb-4">설정</h2>

            {/* PixelLab Key */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-black">PixelLab API Key</label>
                {storedApiKey && (
                  <span className="text-xs text-gray-500 font-mono">
                    현재: <span className="text-green-600">{maskKey(storedApiKey)}</span>
                  </span>
                )}
              </div>
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={storedApiKey ? "변경하려면 새 키 입력 (비우면 유지)" : "e9f65281-7eb8-..."}
                autoComplete="off"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-black focus:outline-none focus:border-black"
              />
              <div className="flex items-center justify-between mt-1">
                <p className="text-xs text-gray-500">
                  <a href="https://www.pixellab.ai" target="_blank" className="text-blue-600 hover:underline">pixellab.ai</a>에서 발급
                </p>
                {storedApiKey && (
                  <button
                    type="button"
                    onClick={clearPixelLabKey}
                    className="text-xs text-red-600 hover:underline"
                  >
                    삭제
                  </button>
                )}
              </div>
            </div>

            {/* Pro API Key */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-black">PixelLab Pro API Key</label>
                {storedProKey && (
                  <span className="text-xs text-gray-500 font-mono">
                    현재: <span className="text-green-600">{maskKey(storedProKey)}</span>
                  </span>
                )}
              </div>
              <input
                type="password"
                value={proKeyInput}
                onChange={(e) => setProKeyInput(e.target.value)}
                placeholder={storedProKey ? "변경하려면 새 키 입력 (비우면 유지)" : "Pro 계정 API Key (선택)"}
                autoComplete="off"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-black focus:outline-none focus:border-black"
              />
              <p className="text-xs text-gray-500 mt-1">
                Pro 계정이 있으면 입력 → style_image 업로드 시 Pro endpoint(v2) 사용. 없으면 Free key로 pixflux 사용.
              </p>
            </div>

            {/* Style 레퍼런스 (Pro용) — 유형별 4슬롯 */}
            <div className="mb-4 pt-3 border-t border-gray-100">
              <label className="text-sm font-medium text-black">Style 레퍼런스 (Pro)</label>
              <p className="text-xs text-gray-500 mb-3">
                유형별 레퍼런스를 두면, 레벨의 bl_category에 맞춰 자동 선택됩니다 (캐릭터/배경/구조).
                유형 슬롯이 비면 <b>공통</b>으로 fallback. 공통도 없으면 pixflux(non-Pro) 사용.
              </p>
              <div className="grid grid-cols-2 gap-3">
                {STYLE_SLOTS.map((s) => {
                  const b64 = styleB64[s.key];
                  return (
                    <div key={s.key} className="border border-gray-200 rounded-lg p-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-semibold text-black">{s.label}</span>
                        {b64 && <span className="text-[10px] text-green-600">✓</span>}
                      </div>
                      <p className="text-[10px] text-gray-400 mb-1.5 leading-tight">{s.desc}</p>
                      {b64 ? (
                        <img
                          src={`data:image/png;base64,${b64}`}
                          alt={s.label}
                          className="h-16 w-full rounded border border-gray-200 object-contain mb-1.5 bg-gray-50"
                        />
                      ) : (
                        <div className="h-16 w-full rounded border border-dashed border-gray-200 mb-1.5 flex items-center justify-center text-[10px] text-gray-300">없음</div>
                      )}
                      <div className="flex items-center gap-2">
                        <label className="px-2 py-1 text-[11px] border border-dashed border-gray-300 rounded cursor-pointer hover:bg-gray-50">
                          {styleUploading === s.key ? "업로드…" : "📎 선택"}
                          <input
                            type="file"
                            accept="image/*"
                            disabled={styleUploading !== ""}
                            onChange={(e) => {
                              const f = e.target.files?.[0];
                              if (f) uploadStyleImage(f, s.key);
                            }}
                            className="hidden"
                          />
                        </label>
                        {b64 && (
                          <button type="button" onClick={() => deleteStyleImage(s.key)}
                            className="text-[11px] text-red-600 hover:underline">삭제</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 저장 버튼 */}
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <button
                onClick={saveKey}
                className="bg-black text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-gray-800"
              >
                저장
              </button>
              <button
                onClick={() => setShowSettings(false)}
                className="bg-gray-100 text-black px-4 py-2 rounded-lg text-sm hover:bg-gray-200"
              >
                닫기
              </button>
            </div>

            {saveNotice && (
              <div className="mt-2 p-2 bg-green-50 border border-green-200 rounded-lg text-xs text-green-700 font-mono break-all">
                {saveNotice}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
