"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

// 데스크톱 하단 아이콘 독 (md+). 이미지 #2의 하단 독 재현.
const DOCK: { href: string; icon: string; label: string; owner?: boolean }[] = [
  { href: "/", icon: "home", label: "대시보드" },
  { href: "/tasks", icon: "tasks", label: "작업 보드" },
  { href: "/agents", icon: "cpu", label: "AI 팀" },
  { href: "/voice", icon: "mic", label: "음성 명령" },
  { href: "/gallery", icon: "image", label: "설계 갤러리" },
  { href: "/balloonflow", icon: "flask", label: "QA 검사" },
  { href: "/simulator", icon: "target", label: "시뮬레이터" },
  { href: "/settings", icon: "gear", label: "설정", owner: true },
];

export default function BottomDock({ isOwner = false }: { isOwner?: boolean }) {
  const pathname = usePathname();
  const active = (h: string) => (h === "/" ? pathname === "/" : pathname?.startsWith(h));
  const items = DOCK.filter((d) => !d.owner || isOwner);

  return (
    <div className="hidden md:flex fixed bottom-0 left-0 right-0 z-30 h-16 items-center justify-between px-6 pointer-events-none">
      <span className="text-[13px] font-bold tracking-hud mono neon-text-soft pointer-events-auto">JARVIS</span>

      <div className="pointer-events-auto flex items-center gap-1.5 px-3 py-2 rounded-2xl glass" style={{ boxShadow: "0 0 30px -10px rgba(34,211,238,.35), 0 10px 40px -12px rgba(0,0,0,.7)" }}>
        {items.map((d) => {
          const on = active(d.href);
          return (
            <Link key={d.href} href={d.href} title={d.label}
              className="group relative w-10 h-10 rounded-xl flex items-center justify-center transition-all"
              style={on
                ? { background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018", boxShadow: "0 0 18px -2px rgba(34,211,238,.7)" }
                : { color: "var(--text-dim)" }}>
              <Icon name={d.icon} size={19} />
              <span className="absolute -top-9 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md text-[10px] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity glass pointer-events-none">{d.label}</span>
            </Link>
          );
        })}
      </div>

      <Link href="/voice" aria-label="음성 명령" className="pointer-events-auto w-10 h-10 rounded-full flex items-center justify-center float"
        style={{ background: "radial-gradient(circle at 40% 35%, #67e8f9, var(--neon-deep))", boxShadow: "0 0 22px -2px rgba(34,211,238,.8)" }}>
        <span className="w-2.5 h-2.5 rounded-full bg-white/90" />
      </Link>
    </div>
  );
}
