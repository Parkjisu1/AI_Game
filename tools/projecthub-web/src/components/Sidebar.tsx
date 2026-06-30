"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

// 데스크톱 좌측 사이드바 (md+). 모바일은 상단 Nav + 하단 탭바.
// 실존 라우트만 — dead link 없음.
const GROUPS: { title: string; items: { href: string; label: string; icon: string; owner?: boolean }[] }[] = [
  {
    title: "메인",
    items: [
      { href: "/", label: "대시보드", icon: "home" },
      { href: "/tasks", label: "작업 보드", icon: "tasks" },
      { href: "/agents", label: "AI 팀", icon: "cpu" },
      { href: "/voice", label: "음성 명령", icon: "mic" },
      { href: "/gallery", label: "디자인 갤러리", icon: "image" },
    ],
  },
  {
    title: "도구",
    items: [
      { href: "/roadmap", label: "로드맵", icon: "map" },
      { href: "/balloonflow", label: "BalloonFlow", icon: "balloon" },
      { href: "/levels", label: "레벨", icon: "flag" },
      { href: "/pixelforge", label: "PixelForge", icon: "palette" },
    ],
  },
  {
    title: "설정",
    items: [{ href: "/settings", label: "환경 설정", icon: "gear", owner: true }],
  },
];

export default function Sidebar({ isOwner = false }: { isOwner?: boolean }) {
  const pathname = usePathname();
  const active = (h: string) => (h === "/" ? pathname === "/" : pathname?.startsWith(h));
  return (
    <aside className="hidden md:flex flex-col fixed left-0 top-0 bottom-0 w-60 border-r border-gray-200 bg-white z-30 overflow-y-auto">
      <Link href="/" className="px-5 py-4 text-lg font-bold flex items-center gap-2 shrink-0">
        <span className="w-7 h-7 rounded-lg bg-blue-500 text-white flex items-center justify-center"><Icon name="cpu" size={16} /></span>
        ProjectHub
      </Link>
      <nav className="px-3 space-y-5 pb-6">
        {GROUPS.map((g) => (
          <div key={g.title}>
            <div className="px-2 text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1">{g.title}</div>
            <div className="space-y-0.5">
              {g.items.filter((it) => !it.owner || isOwner).map((it) => (
                <Link
                  key={it.href}
                  href={it.href}
                  className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors ${
                    active(it.href) ? "bg-blue-50 text-blue-600 font-semibold" : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <Icon name={it.icon} size={17} /> {it.label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
