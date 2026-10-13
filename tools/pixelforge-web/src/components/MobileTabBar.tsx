"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

// Instagram/X 스타일 하단 탭바 — 모바일(md 미만)에서만 노출.
// 데스크탑은 기존 상단 Nav 그대로. 기능 손실 없음 (탭은 기존 라우트 그대로 링크).
export interface TabItem {
  href: string;
  label: string;
  icon: string; // emoji (가벼운 렌더 — SVG 의존 X)
}

interface Props {
  tabs: TabItem[];        // 하단바 주요 탭 (최대 4~5)
  moreLinks?: TabItem[];  // 넘치는 링크 → "더보기" 시트
}

export default function MobileTabBar({ tabs, moreLinks = [] }: Props) {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  const moreActive = moreLinks.some((l) => isActive(l.href));

  return (
    <>
      {/* 더보기 시트 (오버레이) */}
      {moreOpen && moreLinks.length > 0 && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/40"
          onClick={() => setMoreOpen(false)}
        >
          <div
            className="absolute bottom-[calc(3.5rem+env(safe-area-inset-bottom))] left-0 right-0 rounded-t-2xl bg-white p-2 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-gray-300" />
            {moreLinks.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setMoreOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium ${
                  isActive(l.href) ? "bg-black text-white" : "text-gray-900 hover:bg-gray-100 active:bg-gray-200"
                }`}
              >
                <span className="text-lg">{l.icon}</span>
                <span>{l.label}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 하단 고정 탭바 */}
      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 z-40 flex border-t border-gray-200 bg-white/95 backdrop-blur"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {tabs.map((t) => {
          const active = isActive(t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 transition-colors ${
                active ? "text-black" : "text-gray-400 active:text-gray-600"
              }`}
            >
              <span className="text-xl leading-none">{t.icon}</span>
              <span className="text-[10px] font-semibold">{t.label}</span>
            </Link>
          );
        })}
        {moreLinks.length > 0 && (
          <button
            type="button"
            onClick={() => setMoreOpen((v) => !v)}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 transition-colors ${
              moreOpen || moreActive ? "text-black" : "text-gray-400 active:text-gray-600"
            }`}
            aria-label="더보기"
          >
            <span className="text-xl leading-none">⋯</span>
            <span className="text-[10px] font-semibold">더보기</span>
          </button>
        )}
      </nav>
    </>
  );
}
