"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
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

interface Sess { task_id?: string; task_title?: string; role?: string; success?: boolean; created_at?: string; }

function ago(iso?: string) {
  if (!iso) return "";
  const s = Math.floor((Date.now() - Date.parse(iso)) / 1000);
  if (isNaN(s)) return "";
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}

export default function TopNav({ isOwner = false, userLabel = "Boss", role = "Owner", email = "" }: { isOwner?: boolean; userLabel?: string; role?: string; email?: string }) {
  const pathname = usePathname();
  const active = (h: string) => (h === "/" ? pathname === "/" : pathname?.startsWith(h));
  const links = LINKS.filter((l) => !l.owner || isOwner);

  const [notifs, setNotifs] = useState<Sess[]>([]);
  const [open, setOpen] = useState<null | "notif" | "user">(null);

  useEffect(() => {
    fetch("/api/agents/sessions?limit=8").then((r) => r.json()).then((d) => setNotifs(Array.isArray(d?.sessions) ? d.sessions : [])).catch(() => {});
  }, []);

  const errCount = notifs.filter((n) => n.success === false).length;
  // fixed + 최상위 z-index로 어떤 페이지 콘텐츠 위에도 확실히 표시
  const panel: React.CSSProperties = {
    position: "fixed", top: "3.6rem", right: "1.5rem", zIndex: 60,
    background: "rgba(9,15,28,0.98)", border: "1px solid var(--line-strong)",
    backdropFilter: "blur(16px)", borderRadius: 14,
    boxShadow: "0 24px 70px -18px rgba(0,0,0,.85), 0 0 34px -10px rgba(34,211,238,.35)",
  };

  return (
    <>
      <header
        className="hidden md:flex fixed top-0 left-0 right-0 items-center gap-6 px-6"
        style={{ height: "3.5rem", zIndex: 50, background: "linear-gradient(180deg, rgba(6,11,22,0.92), rgba(6,11,22,0.7))", borderBottom: "1px solid var(--line)", backdropFilter: "blur(16px)" }}
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
                className="px-3 py-1.5 rounded-lg text-[13px] font-medium whitespace-nowrap transition-all"
                style={on ? { color: "var(--neon)", background: "rgba(34,211,238,0.1)", boxShadow: "inset 0 0 0 1px var(--line-strong)" } : { color: "var(--text-dim)" }}>
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-3 shrink-0">
          {/* 알림 벨 */}
          <button onClick={() => setOpen(open === "notif" ? null : "notif")}
            className="relative w-9 h-9 rounded-lg flex items-center justify-center glass glass-hover text-gray-300" title="알림">
            <Icon name="bell" size={16} />
            {errCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
                style={{ background: "var(--err)", color: "#fff", boxShadow: "0 0 8px var(--err)" }}>{errCount > 9 ? "9+" : errCount}</span>
            )}
          </button>

          {/* 채팅 → AI팀 대화 로그 */}
          <Link href="/agents" className="w-9 h-9 rounded-lg flex items-center justify-center glass glass-hover text-gray-300" title="AI팀 대화 로그">
            <Icon name="chat" size={16} />
          </Link>

          {/* 아바타 → 사용자 메뉴 */}
          <button onClick={() => setOpen(open === "user" ? null : "user")}
            className="flex items-center gap-2 pl-2" style={{ borderLeft: "1px solid var(--line)" }}>
            <div className="text-right leading-tight">
              <div className="text-[13px] font-semibold text-gray-200">{userLabel}</div>
              <div className="text-[10px] mono tracking-hud" style={{ color: "var(--neon)" }}>{role}</div>
            </div>
            <span className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
              style={{ background: "rgba(34,211,238,0.15)", border: "1px solid var(--line-strong)", color: "var(--neon)" }}>
              <Icon name="users" size={16} />
            </span>
          </button>
        </div>
      </header>

      {/* ── 드롭다운 (fixed, 최상위) — 백드롭으로 바깥 클릭 닫기 ── */}
      {open && (
        <>
          <div className="hidden md:block fixed inset-0" style={{ zIndex: 55 }} onClick={() => setOpen(null)} />
          {open === "notif" && (
            <div className="hidden md:block w-80 p-2 fade-in" style={panel}>
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="text-xs font-bold text-gray-200 tracking-hud">알림 · 최근 활동</span>
                <Link href="/agents" onClick={() => setOpen(null)} className="text-[11px] neon-text-soft">전체 →</Link>
              </div>
              <div className="max-h-80 overflow-y-auto thin-scroll">
                {notifs.length === 0 ? (
                  <div className="text-sm text-gray-500 py-6 text-center mono">NO ACTIVITY</div>
                ) : notifs.map((n, i) => (
                  <Link key={i} href="/agents" onClick={() => setOpen(null)}
                    className="flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-white/5 transition-colors">
                    <span className={`dot ${n.success === false ? "dot-err" : "dot-ok"}`} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] truncate"><span className="font-medium">{n.role || "agent"}</span> <span className="text-gray-500">{n.success === false ? "실패" : "완료"}</span></div>
                      <div className="text-[11px] text-gray-500 truncate">{n.task_title || n.task_id || ""}</div>
                    </div>
                    <span className="text-[10px] mono text-gray-500 shrink-0">{ago(n.created_at)}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}
          {open === "user" && (
            <div className="hidden md:block w-60 p-2 fade-in" style={panel}>
              <div className="px-3 py-2 border-b" style={{ borderColor: "var(--line)" }}>
                <div className="text-sm font-semibold text-gray-200">{userLabel}</div>
                <div className="text-[11px] text-gray-500 truncate mono">{email || role}</div>
              </div>
              <div className="pt-1">
                {isOwner && (
                  <Link href="/settings" onClick={() => setOpen(null)} className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-white/5">
                    <Icon name="gear" size={16} /> 환경 설정
                  </Link>
                )}
                <Link href="/agents" onClick={() => setOpen(null)} className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-white/5">
                  <Icon name="cpu" size={16} /> AI 팀
                </Link>
                <a href="/api/auth/signout" className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-white/5" style={{ color: "var(--err)" }}>
                  <Icon name="undo" size={16} /> 로그아웃
                </a>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
