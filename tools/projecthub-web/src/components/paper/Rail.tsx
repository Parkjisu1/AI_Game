"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Icon from "@/components/Icon";

/* ══════════════════════════════════════════════════════════════
   Rail — 좌측 내비게이션

   왜 바꾸는가
     이동 수단이 셋이었다: 상단 가로 탭 9개 + 하단 떠다니는 독 7개 + 모바일 탭바.
     셋 다 "어디로 갈 수 있나"만 말하고 **"지금 어디에 있나"** 는 아무도 말하지 않았다.
     게다가 9개 탭이 전부 동등해서 위계가 없다 — 매일 쓰는 작업 보드와
     한 달에 한 번 여는 설정이 같은 크기다.

   구조
     워크마크 → 3그룹(일 · 관찰 · 자료) → 하단(액션 · 사용자)
     그룹 라벨이 "이 도구로 뭘 하는가"를 드러낸다. 활성 항목은 잉크로 채운다(하나뿐).

   데스크톱 전용. 모바일은 기존 상단 Nav + 하단 탭바를 그대로 쓴다.
   ══════════════════════════════════════════════════════════════ */

type Item = { href: string; label: string; icon: string; owner?: boolean; badge?: "tasks" };

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: "일",
    items: [
      { href: "/", label: "홈", icon: "home" },
      { href: "/tasks", label: "작업 보드", icon: "tasks", badge: "tasks" },
    ],
  },
  {
    title: "관찰",
    items: [
      { href: "/agents", label: "AI 팀", icon: "cpu" },
      { href: "/balloonflow", label: "QA 검사", icon: "flask" },
      { href: "/simulator", label: "시뮬레이터", icon: "target" },
    ],
  },
  {
    title: "자료",
    items: [
      { href: "/research/supercent", label: "게임 성장 연구", icon: "search" },
      { href: "/levels", label: "레벨", icon: "flag" },
      { href: "/playable", label: "플레이어블", icon: "play" },
      { href: "/gallery", label: "설계 갤러리", icon: "image" },
      { href: "/assets-3d", label: "3D 제작실", icon: "image" },
      { href: "/roadmap", label: "로드맵", icon: "map" },
    ],
  },
];

const BOTTOM: Item[] = [
  { href: "/voice", label: "음성 명령", icon: "mic" },
  { href: "/settings", label: "설정", icon: "gear", owner: true },
];

export default function Rail({
  isOwner = false, userLabel = "Boss", role = "Owner",
}: { isOwner?: boolean; userLabel?: string; role?: string }) {
  const pathname = usePathname();
  const on = (h: string) => (h === "/" ? pathname === "/" : !!pathname?.startsWith(h));

  // 배지는 실데이터만. 못 읽으면 아예 안 보여준다(0 을 띄우면 "0건"이라는 거짓말이 된다).
  const [openTasks, setOpenTasks] = useState<number | null>(null);
  useEffect(() => {
    fetch("/api/tasks")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const list = Array.isArray(d) ? d : d?.tasks || [];
        if (!Array.isArray(list)) return;
        setOpenTasks(list.filter((t: { status?: string }) => t.status === "in_progress" || t.status === "review").length);
      })
      .catch(() => {});
  }, []);

  const renderItem = (it: Item) => (
    <Link key={it.href} href={it.href} className={`pp-rail-item press ${on(it.href) ? "on" : ""}`}>
      <Icon name={it.icon} size={15} />
      <span className="pp-rail-item-label">{it.label}</span>
      {it.badge === "tasks" && openTasks != null && openTasks > 0 && (
        <span className="pp-rail-badge">{openTasks}</span>
      )}
    </Link>
  );

  return (
    <aside className="pp-nav" aria-label="주요 메뉴">
      <Link href="/" className="pp-nav-mark">
        <span className="pp-nav-mark-box">
          <Icon name="cpu" size={14} />
        </span>
        <span className="pp-nav-mark-text">ProjectHub</span>
      </Link>

      <nav className="pp-nav-groups">
        {GROUPS.map((g) => (
          <div key={g.title} className="pp-nav-group">
            <div className="pp-nav-group-title">{g.title}</div>
            {g.items.filter((i) => !i.owner || isOwner).map(renderItem)}
          </div>
        ))}
      </nav>

      <div className="pp-nav-foot">
        {BOTTOM.filter((i) => !i.owner || isOwner).map(renderItem)}
        <div className="pp-nav-user">
          <span className="pp-nav-user-avatar">{(userLabel || "?").slice(0, 1)}</span>
          <span className="min-w-0">
            <span className="pp-nav-user-name">{userLabel}</span>
            <span className="pp-nav-user-role">{role}</span>
          </span>
        </div>
      </div>
    </aside>
  );
}
