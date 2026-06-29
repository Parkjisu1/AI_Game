"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

// Instagram 스토리행 스타일 — 가로 스크롤 원형 네비게이션. md 미만에서만 노출.
// 데스크탑은 기존 nav 가 담당하므로 숨김. 각 항목은 실제 라우트 링크 (기능 손실 0).
export interface StoryItem {
  href: string;
  label: string;
  icon: string; // emoji
}

export default function StoryRow({ items }: { items: StoryItem[] }) {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="md:hidden no-scrollbar -mx-4 mb-4 flex gap-4 overflow-x-auto border-b border-gray-100 px-4 pb-3">
      {items.map((it) => {
        const active = isActive(it.href);
        return (
          <Link key={it.href} href={it.href} className="flex w-16 shrink-0 flex-col items-center gap-1">
            <span
              className={`flex h-16 w-16 items-center justify-center rounded-full p-[2px] ${
                active
                  ? "bg-gradient-to-tr from-fuchsia-600 via-pink-500 to-amber-400"
                  : "bg-gradient-to-tr from-gray-200 to-gray-300"
              }`}
            >
              <span className="flex h-full w-full items-center justify-center rounded-full bg-white text-2xl">
                {it.icon}
              </span>
            </span>
            <span className="w-full truncate text-center text-[11px] text-gray-700">{it.label}</span>
          </Link>
        );
      })}
    </div>
  );
}
