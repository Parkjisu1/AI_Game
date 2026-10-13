"use client";

import { useState } from "react";

/* ══════════════════════════════════════════════════════════════
   Paper — 인터랙션 프리미티브

   테마 CSS 는 "색을 바꾸는" 층이고, 여기는 "구조를 만드는" 층이다.
   아이브로우 → 짧은 선언문 → 작은 본문 이라는 편집 리듬과,
   누르면 반응하는 컨트롤들이 여기 산다.

   규칙
   - 위계는 크기 하나가 아니라 서체·웨이트·색 세 축으로 만든다.
   - 색은 상태에만. 나머지는 잉크 4단.
   - 누른 느낌 100~160ms, scale 0.985 아래로는 내리지 않는다.
   ══════════════════════════════════════════════════════════════ */

/** 섹션 위의 작은 대문자 라벨. 제목 앞에 한 박자를 만든다. */
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="pp-eyebrow">{children}</div>
  );
}

/** 아이브로우 + 선언문 + (선택) 부연. 페이지마다 같은 리듬을 강제한다. */
export function SectionHead({
  eyebrow, title, sub, right,
}: { eyebrow?: string; title: React.ReactNode; sub?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="pp-sechead">
      <div className="min-w-0">
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h2 className="pp-title">{title}</h2>
        {sub && <p className="pp-sub">{sub}</p>}
      </div>
      {right && <div className="shrink-0 flex items-center gap-2">{right}</div>}
    </div>
  );
}

/** 탭이 3~5개일 때. 셀렉트보다 빠르고, 선택지가 다 보인다. */
export function Segmented<T extends string>({
  value, onChange, options,
}: { value: T; onChange: (v: T) => void; options: { value: T; label: string; count?: number }[] }) {
  return (
    <div className="pp-seg" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          className={`pp-seg-item press ${value === o.value ? "on" : ""}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count != null && <span className="pp-seg-count">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** 껐다 켜는 필터 하나. 켜지면 잉크가 찬다. */
export function Chip({
  on, onClick, children, count,
}: { on?: boolean; onClick?: () => void; children: React.ReactNode; count?: number }) {
  return (
    <button className={`pp-chip press ${on ? "on" : ""}`} onClick={onClick} aria-pressed={!!on}>
      {children}
      {count != null && <span className="pp-chip-count">{count}</span>}
    </button>
  );
}

export function Button({
  variant = "ghost", children, ...rest
}: { variant?: "primary" | "ghost" | "quiet" } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...rest} className={`pp-btn pp-btn-${variant} press ${rest.className || ""}`}>
      {children}
    </button>
  );
}

/** 빈 화면은 "없음"이 아니라 "다음에 뭘 하면 되는지"를 말해야 한다. */
export function EmptyState({
  title, hint, action,
}: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="pp-empty">
      <div className="pp-empty-title">{title}</div>
      {hint && <div className="pp-empty-hint">{hint}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/** 값이 주인공인 지표. 라벨은 작게 눕히고 숫자가 이긴다. */
export function Metric({
  label, value, delta, tone = "ink",
}: { label: string; value: React.ReactNode; delta?: string; tone?: "ink" | "ok" | "warn" | "err" | "accent" }) {
  return (
    <div className="pp-metric">
      <div className="pp-metric-label">{label}</div>
      <div className={`pp-metric-value tone-${tone}`}>{value}</div>
      {delta && <div className="pp-metric-delta">{delta}</div>}
    </div>
  );
}

/** 접히는 상세 — 기본은 닫힘. 스레드의 긴 기계 출력에 쓴다. */
export function Disclose({ summary, children }: { summary: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="pp-disclose">
      <button className="pp-disclose-sum press" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="pp-disclose-caret" data-open={open ? "1" : "0"}>▸</span>
        {summary}
      </button>
      {open && <div className="pp-disclose-body">{children}</div>}
    </div>
  );
}
