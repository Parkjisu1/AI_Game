"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";

// JARVIS_AIMED 홀로그래픽 대시보드 — 실데이터(tasks·roles·sessions·node-runs)만 사용.

interface Task { _id?: string; title?: string; status?: string; priority?: string; assignee?: string; team?: string; progress?: number; updated_at?: string; }
interface Role { role: string; team?: string; description?: string; }
interface Sess { task_id?: string; task_title?: string; role?: string; model?: string; success?: boolean; created_at?: string; }

// 오비탈 파이프라인 노드 (워크플로우 단계)
const NODES = [
  { key: "analyze", label: "분석", sub: "Requirements", icon: "search" },
  { key: "plan", label: "계획", sub: "Planning", icon: "brain" },
  { key: "exec", label: "실행", sub: "Execution", icon: "code" },
  { key: "valid", label: "검증", sub: "Validation", icon: "eye" },
  { key: "deploy", label: "배포", sub: "Deployment", icon: "box" },
  { key: "monitor", label: "모니터링", sub: "Monitoring", icon: "signal" },
];

const TEAM_META: Record<string, { label: string; color: string; icon: string }> = {
  dev: { label: "Developer", color: "#22d3ee", icon: "code" },
  design: { label: "Designer", color: "#a78bfa", icon: "brain" },
  art: { label: "Artist", color: "#f472b6", icon: "image" },
  chat: { label: "Router", color: "#8ea3bf", icon: "target" },
};

const STATUS_META: Record<string, { dot: string; label: string }> = {
  in_progress: { dot: "dot-run", label: "진행 중" },
  review: { dot: "dot-wait", label: "리뷰" },
  todo: { dot: "dot-wait", label: "대기" },
  done: { dot: "dot-ok", label: "완료" },
};

function timeAgo(iso?: string) {
  if (!iso) return "";
  const d = Date.parse(iso);
  if (isNaN(d)) return "";
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}

function Waveform({ bars = 40, height = 40 }: { bars?: number; height?: number }) {
  return (
    <div className="wave" style={{ height }}>
      {Array.from({ length: bars }).map((_, i) => (
        <i key={i} style={{ animationDelay: `${(i % 12) * 0.09}s`, height: `${30 + ((i * 37) % 70)}%` }} />
      ))}
    </div>
  );
}

// ── JARVIS_AIMED 오비탈 허브 ──
function OrbitalHub({ running, live }: { running: number; live: boolean }) {
  const R = 40; // 노드 배치 반경 (%)
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[420px]">
      {/* 회전 링 (SVG) */}
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full">
        <defs>
          <radialGradient id="core" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#67e8f9" />
            <stop offset="60%" stopColor="#22d3ee" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </radialGradient>
        </defs>
        <g className="orbit-spin" style={{ transformOrigin: "50px 50px" }}>
          <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(56,189,248,0.18)" strokeWidth="0.4" strokeDasharray="1 3" />
        </g>
        <g className="orbit-spin-rev" style={{ transformOrigin: "50px 50px" }}>
          <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(34,211,238,0.28)" strokeWidth="0.5" strokeDasharray="8 4 2 4" />
        </g>
        <circle cx="50" cy="50" r="30" fill="none" stroke="rgba(56,189,248,0.14)" strokeWidth="0.4" />
        {/* 중심 → 노드 연결선 */}
        {NODES.map((_, i) => {
          const a = (-90 + i * 60) * (Math.PI / 180);
          return <line key={i} x1="50" y1="50" x2={50 + R * Math.cos(a)} y2={50 + R * Math.sin(a)} stroke="rgba(56,189,248,0.12)" strokeWidth="0.4" />;
        })}
        <circle cx="50" cy="50" r="22" fill="url(#core)" className="core-pulse" />
      </svg>

      {/* 중심 코어 텍스트 */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none">
        <div className="text-lg sm:text-2xl font-bold tracking-wide neon-text">JARVIS_AIMED</div>
        <div className="text-[9px] sm:text-[10px] mono tracking-hud text-gray-400 mt-1">AI PROJECT ASSISTANT</div>
        <div className="mt-2 flex items-center gap-1.5 text-[10px]">
          <span className={live ? "dot dot-run" : "dot dot-err"} />
          <span className="mono text-gray-400">{running} RUNNING</span>
        </div>
      </div>

      {/* 6 노드 */}
      {NODES.map((n, i) => {
        const a = (-90 + i * 60) * (Math.PI / 180);
        const x = 50 + R * Math.cos(a);
        const y = 50 + R * Math.sin(a);
        return (
          <div key={n.key} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${x}%`, top: `${y}%` }}>
            <div className="flex flex-col items-center gap-1">
              <div
                className="w-11 h-11 sm:w-12 sm:h-12 rounded-full flex items-center justify-center glass glass-hover"
                style={{ borderColor: "var(--line-strong)", color: "var(--neon)" }}
              >
                <Icon name={n.icon} size={18} />
              </div>
              <div className="text-[10px] sm:text-[11px] font-semibold text-gray-200 leading-none">{n.label}</div>
              <div className="text-[8px] mono tracking-hud text-gray-500 leading-none hidden sm:block">{n.sub}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [running, setRunning] = useState(0);
  const [live, setLive] = useState(false);
  const [cmd, setCmd] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    fetch("/api/tasks").then((r) => r.json()).then((d) => Array.isArray(d) && setTasks(d)).catch(() => {});
    fetch("/api/agents/roles").then((r) => r.json()).then((d) => setRoles(Array.isArray(d) ? d : d.roles || [])).catch(() => {});
    fetch("/api/agents/sessions?limit=6").then((r) => r.json()).then((d) => setSessions(d.sessions || [])).catch(() => {});
    fetch("/api/agents/node-runs").then((r) => r.json()).then((d) => { setRunning((d.running || []).length); }).catch(() => {});
    // LIVE = 실제 watcher 워커 heartbeat(3분 내) 기준 — "API 응답됨"이 아니라 진짜 가동 신호
    fetch("/api/assistant/status").then((r) => r.json()).then((d) => {
      setLive(Array.isArray(d?.workers) && d.workers.length > 0);
    }).catch(() => setLive(false));
  }, []);

  const stat = {
    total: tasks.length,
    inProgress: tasks.filter((t) => t.status === "in_progress").length,
    done: tasks.filter((t) => t.status === "done").length,
    todo: tasks.filter((t) => t.status === "todo").length,
    review: tasks.filter((t) => t.status === "review").length,
    urgent: tasks.filter((t) => t.priority === "urgent").length,
  };
  const activeTasks = tasks.filter((t) => t.status === "in_progress" || t.status === "review").slice(0, 5);
  const teamCounts = roles.reduce((acc, r) => { const t = r.team || "dev"; acc[t] = (acc[t] || 0) + 1; return acc; }, {} as Record<string, number>);

  const submitCmd = async () => {
    if (!cmd.trim() || sending) return;
    setSending(true);
    try {
      await fetch("/api/tasks", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: cmd.trim(), assignee: "hermes", status: "todo", priority: "medium", created_via: "dashboard" }),
      });
      router.push("/tasks");
    } catch { setSending(false); }
  };

  const cards = [
    { label: "전체 작업", value: stat.total, color: "var(--text)" },
    { label: "진행 중", value: stat.inProgress, color: "var(--neon)" },
    { label: "완료", value: stat.done, color: "var(--ok)" },
    { label: "오류·긴급", value: stat.urgent, color: "var(--err)" },
  ];

  return (
    <div className="space-y-4">
      {/* 상단 상태 바 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <span className="px-2.5 py-1 rounded-full glass text-[10px] mono tracking-hud flex items-center gap-1.5" style={{ borderRadius: 9999 }}>
            <span className={live ? "dot dot-run" : "dot dot-err"} /> AI SYSTEM {live ? "ONLINE" : "OFFLINE"}
          </span>
          <span className="text-[11px] mono text-gray-500 tracking-hud hidden sm:inline">JARVIS_AIMED · PROJECT ASSISTANT</span>
        </div>
        <span className="text-[11px] mono text-gray-500">{live ? "LIVE" : "—"}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* ── 좌: 음성 비서 + 시스템 ── */}
        <div className="lg:col-span-3 space-y-4">
          <div className="glass hud p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold tracking-hud neon-text-soft">음성 비서 JARVIS</span>
              <span className="flex items-center gap-1 text-[10px] mono text-emerald-500"><span className="dot dot-ok" />LIVE</span>
            </div>
            <Waveform bars={38} height={38} />
          </div>

          <div className="glass p-4">
            <div className="text-xs font-bold text-gray-300 mb-3 flex items-center gap-1.5"><Icon name="mic" size={14} /> 음성 명령</div>
            <div className="flex items-center gap-2 rounded-xl px-3 py-2" style={{ background: "rgba(6,11,22,0.6)", border: "1px solid var(--line)" }}>
              <input
                value={cmd} onChange={(e) => setCmd(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") submitCmd(); }}
                placeholder="명령을 말하거나 입력하세요…"
                className="flex-1 bg-transparent text-sm outline-none border-0"
              />
              <button onClick={() => router.push("/voice")} title="음성 명령"
                className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 float"
                style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018", boxShadow: "0 0 18px -2px rgba(34,211,238,.6)" }}>
                <Icon name="mic" size={16} />
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {["진행 상황 보고", "UI 수정", "회의 요약", "빌드 배포"].map((c) => (
                <button key={c} onClick={() => setCmd(c + "해줘")}
                  className="text-[11px] px-2.5 py-1 rounded-lg glass glass-hover text-gray-300">{c}</button>
              ))}
            </div>
          </div>

          {/* 시스템 상태 게이지 */}
          <div className="glass p-4">
            <div className="text-xs font-bold text-gray-300 mb-3 flex items-center gap-1.5"><Icon name="signal" size={14} /> 시스템 상태</div>
            <div className="flex items-center gap-3">
              <div className="relative w-16 h-16 shrink-0">
                <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                  <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(56,189,248,0.12)" strokeWidth="3" />
                  <circle cx="18" cy="18" r="15" fill="none" stroke="var(--neon)" strokeWidth="3" strokeLinecap="round"
                    strokeDasharray={`${live ? 88 : 20} 100`} style={{ filter: "drop-shadow(0 0 4px rgba(34,211,238,.8))" }} />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-sm font-bold neon-text">{live ? "정상" : "—"}</span>
                </div>
              </div>
              <div className="flex-1 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                <div className="flex justify-between"><span className="text-gray-500 mono">RUN</span><span className="neon-text-soft font-bold">{running}</span></div>
                <div className="flex justify-between"><span className="text-gray-500 mono">TODO</span><span className="text-amber-500 font-bold">{stat.todo}</span></div>
                <div className="flex justify-between"><span className="text-gray-500 mono">REVIEW</span><span className="text-amber-500 font-bold">{stat.review}</span></div>
                <div className="flex justify-between"><span className="text-gray-500 mono">TOTAL</span><span className="font-bold">{stat.total}</span></div>
              </div>
            </div>
          </div>
        </div>

        {/* ── 중앙: 오비탈 허브 ── */}
        <div className="lg:col-span-5 space-y-4">
          <div className="glass hud p-5 flex flex-col items-center">
            <div className="w-full flex items-center justify-center mb-2">
              <span className="px-3 py-1 rounded-full text-[10px] mono tracking-hud"
                style={live
                  ? { background: "rgba(34,211,238,0.1)", border: "1px solid var(--line-strong)", color: "var(--neon)" }
                  : { background: "rgba(251,90,107,0.08)", border: "1px solid rgba(251,90,107,0.35)", color: "var(--err)" }}
                title={live ? "watcher 워커 heartbeat 정상 (3분 내)" : "watcher heartbeat 없음 — hermes-watcher 서비스 확인 필요"}>
                {live ? "◇ AI SYSTEM ONLINE ◇" : "◇ AI SYSTEM OFFLINE ◇"}
              </span>
            </div>
            <OrbitalHub running={running} live={live} />
            <div className="w-full mt-2 flex items-center justify-center gap-2 text-gray-400">
              <Waveform bars={28} height={22} />
            </div>
            <div className="text-sm text-gray-400 mt-2">명령을 말씀해주세요, <span className="neon-text-soft font-semibold">Boss</span></div>
          </div>

          {/* 통계 카드 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {cards.map((c) => (
              <Link key={c.label} href="/tasks" className="glass glass-hover p-3.5 text-center">
                <div className="text-[10px] mono tracking-hud text-gray-500 mb-1">{c.label}</div>
                <div className="text-2xl sm:text-[28px] font-bold mono" style={{ color: c.color, textShadow: `0 0 14px ${c.color}44` }}>{c.value}</div>
              </Link>
            ))}
          </div>
        </div>

        {/* ── 우: 진행 작업 + AI 팀 + 활동 ── */}
        <div className="lg:col-span-4 space-y-4">
          <div className="glass p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-gray-300 flex items-center gap-1.5"><Icon name="box" size={14} /> 진행 중인 작업</span>
              <Link href="/tasks" className="text-[11px] neon-text-soft">전체 {stat.total} →</Link>
            </div>
            {activeTasks.length === 0 ? (
              <div className="text-sm text-gray-500 py-6 text-center mono">NO ACTIVE TASKS</div>
            ) : (
              <div className="space-y-2">
                {activeTasks.map((t) => {
                  const sm = STATUS_META[t.status || "todo"] || STATUS_META.todo;
                  const prog = typeof t.progress === "number" ? t.progress : (t.status === "review" ? 90 : 45);
                  return (
                    <Link key={t._id} href="/tasks" className="block glass glass-hover p-2.5">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className={`dot ${sm.dot}`} />
                        <span className="text-sm font-medium truncate flex-1">{t.title || "제목 없음"}</span>
                        <span className="text-[10px] mono neon-text-soft">{prog}%</span>
                      </div>
                      <div className="gauge-track h-1"><div className="gauge-fill h-full" style={{ width: `${prog}%` }} /></div>
                      <div className="mt-1.5 text-[10px] text-gray-500 truncate">{TEAM_META[t.team || "dev"]?.label || t.assignee || "hermes"}</div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          {/* AI 팀 현황 */}
          <div className="glass p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-gray-300 flex items-center gap-1.5"><Icon name="cpu" size={14} /> AI 팀 현황</span>
              <Link href="/agents" className="text-[11px] neon-text-soft">총 {roles.length} →</Link>
            </div>
            <div className="space-y-1.5">
              {Object.entries(TEAM_META).map(([k, m]) => (
                <div key={k} className="flex items-center gap-2.5 text-sm">
                  <span className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0" style={{ background: m.color + "22", color: m.color }}><Icon name={m.icon} size={13} /></span>
                  <span className="flex-1 text-gray-300">{m.label}</span>
                  <span className="mono font-bold" style={{ color: m.color }}>{teamCounts[k] || 0}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 최근 커뮤니케이션 */}
          <div className="glass p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-gray-300 flex items-center gap-1.5"><Icon name="signal" size={14} /> 최근 활동</span>
              <Link href="/agents" className="text-[11px] neon-text-soft">전체 →</Link>
            </div>
            {sessions.length === 0 ? (
              <div className="text-sm text-gray-500 py-4 text-center mono">NO ACTIVITY</div>
            ) : (
              <ul className="space-y-1.5">
                {sessions.map((s, i) => (
                  <li key={i} className="flex items-center gap-2.5 text-sm">
                    <span className={`dot ${s.success === false ? "dot-err" : "dot-ok"}`} />
                    <span className="flex-1 min-w-0 truncate"><span className="font-medium">{s.role || "agent"}</span> <span className="text-gray-500">— {s.task_title || s.task_id || ""}</span></span>
                    <span className="text-[10px] mono text-gray-500 shrink-0">{timeAgo(s.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {/* ── 하단 요약 바 ── */}
      <div className="glass p-4 flex items-center flex-wrap gap-x-8 gap-y-3">
        <span className="text-xs font-bold tracking-hud text-gray-400">오늘의 요약</span>
        {[
          { k: "완료된 작업", v: stat.done, c: "var(--ok)" },
          { k: "진행 중", v: stat.inProgress, c: "var(--neon)" },
          { k: "대기", v: stat.todo, c: "var(--warn)" },
          { k: "리뷰", v: stat.review, c: "var(--warn)" },
          { k: "전체", v: stat.total, c: "var(--text)" },
          { k: "실행 중 에이전트", v: running, c: "var(--neon-soft)" },
        ].map((s) => (
          <div key={s.k} className="flex items-center gap-2">
            <span className="text-[11px] text-gray-500">{s.k}</span>
            <span className="text-lg font-bold mono" style={{ color: s.c }}>{s.v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
