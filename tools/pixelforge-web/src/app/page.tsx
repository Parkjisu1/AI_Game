"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

export default function Dashboard() {
  const [stats, setStats] = useState({ levels: 0, generated: 0 });
  const [balance, setBalance] = useState<string>("--");

  function loadBalance() {
    const k = typeof window !== "undefined" ? localStorage.getItem("pixellab_api_key") : null;
    if (!k) { setBalance("--"); return; }
    fetch("/api/generate", { headers: { "x-pixellab-key": k } })
      .then((r) => r.json())
      .then((data) => {
        // 공식 스키마: { credits: {usd: N}, subscription: {generations, total} }
        const subGen = data?.subscription?.generations;
        const subTotal = data?.subscription?.total;
        const usd = data?.credits?.usd;
        if (typeof subGen === "number" && subGen > 0) {
          setBalance(typeof subTotal === "number" ? `${subGen}/${subTotal}` : `${subGen} gen`);
        } else if (typeof usd === "number") {
          setBalance(`$${usd.toFixed(2)}`);
        } else if (typeof subGen === "number") {
          setBalance(`${subGen}/${subTotal || 0}`);
        } else if (data?.error || data?.detail) {
          setBalance("err");
        } else {
          setBalance("?");
        }
      })
      .catch(() => setBalance("err"));
  }

  useEffect(() => {
    fetch("/api/levels").then((r) => r.json()).then((data) => {
      if (Array.isArray(data)) {
        setStats({
          levels: data.length,
          generated: data.filter((l: Record<string, unknown>) => l.image_base64).length,
        });
      }
    }).catch(() => {});
    loadBalance();
  }, []);

  const cards = [
    { title: "전체 레벨", value: String(stats.levels), href: "/levels" },
    { title: "생성 완료", value: String(stats.generated), href: "/gallery" },
    { title: "API 잔액", value: balance, href: "/levels", onClick: loadBalance },
    { title: "JSON 보관함", value: String(stats.generated), href: "/json-vault" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">PixelForge</h1>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
        {cards.map((c) => (
          <Link
            key={c.title}
            href={c.href}
            className="bg-white rounded-xl border border-gray-200 p-4 sm:p-5 hover:shadow-md transition-shadow min-w-0"
          >
            <div className="text-xs sm:text-sm text-gray-500 mb-1 truncate">{c.title}</div>
            <div className="text-2xl sm:text-3xl font-bold truncate">{c.value}</div>
          </Link>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <Link href="/levels" style={{color:"#ffffff"}} className="bg-black rounded-xl p-5 sm:p-6 hover:bg-gray-800 transition-colors">
          <div className="text-base sm:text-lg font-bold mb-1" style={{color:"#ffffff"}}>레벨 데이터 + 이미지</div>
          <div className="text-xs sm:text-sm" style={{color:"#cccccc"}}>CSV 가져오기 · 이미지 생성 · JSON export 통합</div>
        </Link>
        <Link href="/json-vault" className="bg-white rounded-xl border border-gray-200 p-5 sm:p-6 hover:shadow-md transition-shadow">
          <div className="text-base sm:text-lg font-bold mb-1">JSON 보관함</div>
          <div className="text-xs sm:text-sm text-gray-500">레벨별 JSON 미리보기 · 복사 · 공유 · 다운로드</div>
        </Link>
      </div>

      {/* ProjectHub link */}
      <div className="mt-6 bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl border border-blue-200 p-5">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <div className="flex-1">
            <div className="font-bold text-base mb-0.5">📊 OKR · 로드맵 · 작업 보드</div>
            <div className="text-xs text-gray-600">스프린트 로드맵, 작업 칸반, Slack 알림은 ProjectHub에서 관리</div>
          </div>
          <a
            href="https://projecthub-web.vercel.app"
            target="_blank"
            rel="noopener"
            className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 transition-colors self-start sm:self-auto"
          >
            ProjectHub 열기 →
          </a>
        </div>
      </div>
    </div>
  );
}
