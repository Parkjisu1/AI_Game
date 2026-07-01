"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

// 데스크톱 좌측 사이드바 (md+). 홀로그래픽 다크 테마. 실존 라우트만.
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
    <aside
      className="hidden md:flex flex-col fixed left-0 top-0 bottom-0 w-60 z-30 overflow-y-auto thin-scroll"
      style={{
        background: "linear-gradient(180deg, rgba(9,15,28,0.92), rgba(4,8,16,0.92))",
        borderRight: "1px solid var(--line)",
        backdropFilter: "blur(16px)",
      }}
    >
      <Link href="/" className="px-5 py-5 flex items-center gap-2.5 shrink-0">
        <span
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", boxShadow: "0 0 16px -2px rgba(34,211,238,.7)", color: "#041018" }}
        >
          <Icon name="cpu" size={17} />
        </span>
        <span className="text-[17px] font-bold tracking-hud neon-text-soft">PROJECTHUB</span>
      </Link>

      {/* 시스템 상태 배지 */}
      <div className="mx-4 mb-4 flex items-center gap-2 rounded-lg px-3 py-2 glass" style={{ borderRadius: 10 }}>
        <span className="dot dot-run" />
        <span className="text-[11px] mono tracking-hud text-gray-400">AI SYSTEM ONLINE</span>
      </div>

      <nav className="px-3 space-y-5 pb-6">
        {GROUPS.map((g) => (
          <div key={g.title}>
            <div className="px-2 text-[10px] font-semibold text-gray-400 uppercase tracking-hud mb-1.5">{g.title}</div>
            <div className="space-y-0.5">
              {g.items.filter((it) => !it.owner || isOwner).map((it) => {
                const on = active(it.href);
                return (
                  <Link
                    key={it.href}
                    href={it.href}
                    className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-all relative"
                    style={
                      on
                        ? { background: "rgba(34,211,238,0.12)", color: "var(--neon)", boxShadow: "inset 0 0 0 1px var(--line-strong), 0 0 18px -6px rgba(34,211,238,.5)", fontWeight: 600 }
                        : { color: "var(--text-dim)" }
                    }
                  >
                    {on && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full" style={{ background: "var(--neon)", boxShadow: "0 0 8px var(--neon)" }} />}
                    <Icon name={it.icon} size={17} /> {it.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="mt-auto px-5 py-4 text-[10px] mono text-gray-500 tracking-hud" style={{ borderTop: "1px solid var(--line)" }}>
        JARVIS_AIMED · AI PROJECT ASSISTANT
      </div>
    </aside>
  );
}
