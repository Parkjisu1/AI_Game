"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import { useEffect, useState } from "react";

/**
 * 계기판 셸 — 상단 상태 스트립 + 그룹 탭 + 하위 탭 (NEXT_PUBLIC_APP_THEME=instrument 전용).
 *
 * 화면이 16개를 넘어 한 줄 탭으로는 안 담긴다. 그룹(6) → 화면 2단으로 나누고,
 * 하위 탭에는 실제 라우트를 함께 적어 "지금 어디에 있는지"를 주소 수준까지 노출한다.
 * 상태 스트립은 어느 화면에 있든 시스템이 살아있는지 보여준다.
 */

type Screen = { href: string; label: string; owner?: boolean };
type Group = { id: string; label: string; items: Screen[] };

const GROUPS: Group[] = [
  { id: "ws", label: "워크스페이스", items: [
    { href: "/", label: "대시보드" },
    { href: "/tasks", label: "작업 보드" },
    { href: "/roadmap", label: "로드맵" },
  ]},
  { id: "ai", label: "AI", items: [
    { href: "/agents", label: "AI 팀" },
    { href: "/agents/cost", label: "비용" },
    { href: "/voice", label: "음성 명령" },
  ]},
  { id: "game", label: "게임", items: [
    { href: "/balloonflow", label: "QA 검사" },
    { href: "/simulator", label: "시뮬레이터" },
    { href: "/gallery", label: "설계 갤러리" },
    { href: "/assets-3d", label: "3D 제작실" },
    { href: "/levels", label: "레벨" },
    { href: "/agents/batches", label: "레벨 배치" },
  ]},
  { id: "quality", label: "품질", items: [
    { href: "/agents/design-teams", label: "팀 점수" },
    { href: "/agents/eval", label: "Eval" },
  ]},
  { id: "sys", label: "시스템", items: [
    { href: "/settings", label: "설정", owner: true },
  ]},
];

function groupOf(pathname: string): Group {
  // 더 긴 href 가 먼저 매치되도록 (예: /agents/cost 가 /agents 보다 우선)
  let best: { g: Group; len: number } | null = null;
  for (const g of GROUPS) {
    for (const it of g.items) {
      const hit = it.href === "/" ? pathname === "/" : pathname.startsWith(it.href);
      if (hit && (!best || it.href.length > best.len)) best = { g, len: it.href.length };
    }
  }
  return best ? best.g : GROUPS[0];
}

export default function InstrumentNav({
  isOwner,
  userLabel,
  email,
}: {
  isOwner: boolean;
  userLabel: string;
  email: string;
}) {
  const pathname = usePathname() || "/";
  const [stat, setStat] = useState<{ online: boolean }>({ online: false });

  // 상태 스트립 — 워커 온라인 여부만.
  //
  // ⚠️ 여기서 /api/tasks 를 폴링하지 말 것.
  // 목록 API는 project 스코프 없이 부르면 balloonflow 의 image_base64(약 105MB)까지
  // 훑느라 45초를 넘겨 응답이 없다. 30초 주기로 부르면 응답 없는 요청이 계속 쌓여
  // 열어둔 탭이 죽는다 (2026-08-03 실장애). 진행/검수 건수가 필요하면
  // 목록이 아니라 카운트 전용 API를 새로 만들어 쓴다.
  useEffect(() => {
    let alive = true;
    const load = async () => {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), 8000); // 느린 응답이 쌓이지 않게 강제 중단
      try {
        const r = await fetch("/api/assistant/status", { signal: ctl.signal });
        const a = r.ok ? await r.json() : null;
        if (!alive) return;
        setStat((s) => ({ ...s, online: !!(a && (a.online ?? a.alive ?? a.ok)) }));
      } catch {
        /* 상태 표시는 부가 정보 — 실패를 화면에 띄우지 않는다 */
      } finally {
        clearTimeout(timer);
      }
    };
    load();
    const id = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (pathname === "/login") return null;

  const current = groupOf(pathname);
  const visible = (items: Screen[]) => items.filter((i) => !i.owner || isOwner);

  return (
    <div className="hidden md:block fixed top-0 left-0 right-0 z-40 instr-shell">
      {/* 상태 스트립 */}
      <div className="instr-strip">
        <div className="instr-kv">
          <span className="k">INSTANCE</span>
          <span className="v">PROJECTHUB</span>
        </div>
        <div className="instr-kv">
          <span className="k">AI 워커</span>
          <span className={`v ${stat.online ? "ok" : "off"}`}>{stat.online ? "ONLINE" : "OFFLINE"}</span>
        </div>
        <div className="instr-spacer" />
        <div className="instr-kv right">
          <span className="k">{email || "—"}</span>
          <span className="v">{userLabel}</span>
        </div>
        <button className="instr-out" onClick={() => signOut({ callbackUrl: "/login" })}>
          로그아웃
        </button>
      </div>

      {/* 그룹 탭 */}
      <nav className="instr-tabs">
        {GROUPS.map((g, i) => {
          const items = visible(g.items);
          if (!items.length) return null;
          return (
            <Link
              key={g.id}
              href={items[0].href}
              className={`instr-tab${g.id === current.id ? " on" : ""}`}
            >
              <span className="n">{String(i + 1).padStart(2, "0")}</span>
              {g.label}
              <span className="cnt font-mono">{items.length}</span>
            </Link>
          );
        })}
      </nav>

      {/* 하위 탭 — 현재 그룹의 화면들 */}
      <nav className="instr-sub">
        <span className="cap">화면 {visible(current.items).length}</span>
        {visible(current.items).map((it) => {
          const on = it.href === "/" ? pathname === "/" : pathname.startsWith(it.href);
          return (
            <Link key={it.href} href={it.href} className={`instr-stab${on ? " on" : ""}`}>
              {it.label}
              <span className="rt font-mono">{it.href}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
