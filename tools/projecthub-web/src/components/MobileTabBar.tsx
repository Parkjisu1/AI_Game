"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import Icon from "./Icon";

// 모바일 하단 탭바 (md 미만). 중앙에 떠오른 FAB(+ 새 작업) + 좌우 탭 + 더보기 시트.
export interface TabItem {
  href: string;
  label: string;
  icon: string; // Icon 컴포넌트 키
}

interface Props {
  tabs: TabItem[];           // 좌우로 분배될 주요 탭 (3개 권장)
  moreLinks?: TabItem[];     // "더보기" 시트
  fab?: { href: string; icon: string }; // 중앙 떠오른 버튼
}

export default function MobileTabBar({ tabs, moreLinks = [], fab }: Props) {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname?.startsWith(href));
  const moreActive = moreLinks.some((l) => isActive(l.href));

  const half = Math.ceil(tabs.length / 2);
  const left = tabs.slice(0, half);
  const right = tabs.slice(half);

  const Tab = (t: TabItem) => {
    const active = isActive(t.href);
    return (
      <Link key={t.href} href={t.href}
        className={`flex flex-1 flex-col items-center gap-0.5 py-2 transition-colors ${active ? "text-blue-500" : "text-gray-400 active:text-gray-600"}`}>
        <Icon name={t.icon} size={21} />
        <span className="text-[10px] font-semibold">{t.label}</span>
      </Link>
    );
  };

  return (
    <>
      {moreOpen && moreLinks.length > 0 && (
        <div className="md:hidden fixed inset-0 z-40 bg-black/40 fade-in" onClick={() => setMoreOpen(false)}>
          <div className="absolute bottom-[calc(3.5rem+env(safe-area-inset-bottom))] left-0 right-0 rounded-t-2xl bg-white p-2 shadow-2xl sheet-in" onClick={(e) => e.stopPropagation()}>
            <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-gray-300" />
            {moreLinks.map((l) => (
              <Link key={l.href} href={l.href} onClick={() => setMoreOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium ${isActive(l.href) ? "bg-blue-50 text-blue-600" : "text-gray-900 hover:bg-gray-100 active:bg-gray-200"}`}>
                <Icon name={l.icon} size={20} />
                <span>{l.label}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 flex items-stretch border-t border-gray-200 bg-white/95 backdrop-blur"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        {left.map(Tab)}
        {fab && (
          <div className="relative flex-1 flex justify-center">
            <Link href={fab.href} aria-label="새 작업"
              className="absolute -top-5 w-12 h-12 rounded-full bg-blue-500 text-white shadow-lg flex items-center justify-center active:scale-95 hover:bg-blue-600">
              <Icon name={fab.icon} size={24} />
            </Link>
          </div>
        )}
        {right.map(Tab)}
        {moreLinks.length > 0 && (
          <button type="button" onClick={() => setMoreOpen((v) => !v)} aria-label="더보기"
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 transition-colors ${moreOpen || moreActive ? "text-blue-500" : "text-gray-400 active:text-gray-600"}`}>
            <Icon name="more" size={21} />
            <span className="text-[10px] font-semibold">더보기</span>
          </button>
        )}
      </nav>
    </>
  );
}
