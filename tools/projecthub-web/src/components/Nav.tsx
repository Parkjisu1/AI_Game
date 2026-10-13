"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

// 모바일 상단 바 (md 미만). 데스크톱은 TopNav + BottomDock.
const IS_CLEAN = process.env.NEXT_PUBLIC_APP_THEME === "clean";
const links = [
  { href: "/", label: "대시보드" },
  { href: "/roadmap", label: "로드맵" },
  { href: "/tasks", label: "작업 보드" },
  { href: "/voice", label: "음성 명령" },
  { href: "/agents", label: "AI 팀" },
  { href: "/balloonflow", label: "QA 검사", game: true },
  { href: "/gallery", label: "설계 갤러리", game: true },
  { href: "/pixelforge", label: "PixelForge", game: true },
  { href: "/levels", label: "레벨", game: true },
  { href: "/settings", label: "설정" },
].filter((l: { href: string; label: string; game?: boolean }) => !IS_CLEAN || !l.game);

export default function Nav({ isOwner = false }: { isOwner?: boolean }) {
  const pathname = usePathname();
  const visible = links.filter((l) => l.href !== "/settings" || isOwner);
  // 현재 경로의 페이지 라벨 (하단 탭바가 네비게이션 담당)
  const current = visible.find((l) => (l.href === "/" ? pathname === "/" : pathname?.startsWith(l.href)));

  if (pathname === "/login") return null;

  return (
    <nav
      className="md:hidden sticky top-0 z-30"
      style={{ background: "linear-gradient(180deg, rgba(6,11,22,0.94), rgba(6,11,22,0.75))", borderBottom: "1px solid var(--line)", backdropFilter: "blur(16px)" }}
    >
      <div className="px-4 py-3 flex items-center gap-2.5">
        <Link href="/" className="shrink-0 flex items-center gap-2">
          <span className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", boxShadow: "0 0 14px -2px rgba(34,211,238,.7)", color: "#041018" }}>
            <Icon name="cpu" size={15} />
          </span>
          <span className="text-[15px] font-bold tracking-hud neon-text-soft">PROJECTHUB</span>
        </Link>
        {current && current.href !== "/" && (
          <span className="text-sm font-medium text-gray-400 truncate">· {current.label}</span>
        )}
        <span className="ml-auto flex items-center gap-1 text-[9px] mono tracking-hud text-gray-500 shrink-0">
          <span className="dot dot-ok" /> ONLINE
        </span>
      </div>
    </nav>
  );
}
