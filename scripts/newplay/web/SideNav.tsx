"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "@/components/Icon";

// clean 인스턴스 전용 좌측 사이드바 (Slack/Flex형 사무 레이아웃).
// 데스크톱(md+)만 — 모바일은 기존 Nav + MobileTabBar 유지.
type Item = { href: string; label: string; icon: string; owner?: boolean };

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: "워크스페이스",
    items: [
      { href: "/", label: "대시보드", icon: "home" },
      { href: "/tasks", label: "작업 보드", icon: "tasks" },
      { href: "/data", label: "데이터", icon: "graph" },
      { href: "/roadmap", label: "로드맵", icon: "map" },
      { href: "/platform", label: "플랫폼 현황", icon: "eye" },
    ],
  },
  {
    title: "AI",
    items: [
      { href: "/agents", label: "AI 팀", icon: "cpu" },
      { href: "/voice", label: "음성 명령", icon: "mic" },
    ],
  },
];

export default function SideNav({
  isOwner = false,
  showSettings,
  email = "",
  userLabel = "",
}: {
  isOwner?: boolean;
  /** 설정 링크 노출 여부. 미지정이면 소유자 여부를 따른다(기존 동작). */
  showSettings?: boolean;
  email?: string;
  userLabel?: string;
}) {
  const canSeeSettings = showSettings ?? isOwner;
  const pathname = usePathname();
  const active = (h: string) => (h === "/" ? pathname === "/" : pathname?.startsWith(h));

  if (pathname === "/login") return null;

  return (
    <aside className="sidenav hidden md:flex fixed inset-y-0 left-0 z-30 w-60 flex-col border-r border-gray-200 bg-white">
      {/* 브랜드 */}
      <div className="flex items-center gap-2.5 px-4 h-14 border-b border-gray-200">
        <span className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white text-sm font-bold">N</span>
        <span className="text-[15px] font-bold text-gray-900">NewPlay Hub</span>
      </div>

      {/* 내비게이션 */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-5">
        {GROUPS.map((g) => (
          <div key={g.title}>
            <div className="px-2.5 mb-1 text-[11px] font-semibold text-gray-400 tracking-wide">{g.title}</div>
            <div className="space-y-0.5">
              {g.items
                .filter((i) => !i.owner || isOwner)
                .map((i) => {
                  const on = active(i.href);
                  return (
                    <Link
                      key={i.href}
                      href={i.href}
                      className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors ${
                        on ? "bg-gray-100 font-semibold text-gray-900" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                      }`}
                    >
                      <Icon name={i.icon} size={16} />
                      {i.label}
                    </Link>
                  );
                })}
            </div>
          </div>
        ))}
      </nav>

      {/* 하단: 설정 + 사용자 */}
      <div className="border-t border-gray-200 px-2 py-2 space-y-0.5">
        {canSeeSettings && (
          <Link
            href="/settings"
            className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] ${
              active("/settings") ? "bg-gray-100 font-semibold text-gray-900" : "text-gray-600 hover:bg-gray-50"
            }`}
          >
            <Icon name="gear" size={16} />
            설정
          </Link>
        )}
        <div className="flex items-center gap-2.5 px-2.5 py-2">
          <span className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-[11px] font-bold text-gray-600">
            {(userLabel || email || "?").slice(0, 1).toUpperCase()}
          </span>
          <span className="flex-1 min-w-0 text-[12px] text-gray-600 truncate" title={email}>
            {email || userLabel}
          </span>
          <Link href="/api/auth/signout" className="text-[11px] text-gray-400 hover:text-gray-600 shrink-0">
            로그아웃
          </Link>
        </div>
      </div>
    </aside>
  );
}
