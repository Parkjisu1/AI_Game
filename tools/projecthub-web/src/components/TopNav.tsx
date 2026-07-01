"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

// 데스크톱 상단 가로 네비 (md+). 모바일은 별도 상단 Nav + 하단 탭바.
const LINKS: { href: string; label: string; owner?: boolean }[] = [
  { href: "/", label: "대시보드" },
  { href: "/tasks", label: "작업 보드" },
  { href: "/agents", label: "AI 팀" },
  { href: "/voice", label: "음성 명령" },
  { href: "/gallery", label: "설계 갤러리" },
  { href: "/balloonflow", label: "QA 검사" },
  { href: "/roadmap", label: "로드맵" },
  { href: "/settings", label: "설정", owner: true },
];

export default function TopNav({ isOwner = false, userLabel = "Boss", role = "Owner" }: { isOwner?: boolean; userLabel?: string; role?: string }) {
  const pathname = usePathname();
  const active = (h: string) => (h === "/" ? pathname === "/" : pathname?.startsWith(h));
  const links = LINKS.filter((l) => !l.owner || isOwner);

  return (
    <header
      className="hidden md:flex fixed top-0 left-0 right-0 z-30 h-14 items-center gap-6 px-6"
      style={{
        background: "linear-gradient(180deg, rgba(6,11,22,0.92), rgba(6,11,22,0.7))",
        borderBottom: "1px solid var(--line)",
        backdropFilter: "blur(16px)",
      }}
    >
      <Link href="/" className="flex items-center gap-2.5 shrink-0">
        <span className="w-7 h-7 rounded-lg flex items-center justify-center"
          style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", boxShadow: "0 0 14px -2px rgba(34,211,238,.7)", color: "#041018" }}>
          <Icon name="cpu" size={15} />
        </span>
        <span className="text-[16px] font-bold tracking-hud neon-text-soft">ProjectHub</span>
      </Link>

      <nav className="flex items-center gap-1 flex-1 min-w-0 overflow-x-auto no-scrollbar">
        {links.map((l) => {
          const on = active(l.href);
          return (
            <Link key={l.href} href={l.href}
              className="px-3 py-1.5 rounded-lg text-[13px] font-medium whitespace-nowrap transition-all relative"
              style={on
                ? { color: "var(--neon)", background: "rgba(34,211,238,0.1)", boxShadow: "inset 0 0 0 1px var(--line-strong)" }
                : { color: "var(--text-dim)" }}>
              {l.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex items-center gap-3 shrink-0">
        <button className="relative w-9 h-9 rounded-lg flex items-center justify-center glass glass-hover text-gray-300" title="알림">
          <Icon name="bell" size={16} />
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
            style={{ background: "var(--err)", color: "#fff", boxShadow: "0 0 8px var(--err)" }}>5</span>
        </button>
        <button className="w-9 h-9 rounded-lg flex items-center justify-center glass glass-hover text-gray-300" title="메시지">
          <Icon name="chat" size={16} />
        </button>
        <div className="flex items-center gap-2 pl-2" style={{ borderLeft: "1px solid var(--line)" }}>
          <div className="text-right leading-tight">
            <div className="text-[13px] font-semibold text-gray-200">{userLabel}</div>
            <div className="text-[10px] mono tracking-hud" style={{ color: "var(--neon)" }}>{role}</div>
          </div>
          <span className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
            style={{ background: "rgba(34,211,238,0.15)", border: "1px solid var(--line-strong)", color: "var(--neon)" }}>
            <Icon name="users" size={16} />
          </span>
        </div>
      </div>
    </header>
  );
}
