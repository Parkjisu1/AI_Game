"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "대시보드" },
  { href: "/roadmap", label: "로드맵" },
  { href: "/tasks", label: "작업 보드" },
  { href: "/voice", label: "🎤 음성" },
  { href: "/agents", label: "AI 팀" },
  { href: "/balloonflow", label: "🎈 BalloonFlow" },
  { href: "/gallery", label: "🖼 갤러리" },
  { href: "/pixelforge", label: "🎨 PixelForge" },
  { href: "/settings", label: "설정" },
];

export default function Nav({ isOwner = false }: { isOwner?: boolean }) {
  const pathname = usePathname();
  // 설정 창은 소유자(본인)만
  const visible = links.filter((l) => l.href !== "/settings" || isOwner);
  // 현재 경로의 페이지 라벨 (모바일 미니헤더 표시용)
  const current = visible.find((l) => (l.href === "/" ? pathname === "/" : pathname?.startsWith(l.href)));

  return (
    <nav className="md:hidden border-b border-gray-200 bg-white sticky top-0 z-30">
      <div className="px-4 sm:px-6 py-3 flex items-center gap-3 sm:gap-8">
        <Link href="/" className="shrink-0">
          {/* 정적 워드마크 (그라데이션/이탤릭 제거) */}
          <span className="md:hidden text-xl font-bold tracking-tight text-gray-100">
            ProjectHub
          </span>
          <span className="hidden md:inline text-lg font-bold text-gray-100 tracking-tight">
            ProjectHub
          </span>
        </Link>

        {/* 모바일: 현재 페이지 라벨 (하단 탭바가 네비게이션 담당) */}
        {current && current.href !== "/" && (
          <span className="md:hidden text-sm font-medium text-gray-500 truncate">{current.label}</span>
        )}

        {/* Desktop links */}
        <div className="hidden md:flex gap-1">
          {visible.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              style={{ color: pathname === l.href ? "#ffffff" : "#cbd2dc" }}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                pathname === l.href ? "bg-black" : "hover:bg-gray-100"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
