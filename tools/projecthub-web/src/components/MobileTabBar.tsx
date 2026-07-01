"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import Icon from "./Icon";

// 모바일 하단 탭바 (md 미만). 홀로그래픽 테마. 중앙 FAB + 좌우 탭 + 더보기 시트.
export interface TabItem {
  href: string;
  label: string;
  icon: string;
}

interface Props {
  tabs: TabItem[];
  moreLinks?: TabItem[];
  fab?: { href: string; icon: string };
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
    const on = isActive(t.href);
    return (
      <Link key={t.href} href={t.href}
        className="flex flex-1 flex-col items-center gap-0.5 py-2 transition-colors"
        style={on ? { color: "var(--neon)" } : { color: "var(--text-faint)" }}>
        <span className="flex items-center justify-center" style={on ? { filter: "drop-shadow(0 0 6px rgba(34,211,238,.7))" } : undefined}>
          <Icon name={t.icon} size={21} />
        </span>
        <span className="text-[10px] font-semibold">{t.label}</span>
      </Link>
    );
  };

  return (
    <>
      {moreOpen && moreLinks.length > 0 && (
        <div className="md:hidden fixed inset-0 bg-black/50 fade-in" style={{ zIndex: 44 }} onClick={() => setMoreOpen(false)}>
          <div className="absolute bottom-[calc(3.5rem+env(safe-area-inset-bottom))] left-0 right-0 rounded-t-2xl p-2 sheet-in"
            style={{ background: "rgba(9,15,28,0.98)", borderTop: "1px solid var(--line-strong)", boxShadow: "0 -20px 60px -20px rgba(0,0,0,.8)" }}
            onClick={(e) => e.stopPropagation()}>
            <div className="mx-auto mb-2 h-1 w-10 rounded-full" style={{ background: "var(--line-strong)" }} />
            {moreLinks.map((l) => {
              const on = isActive(l.href);
              return (
                <Link key={l.href} href={l.href} onClick={() => setMoreOpen(false)}
                  className="flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium"
                  style={on ? { background: "rgba(34,211,238,0.12)", color: "var(--neon)" } : { color: "var(--text)" }}>
                  <Icon name={l.icon} size={20} />
                  <span>{l.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      <nav className="md:hidden fixed bottom-0 left-0 right-0 flex items-stretch"
        style={{
          zIndex: 45,
          background: "rgba(6,11,22,0.96)",
          borderTop: "1px solid var(--line)",
          backdropFilter: "blur(16px)",
          boxShadow: "0 -14px 40px -18px rgba(0,0,0,.8)",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}>
        {left.map(Tab)}
        {fab && (
          <div className="relative flex-1 flex justify-center">
            <Link href={fab.href} aria-label="새 작업"
              className="absolute -top-5 w-12 h-12 rounded-full flex items-center justify-center active:scale-95"
              style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018", boxShadow: "0 0 22px -2px rgba(34,211,238,.75)" }}>
              <Icon name={fab.icon} size={24} />
            </Link>
          </div>
        )}
        {right.map(Tab)}
        {moreLinks.length > 0 && (
          <button type="button" onClick={() => setMoreOpen((v) => !v)} aria-label="더보기"
            className="flex flex-1 flex-col items-center gap-0.5 py-2 transition-colors"
            style={moreOpen || moreActive ? { color: "var(--neon)" } : { color: "var(--text-faint)" }}>
            <Icon name="more" size={21} />
            <span className="text-[10px] font-semibold">더보기</span>
          </button>
        )}
      </nav>
    </>
  );
}
