"use client";
import { useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";

type Team = "dev" | "design" | "art";

interface AgentRole {
  role: string;
  tool: string;
  model: string;
  description: string;
  display_order?: number;
  team?: Team;
  sub_team?: string;
  /** 직무 기술서 (JD). 호출 시 프롬프트 상단에 주입 */
  persona?: string;
}

const SUB_TEAM_LABELS: Record<string, string> = {
  general:      "공용",
  ui:           "UI",
  server:       "서버",
  ingame:       "인게임",
  outgame:      "아웃게임",
  background:   "배경",
  illustration: "원화",
  content:      "컨텐츠",
  level:        "레벨",
};
function subLabel(s?: string): string {
  if (!s) return "공용";
  return SUB_TEAM_LABELS[s] || s;
}

interface AgentSession {
  _id?: string;
  task_id: string;
  task_title?: string;
  role: string;
  model: string;
  duration_sec: number;
  success: boolean;
  error?: string | null;
  output_len?: number;
  output_preview?: string;
  created_at: string;
}

const EMPTY_ROLE: AgentRole = { role: "", tool: "claude", model: "", description: "", display_order: 10, team: "dev", sub_team: "general", persona: "" };

// 팀 메타 (색·라벨·아이콘)
const TEAMS: Record<Team, { label: string; color: string; glow: string; icon: string; description: string }> = {
  design: {
    label: "기획",
    color: "#f59e0b",
    glow: "rgba(245, 158, 11, 0.4)",
    icon: "ruler",
    description: "기획서·레벨 밸런스 (현재 미연결)",
  },
  dev: {
    label: "개발",
    color: "#22d3ee",
    glow: "rgba(34, 211, 238, 0.45)",
    icon: "code",
    description: "Unity 코드 수정 · 검증 · PR",
  },
  art: {
    label: "아트",
    color: "#ec4899",
    glow: "rgba(236, 72, 153, 0.4)",
    icon: "palette",
    description: "GPT Image 2 · 이미지 리뷰",
  },
};

const ROLE_ICON: Record<string, string> = {
  translator: "target",
  lead: "brain",
  main_coder: "code",
  sub_coder: "users",
  validator: "search",
  optimizer: "zap",
  optimization_reviewer: "search",
  reviewer: "eye",
  art_prompter: "edit",
  image_generator: "image",
  art_reviewer: "eye",
  designer: "tasks",
  balance_planner: "scale",
  design_reviewer: "doc",
};

// 기능별 5-레이어 파이프라인 — 실제 role 이름을 기능 레이어로 매핑 (첫 매칭 레이어에 배정)
const PIPE_LAYERS: { name: string; sub: string; match: (r: string) => boolean }[] = [
  { name: "Thinking", sub: "분석 · 이해", match: (r) => /translat|analy|research/i.test(r) },
  { name: "Planning", sub: "계획 · 분배", match: (r) => /(_pm|^lead$|_lead|planner|architect|split)/i.test(r) },
  { name: "Execution", sub: "실행 · 개발", match: (r) => /coder|prompter|generator|^designer$/i.test(r) },
  { name: "Review", sub: "검증 · 리뷰", match: (r) => /validat|review|optim/i.test(r) },
];
const pipeLayerOf = (role: string) => { for (let i = 0; i < PIPE_LAYERS.length; i++) if (PIPE_LAYERS[i].match(role)) return i; return -1; };

const OPTIONAL_ROLES = new Set(["optimizer", "optimization_reviewer"]);
const ACTIVE_WINDOW_MS = 300_000; // 5분

function iconOf(role: string) { return ROLE_ICON[role] || "bot"; }

function formatTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
  catch { return iso; }
}

function ago(iso: string, now: number): string {
  try {
    const s = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
    if (s < 60) return `${s}초 전`;
    if (s < 3600) return `${Math.floor(s / 60)}분 전`;
    return `${Math.floor(s / 3600)}시간 전`;
  } catch { return ""; }
}

function gradeOf(s: number): string {
  return s >= 95 ? "A+" : s >= 90 ? "A" : s >= 85 ? "B+" : s >= 80 ? "B" : s >= 70 ? "C" : "D";
}

export default function AgentsPage() {
  const [roles, setRoles] = useState<AgentRole[]>([]);
  const [rolesSource, setRolesSource] = useState("");
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [liveOn, setLiveOn] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [editing, setEditing] = useState<AgentRole | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [showCompleted, setShowCompleted] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [taskStats, setTaskStats] = useState({ inProgress: 0, done: 0 });
  const [costUsd, setCostUsd] = useState<number | null>(null);
  const [teamScore, setTeamScore] = useState<number | null>(null);
  const [gateData, setGateData] = useState<{ gates: { gate: string; result: string; n: number }[]; mergeStates: { state: string; n: number }[]; blocked: { id: string; title: string; reason: string; at: string }[] }>({ gates: [], mergeStates: [], blocked: [] });
  const [latestTask, setLatestTask] = useState<{ title?: string; description?: string; created_at?: string; status?: string } | null>(null);
  const [running, setRunning] = useState<{ task_id?: string; role?: string; started_at?: string }[]>([]);

  useEffect(() => {
    const load = () => fetch("/api/agents/node-runs").then((r) => r.json()).then((d) => setRunning(Array.isArray(d?.running) ? d.running : [])).catch(() => {});
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetch("/api/tasks").then((r) => r.json()).then((d) => {
      if (Array.isArray(d)) {
        setTaskStats({ inProgress: d.filter((t) => t.status === "in_progress").length, done: d.filter((t) => t.status === "done").length });
        const sorted = [...d].sort((a, b) => Date.parse(b.created_at || "") - Date.parse(a.created_at || ""));
        setLatestTask(sorted[0] || null);
      }
    }).catch(() => {});
    fetch("/api/agents/cost").then((r) => r.json()).then((d) => { if (d?.totals?.cost_usd != null) setCostUsd(Number(d.totals.cost_usd)); }).catch(() => {});
    fetch("/api/agents/scores").then((r) => r.json()).then((d) => {
      const t = Array.isArray(d?.totals) ? d.totals : [];
      const num = t.reduce((a: number, x: { avg?: number; count?: number }) => a + (x.avg || 0) * (x.count || 0), 0);
      const den = t.reduce((a: number, x: { count?: number }) => a + (x.count || 0), 0);
      if (den > 0) setTeamScore(num / den);
    }).catch(() => {});
    fetch("/api/agents/gates").then((r) => r.json()).then((d) => setGateData({ gates: d?.gates || [], mergeStates: d?.mergeStates || [], blocked: d?.blocked || [] })).catch(() => {});
  }, []);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  async function reloadAll() {
    const [r, s] = await Promise.all([
      fetch("/api/agents/roles").then((x) => x.json()),
      fetch("/api/agents/sessions?limit=80").then((x) => x.json()),
    ]);
    if (Array.isArray(r?.roles)) setRoles(r.roles);
    if (typeof r?.source === "string") setRolesSource(r.source);
    if (Array.isArray(s?.sessions)) setSessions(s.sessions);
  }

  useEffect(() => {
    reloadAll().finally(() => setLoading(false));
    fetch("/api/admin/allowed-users").then((r) => setIsAdmin(r.ok)).catch(() => setIsAdmin(false));
  }, []);

  // SSE
  useEffect(() => {
    const es = new EventSource("/api/agents/sessions/stream");
    es.addEventListener("ready", () => setLiveOn(true));
    es.addEventListener("session", (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data)?.session as AgentSession | undefined;
        if (!parsed?.task_id) return;
        setSessions((prev) => [parsed, ...prev].slice(0, 200));
      } catch { /* ignore */ }
    });
    es.addEventListener("error", () => setLiveOn(false));
    return () => { es.close(); setLiveOn(false); };
  }, []);

  // 역할별 활성 집합 (최근 5분)
  const activeRoles = useMemo(() => {
    const set = new Set<string>();
    for (const s of sessions) {
      if (now - new Date(s.created_at).getTime() <= ACTIVE_WINDOW_MS) set.add(s.role);
    }
    return set;
  }, [sessions, now]);

  // task_id별로 묶은 실시간 활동
  const groupedActivity = useMemo(() => {
    const map = new Map<string, { task_id: string; title: string; sessions: AgentSession[]; latest: number; active: boolean }>();
    for (const s of sessions) {
      const key = s.task_id;
      if (!key) continue;
      const g = map.get(key);
      const t = new Date(s.created_at).getTime();
      if (g) {
        g.sessions.push(s);
        if (t > g.latest) g.latest = t;
        if (now - t <= ACTIVE_WINDOW_MS) g.active = true;
      } else {
        map.set(key, {
          task_id: s.task_id,
          title: s.task_title || "(no title)",
          sessions: [s],
          latest: t,
          active: now - t <= ACTIVE_WINDOW_MS,
        });
      }
    }
    const arr = Array.from(map.values()).sort((a, b) => b.latest - a.latest);
    arr.forEach((g) => g.sessions.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()));
    return arr;
  }, [sessions, now]);

  const activeGroups = groupedActivity.filter((g) => g.active);
  const completedGroups = groupedActivity.filter((g) => !g.active).slice(0, 15);

  // 통계
  const stats = useMemo(() => {
    const m: Record<string, { count: number; success: number }> = {};
    for (const s of sessions) {
      const r = s.role;
      if (!m[r]) m[r] = { count: 0, success: 0 };
      m[r].count++;
      if (s.success) m[r].success++;
    }
    return m;
  }, [sessions]);

  // 팀별 역할 그룹화
  const byTeam = useMemo(() => {
    const g: Record<Team, AgentRole[]> = { design: [], dev: [], art: [] };
    for (const r of roles) {
      const t = (r.team || "dev") as Team;
      g[t].push(r);
    }
    for (const t of Object.keys(g) as Team[]) {
      g[t].sort((a, b) => (a.display_order ?? 99) - (b.display_order ?? 99));
    }
    return g;
  }, [roles]);

  async function saveRole() {
    if (!editing) return;
    setErr(""); setSaving(true);
    try {
      const res = await fetch("/api/agents/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editing),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) { setErr(j.error || "저장 실패"); return; }
      await reloadAll();
      setEditing(null);
    } finally { setSaving(false); }
  }

  async function deleteRole(role: string) {
    if (!confirm(`에이전트 "${role}" 삭제?`)) return;
    const res = await fetch(`/api/agents/roles?role=${encodeURIComponent(role)}`, { method: "DELETE" });
    if (!res.ok) { const j = await res.json().catch(() => ({})); alert(j.error || "삭제 실패"); return; }
    await reloadAll();
  }

  async function seedDefaults() {
    const res = await fetch("/api/agents/roles", { method: "PUT" });
    if (!res.ok) { const j = await res.json().catch(() => ({})); alert(j.error || "시드 실패"); return; }
    await reloadAll();
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2"><Icon name="cpu" size={24} /> AI 팀</h1>
          <p className="text-sm text-gray-500 mt-1 leading-relaxed">
            기획 · 개발 · 아트 팀 워크플로 + 실시간 활동
            {rolesSource === "default" && <span className="ml-2 text-amber-600">(기본값)</span>}
          </p>
        </div>
        <div className="flex items-center flex-wrap gap-2">
          <a href="/agents/cost" className="text-xs px-2.5 py-1.5 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded-lg border border-indigo-200 inline-flex items-center gap-1.5">
            <Icon name="dollar" size={14} /> 비용
          </a>
          <a href="/agents/design-teams" className="text-xs px-2.5 py-1.5 bg-pink-50 text-pink-700 hover:bg-pink-100 rounded-lg border border-pink-200 inline-flex items-center gap-1.5">
            <Icon name="flag" size={14} /> 팀 점수
          </a>
          <a href="/agents/eval" className="text-xs px-2.5 py-1.5 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 rounded-lg border border-emerald-200 inline-flex items-center gap-1.5">
            <Icon name="flask" size={14} /> Eval
          </a>
          <a href="/agents/batches" className="text-xs px-2.5 py-1.5 bg-violet-50 text-violet-700 hover:bg-violet-100 rounded-lg border border-violet-200 inline-flex items-center gap-1.5">
            <Icon name="box" size={14} /> Batch
          </a>
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className={`w-2 h-2 rounded-full ${liveOn ? "bg-emerald-500 animate-pulse" : "bg-gray-300"}`} />
            {liveOn ? "LIVE" : "오프라인"}
          </span>
          {isAdmin && rolesSource === "default" && (
            <button onClick={seedDefaults} className="text-xs text-blue-600 hover:underline">DB에 시드</button>
          )}
          {isAdmin && (
            <button onClick={() => { setErr(""); setEditing({ ...EMPTY_ROLE }); }} className="text-xs px-3 py-1.5 bg-black text-white rounded-lg hover:bg-gray-800">
              + 에이전트
            </button>
          )}
        </div>
      </div>

      {/* 커맨드센터 상단 스탯바 — 실데이터 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        {[
          { label: "진행 중 작업", value: String(taskStats.inProgress), icon: "box", color: "text-blue-500" },
          { label: "완료된 작업", value: String(taskStats.done), icon: "check", color: "text-emerald-500" },
          { label: "오류·이슈", value: String(sessions.filter((s) => s.success === false).length), icon: "ban", color: "text-rose-500" },
          { label: "총 비용", value: costUsd != null ? `$${costUsd.toFixed(2)}` : "—", icon: "dollar", color: "text-amber-500" },
          { label: "팀 점수", value: teamScore != null ? `${gradeOf(teamScore)} ${teamScore.toFixed(1)}` : "—", icon: "award", color: "text-violet-500" },
        ].map((c) => (
          <div key={c.label} className="rounded-xl border border-gray-200 bg-white p-3 min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] text-gray-500 mb-1"><Icon name={c.icon} size={13} /> {c.label}</div>
            <div className={`text-xl sm:text-2xl font-bold truncate ${c.color}`}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* 현재 요청 + 작업 흐름 stepper */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-sm font-bold mb-2 flex items-center gap-1.5"><Icon name="chat" size={15} /> 현재 요청</div>
          {latestTask ? (
            <div>
              <div className="text-sm font-medium">{latestTask.title}</div>
              {latestTask.description && <div className="text-xs text-gray-500 mt-1 line-clamp-2">{latestTask.description}</div>}
              <div className="text-[11px] text-gray-400 mt-1.5">{ago(latestTask.created_at || "", now)} · {latestTask.status}</div>
            </div>
          ) : <div className="text-sm text-gray-400">최근 요청 없음</div>}
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-sm font-bold mb-3 flex items-center gap-1.5"><Icon name="zap" size={15} /> 작업 흐름</div>
          <div className="flex items-center">
            {([["분석", "search"], ["계획", "tasks"], ["실행", "code"], ["검증", "flask"], ["배포", "rocket"]] as [string, string][]).map(([label, icon], i, arr) => {
              const active = label === "실행" && sessions.some((s) => now - new Date(s.created_at).getTime() < ACTIVE_WINDOW_MS);
              return (
                <div key={label} className="flex items-center flex-1 last:flex-none">
                  <div className="flex flex-col items-center gap-1 shrink-0">
                    <span className={`w-9 h-9 rounded-full flex items-center justify-center ${active ? "bg-blue-500 text-white" : "border border-gray-300 text-gray-500"}`}><Icon name={icon} size={16} /></span>
                    <span className={`text-[10px] ${active ? "text-blue-500 font-semibold" : "text-gray-500"}`}>{label}</span>
                  </div>
                  {i < arr.length - 1 && <span className="flex-1 h-px bg-gray-200 mx-1 mb-4" />}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* AI 워크플로우 (Pipeline) — 기능별 5-레이어, 실데이터(roles + 라이브 상태) */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 mb-4 overflow-x-auto thin-scroll">
        <div className="text-sm font-bold mb-3 flex items-center gap-1.5"><Icon name="cpu" size={15} /> AI 워크플로우 (Pipeline)</div>
        {(() => {
          const rs = (role: string): "running" | "error" | "done" | "idle" => {
            if (running.some((x) => x.role === role)) return "running";
            const r = sessions.find((s) => s.role === role);
            return r ? (r.success === false ? "error" : "done") : "idle";
          };
          const stCls = (s: string) => s === "running" ? "bg-emerald-500 text-white" : s === "error" ? "bg-rose-500/15 text-rose-500" : s === "done" ? "bg-blue-500/15 text-blue-500" : "bg-gray-500/15 text-gray-400";
          const stLabel = (s: string) => s === "running" ? "RUNNING" : s === "error" ? "ERROR" : s === "done" ? "DONE" : "WAITING";
          const col = (title: string, sub: string, items: { role: string; st: string }[]) => (
            <div key={title} className="flex-1 min-w-[150px]">
              <div className="text-xs font-semibold text-gray-700">{title}</div>
              <div className="text-[10px] text-gray-400 mb-2">{sub}</div>
              <div className="space-y-1.5">
                {items.length === 0 ? <div className="text-[11px] text-gray-300 py-1">—</div> : items.map((it) => (
                  <div key={it.role} className="rounded-lg border border-gray-200 p-2 flex items-center gap-1.5">
                    <Icon name={ROLE_ICON[it.role] || "bot"} size={13} />
                    <span className="text-[11px] truncate flex-1" title={it.role}>{it.role}</span>
                    <span className={`text-[8px] px-1 py-0.5 rounded font-semibold shrink-0 ${stCls(it.st)}`}>{stLabel(it.st)}</span>
                  </div>
                ))}
              </div>
            </div>
          );
          return (
            <div className="flex gap-3 min-w-[760px]">
              {PIPE_LAYERS.map((L, i) => col(L.name, L.sub, roles.filter((r) => pipeLayerOf(r.role) === i).map((r) => ({ role: r.role, st: rs(r.role) }))))}
              <div className="flex-1 min-w-[150px]">
                <div className="text-xs font-semibold text-gray-700">Deploy</div>
                <div className="text-[10px] text-gray-400 mb-2">배포 · 완료</div>
                <div className="space-y-1.5">
                  {([["Git Commit", "check"], ["Build", "box"], ["Slack Notify", "chat"]] as [string, string][]).map(([l, ic]) => (
                    <div key={l} className="rounded-lg border border-gray-200 p-2 flex items-center gap-1.5">
                      <Icon name={ic} size={13} /><span className="text-[11px] truncate flex-1">{l}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })()}
      </div>

      {/* Live Inspector — 실행 중 에이전트 (실데이터: node-runs) */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-bold flex items-center gap-1.5"><Icon name="cpu" size={15} /> Live Inspector <span className="text-[11px] text-gray-400 font-normal">실행 중 에이전트</span></div>
          <span className={`text-[11px] flex items-center gap-1 ${running.length ? "text-emerald-500" : "text-gray-400"}`}>
            <span className={`w-2 h-2 rounded-full ${running.length ? "bg-emerald-500 animate-pulse" : "bg-gray-300"}`} />{running.length ? `RUNNING ${running.length}` : "유휴"}
          </span>
        </div>
        {running.length === 0 ? (
          <div className="text-sm text-gray-400">실행 중인 에이전트가 없습니다.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {running.slice(0, 9).map((r, i) => (
              <div key={i} className="rounded-lg border border-gray-100 p-2.5 flex items-center gap-2 min-w-0">
                <span className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0"><Icon name={ROLE_ICON[r.role || ""] || "bot"} size={15} /></span>
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{r.role || "agent"}</div>
                  <div className="text-[11px] text-gray-400 truncate">#{(r.task_id || "").slice(-8)} · {ago(r.started_at || "", now)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 검증 게이트 측정 (P0 관측 — gate_events·merge_state 표면화) */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 mb-4">
        <div className="text-sm font-bold mb-2 flex items-center gap-1.5"><Icon name="flask" size={15} /> 검증 게이트 (최근 14일)</div>
        {gateData.gates.length === 0 ? (
          <div className="text-sm text-gray-400">아직 게이트 이벤트 없음 — task 처리 시 누적됩니다 (현재 컴파일 게이트 warn 측정 중).</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {Object.entries(gateData.gates.reduce((acc, g) => { if (!acc[g.gate]) acc[g.gate] = {}; acc[g.gate][g.result] = g.n; return acc; }, {} as Record<string, Record<string, number>>)).map(([gate, res]) => (
              <div key={gate} className="rounded-lg border border-gray-200 p-2.5 min-w-[140px]">
                <div className="text-xs font-semibold mb-1">{gate}</div>
                <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-[11px]">
                  {res.pass != null && <span className="text-emerald-500">pass {res.pass}</span>}
                  {res.warn != null && <span className="text-amber-500">warn {res.warn}</span>}
                  {res.block != null && <span className="text-rose-500">block {res.block}</span>}
                  {res.indeterminate != null && <span className="text-gray-400">검증불가 {res.indeterminate}</span>}
                  {res.merged != null && <span className="text-blue-500">merged {res.merged}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
        {gateData.blocked.length > 0 && (
          <div className="mt-3 border-t border-gray-100 pt-2">
            <div className="text-xs font-semibold text-rose-500 mb-1 flex items-center gap-1.5"><Icon name="ban" size={13} /> 차단된 task ({gateData.blocked.length}) — 검토 필요</div>
            <ul className="space-y-1">
              {gateData.blocked.slice(0, 6).map((b) => (
                <li key={b.id} className="text-xs flex items-center gap-2">
                  <a href="/tasks" className="truncate flex-1 hover:underline">{b.title}</a>
                  <span className="text-gray-400 shrink-0 truncate max-w-[40%]">{b.reason}</span>
                  <span className="text-gray-300 shrink-0">{ago(b.at, now)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 팀 플로우차트 */}
      <div className="rounded-xl border border-slate-800 mb-4 p-5 overflow-x-auto thin-scroll"
           style={{ background: "radial-gradient(ellipse at center, #0a1524 0%, #04070c 100%)" }}>
        <div className="min-w-[680px]">
        {/* 최상단: User Input → Translator */}
        <div className="flex flex-col items-center mb-6">
          <NodeBox icon="tasks" label="User Task Input" borderColor="#22d3ee" textColor="#67e8f9" />
          <Arrow color="#22d3ee" />
          {byTeam.dev.find((r) => r.role === "translator") && (
            <>
              <NodeBox
                icon={iconOf("translator")}
                label="Translator"
                borderColor="#a855f7"
                textColor="#c084fc"
                sub="자연어 해석 · 팀 라우팅"
                active={activeRoles.has("translator")}
                stats={stats["translator"]}
              />
              <div className="flex flex-col items-center py-1.5">
                <div className="w-px h-4 bg-slate-600" />
                <div className="flex items-center gap-2.5 rounded-full border border-slate-700 bg-slate-800/40 px-3 py-1">
                  <span className="text-[10px] text-slate-400 mr-0.5">팀 라우팅</span>
                  {(["design", "dev", "art"] as Team[]).map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 text-[11px] font-medium" style={{ color: TEAMS[t].color }}>
                      <Icon name={TEAMS[t].icon} size={12} /> {TEAMS[t].label}
                    </span>
                  ))}
                </div>
                <Arrow color="#64748b" />
              </div>
            </>
          )}
        </div>

        {/* 조직도 — 팀별 풀-와이드 행, 분과는 가로 정렬 */}
        <div className="space-y-5">
          {(["dev", "art", "design"] as Team[]).map((t) => (
            <TeamOrgChart
              key={t}
              team={t}
              roles={byTeam[t].filter((r) => r.role !== "translator")}
              activeRoles={activeRoles}
              stats={stats}
              isAdmin={isAdmin}
              onEdit={(r) => { setErr(""); setEditing({ ...r }); }}
              onDelete={deleteRole}
            />
          ))}
        </div>

        {/* 합류 → PR */}
        <div className="flex flex-col items-center mt-4">
          <div className="flex items-center gap-6 mb-1">
            <div className="w-px h-8 bg-slate-700" />
            <div className="w-px h-8 bg-cyan-500" />
            <div className="w-px h-8 bg-slate-700" />
          </div>
          <Arrow color="#10b981" />
          <NodeBox icon="rocket" label="Git / PR / main" borderColor="#10b981" textColor="#6ee7b7" sub="auto-merge → 팀 git pull" />
        </div>
        </div>
      </div>

      {/* Phase 3 보상 체계: 팀·분과별 품질 점수 패널 */}
      <TeamScorePanel />

      {/* Phase 5 자가 진화: 자동 학습된 프롬프트 패치 패널 */}
      <PatchesPanel />

      {/* 실시간 활동 — 진행 중 + 완료 분리 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-bold flex items-center gap-2"><Icon name="signal" size={18} /> 실시간 활동</h2>
          <span className="text-xs text-gray-400">총 {groupedActivity.length}개 태스크 · 진행중 {activeGroups.length}</span>
        </div>

        {/* 진행 중 */}
        <div className="mb-4">
          <h3 className="text-xs font-medium text-cyan-600 uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" /> 진행 중 (최근 5분)
          </h3>
          {activeGroups.length === 0 ? (
            <p className="text-sm text-gray-400 italic pl-4">대기 중</p>
          ) : (
            <ul className="space-y-2">
              {activeGroups.map((g) => (
                <TaskGroupCard key={g.task_id} group={g} now={now} active />
              ))}
            </ul>
          )}
        </div>

        {/* 완료 (접기) */}
        {completedGroups.length > 0 && (
          <div>
            <button
              onClick={() => setShowCompleted(!showCompleted)}
              className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5 hover:text-gray-700"
            >
              <span>{showCompleted ? "▼" : "▶"}</span>
              완료 / 오래된 ({completedGroups.length})
            </button>
            {showCompleted && (
              <ul className="space-y-2">
                {completedGroups.map((g) => (
                  <TaskGroupCard key={g.task_id} group={g} now={now} />
                ))}
              </ul>
            )}
          </div>
        )}

        {loading && <p className="text-sm text-gray-400 py-4">로딩 중...</p>}
      </div>

      {/* AI 팀 상태 요약 — 실데이터 (sessions·roles·cost) */}
      <div className="mt-4 rounded-xl border border-gray-200 bg-white p-3 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {(() => {
          const recent = sessions.filter((s) => now - new Date(s.created_at).getTime() < ACTIVE_WINDOW_MS);
          const activeAgents = new Set(recent.map((s) => s.role)).size;
          const total = roles.length;
          const todayStr = new Date(now).toISOString().slice(0, 10);
          const todayDone = sessions.filter((s) => s.success && (s.created_at || "").slice(0, 10) === todayStr).length;
          const succ = sessions.length ? Math.round((sessions.filter((s) => s.success).length / sessions.length) * 100) : 0;
          const avgDur = sessions.length ? (sessions.reduce((a, s) => a + (s.duration_sec || 0), 0) / sessions.length) : 0;
          const cells: { label: string; value: string; color?: string }[] = [
            { label: "총 에이전트", value: String(total) },
            { label: "활성", value: String(activeAgents), color: "text-emerald-500" },
            { label: "대기", value: String(Math.max(0, total - activeAgents)), color: "text-gray-400" },
            { label: "오늘 완료", value: String(todayDone) },
            { label: "성공률", value: `${succ}%`, color: "text-emerald-500" },
            { label: "평균 응답", value: `${avgDur.toFixed(1)}s` },
            { label: "총 비용", value: costUsd != null ? `$${costUsd.toFixed(2)}` : "—" },
          ];
          return cells.map((c) => (
            <div key={c.label} className="min-w-0">
              <div className="text-[11px] text-gray-500 truncate">{c.label}</div>
              <div className={`text-lg font-bold truncate ${c.color || ""}`}>{c.value}</div>
            </div>
          ));
        })()}
      </div>

      {/* 편집 모달 */}
      {editing && <EditModal editing={editing} setEditing={setEditing} err={err} saving={saving} onSave={saveRole} roles={roles} />}
    </div>
  );
}

/* ──────────────────────────────────────────────
   하위 컴포넌트
   ────────────────────────────────────────────── */

function NodeBox({
  icon, label, borderColor, textColor, sub, active, stats,
}: {
  icon: string; label: string; borderColor: string; textColor: string;
  sub?: string; active?: boolean; stats?: { count: number; success: number };
}) {
  return (
    <div
      className={`relative rounded-xl border-2 px-4 py-2.5 bg-slate-900/70 backdrop-blur transition-all ${
        active ? "scale-105 shadow-lg" : ""
      }`}
      style={{
        borderColor,
        boxShadow: active ? `0 0 20px ${borderColor}99, 0 0 40px ${borderColor}40` : `0 0 8px ${borderColor}30`,
      }}
    >
      {active && (
        <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-cyan-400 animate-pulse"
              style={{ boxShadow: `0 0 8px ${borderColor}` }} />
      )}
      <div className="flex items-center gap-2">
        <span className="text-xl" style={{ color: textColor }}><Icon name={icon} size={20} /></span>
        <div>
          <div className="text-sm font-semibold" style={{ color: textColor }}>{label}</div>
          {sub && <div className="text-[10px] text-slate-400 mt-0.5">{sub}</div>}
        </div>
      </div>
      {stats && stats.count > 0 && (
        <div className="mt-1.5 text-[10px] text-slate-500 flex items-center gap-2">
          <span>{stats.count}회</span>
          <span className={stats.success === stats.count ? "text-emerald-500" : "text-amber-500"}>
            ✓{stats.success}/{stats.count}
          </span>
        </div>
      )}
    </div>
  );
}

function Arrow({ color }: { color: string }) {
  return (
    <svg width="12" height="24" viewBox="0 0 12 24">
      <line x1="6" y1="0" x2="6" y2="18" stroke={color} strokeWidth="1.5" />
      <polyline points="2,16 6,22 10,16" fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

function TeamOrgChart({
  team, roles, activeRoles, stats, isAdmin, onEdit, onDelete,
}: {
  team: Team; roles: AgentRole[]; activeRoles: Set<string>; stats: Record<string, { count: number; success: number }>;
  isAdmin: boolean; onEdit: (r: AgentRole) => void; onDelete: (role: string) => void;
}) {
  const meta = TEAMS[team];
  const anyActive = roles.some((r) => activeRoles.has(r.role));

  // PM은 헤더에 따로, 나머지는 sub_team별로 그룹화
  const pm = roles.find((r) => r.role.endsWith("_pm"));
  const others = roles.filter((r) => !r.role.endsWith("_pm"));

  const groups = new Map<string, AgentRole[]>();
  for (const r of others) {
    const k = r.sub_team || "general";
    const arr = groups.get(k) || [];
    arr.push(r);
    groups.set(k, arr);
  }
  const ordered = Array.from(groups.entries()).sort((a, b) => {
    if (a[0] === "general") return -1;
    if (b[0] === "general") return 1;
    const minA = Math.min(...a[1].map((x) => x.display_order ?? 99));
    const minB = Math.min(...b[1].map((x) => x.display_order ?? 99));
    return minA - minB;
  });

  return (
    <div
      className="rounded-xl border-2 p-4"
      style={{
        borderColor: meta.color,
        background: `linear-gradient(180deg, ${meta.color}12 0%, transparent 60%)`,
        boxShadow: anyActive ? `0 0 25px ${meta.glow}` : "none",
      }}
    >
      {/* 팀 헤더 — 회사 부서장 자리 */}
      <div className="flex items-center gap-3 mb-3 pb-2 border-b" style={{ borderColor: `${meta.color}40` }}>
        <span style={{ color: meta.color }}><Icon name={meta.icon} size={28} /></span>
        <div className="flex-1">
          <div className="font-bold text-base" style={{ color: meta.color }}>{meta.label}팀</div>
          <div className="text-[11px] text-slate-400">{meta.description}</div>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-slate-500">{ordered.length}개 분과 · {others.length + (pm ? 1 : 0)}명</div>
          {anyActive && <span className="inline-block mt-0.5 w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />}
        </div>
      </div>

      {/* PM 박스 + 분과로 내려가는 연결선 */}
      {pm && (
        <div className="flex flex-col items-center mb-1">
          <div className="w-[200px]">
            <RoleBox role={pm} active={activeRoles.has(pm.role)} stats={stats[pm.role]} meta={meta} isAdmin={isAdmin} onEdit={onEdit} onDelete={onDelete} />
          </div>
          <div className="w-px h-4" style={{ background: meta.color, opacity: 0.6 }} />
        </div>
      )}

      {/* 분과 가로 라인 (조직도 가로줄) */}
      {ordered.length > 0 && (
        <div className="relative pt-1">
          {ordered.length > 1 && (
            <div
              className="absolute top-0 left-0 right-0 h-px"
              style={{ background: meta.color, opacity: 0.5 }}
            />
          )}
          {/* 분과 박스 가로 정렬 — 많아지면 가로 스크롤 */}
          <div className="overflow-x-auto pb-1 thin-scroll">
            <div className="flex gap-3 items-start min-w-fit pt-3">
              {ordered.length === 0 ? (
                <p className="text-xs text-slate-500 italic py-4">이 팀에 분과가 없습니다 (관리자가 + 새 역할로 추가)</p>
              ) : (
                ordered.map(([sub, list]) => (
                  <div key={sub} className="flex flex-col items-stretch shrink-0" style={{ width: 200 }}>
                    {/* 분과 위 짧은 세로선 */}
                    <div className="flex justify-center mb-1">
                      <div className="w-px h-3" style={{ background: meta.color, opacity: 0.5 }} />
                    </div>
                    {/* 분과 헤더 */}
                    <div
                      className="rounded-md text-center py-1.5 mb-2"
                      style={{
                        background: sub === "general" ? `${meta.color}25` : `${meta.color}18`,
                        border: `1px solid ${meta.color}55`,
                      }}
                    >
                      <div className="text-[11px] font-bold uppercase tracking-wide" style={{ color: meta.color }}>
                        {sub === "general" ? "공용 풀" : subLabel(sub)}
                      </div>
                      <div className="text-[9px] text-slate-400">{list.length}명</div>
                    </div>
                    {/* 분과 멤버 (세로 스택) */}
                    <div
                      className="rounded-lg p-2 flex-1 space-y-1.5"
                      style={{ background: `${meta.color}06`, border: `1px dashed ${meta.color}25` }}
                    >
                      {list.map((r) => (
                        <RoleBox key={r.role} role={r} active={activeRoles.has(r.role)} stats={stats[r.role]} meta={meta} isAdmin={isAdmin} onEdit={onEdit} onDelete={onDelete} />
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RoleBox({
  role: r, active, stats, meta, isAdmin, onEdit, onDelete,
}: {
  role: AgentRole; active: boolean; stats?: { count: number; success: number };
  meta: { color: string; glow: string }; isAdmin: boolean;
  onEdit: (r: AgentRole) => void; onDelete: (role: string) => void;
}) {
  const isOptional = OPTIONAL_ROLES.has(r.role);
  const isPlaceholder = r.description.startsWith("[미연결]");
  return (
    <div
      className={`relative rounded-lg border px-3 py-2 transition-all ${isPlaceholder ? "opacity-40" : ""}`}
      style={{
        borderColor: meta.color,
        borderStyle: isOptional || isPlaceholder ? "dashed" : "solid",
        background: active ? `${meta.color}20` : "rgba(15,23,42,0.6)",
        boxShadow: active ? `0 0 12px ${meta.glow}` : "none",
      }}
    >
      <div className="flex items-center gap-1.5">
        <span style={{ color: meta.color }}><Icon name={ROLE_ICON[r.role] || "bot"} size={16} /></span>
        <span className="font-mono text-[10px] font-bold uppercase" style={{ color: meta.color }}>{r.role}</span>
        {active && <span className="text-[9px] text-cyan-400 font-bold animate-pulse">● LIVE</span>}
        {isAdmin && (
          <div className="ml-auto flex gap-0.5">
            <button onClick={() => onEdit(r)} className="text-[9px] text-blue-400 hover:text-blue-300 px-1">편집</button>
            <button onClick={() => onDelete(r.role)} className="text-[9px] text-red-400 hover:text-red-300 px-1">×</button>
          </div>
        )}
      </div>
      <div className="text-[10px] font-mono text-slate-300 truncate mt-0.5" title={r.model}>{r.model}</div>
      <div className="text-[10px] text-slate-400 line-clamp-2 mt-0.5">{r.description}</div>
      {stats && stats.count > 0 && (
        <div className="mt-1 text-[9px] text-slate-500 flex items-center gap-1.5">
          <span>{stats.count}회</span>
          <span className={stats.success === stats.count ? "text-emerald-400" : "text-amber-400"}>
            ✓{stats.success}
          </span>
        </div>
      )}
    </div>
  );
}

function TaskGroupCard({
  group, now, active,
}: {
  group: { task_id: string; title: string; sessions: AgentSession[]; latest: number; active?: boolean };
  now: number; active?: boolean;
}) {
  return (
    <li className={`border rounded-lg p-3 ${active ? "border-cyan-300 bg-cyan-50/40" : "border-gray-200 bg-white"}`}>
      <div className="flex items-center gap-2 flex-wrap text-xs">
        <span className="font-mono text-[10px] text-gray-400">#{group.task_id.slice(-8)}</span>
        <span className="font-medium text-gray-700 truncate flex-1">{group.title}</span>
        <span className="text-[10px] text-gray-500">{ago(new Date(group.latest).toISOString(), now)}</span>
      </div>
      <div className="mt-2 flex items-center gap-1 flex-wrap">
        {group.sessions.map((s, i) => (
          <span
            key={(s._id || "") + i}
            title={`${s.role} · ${s.model} · ${(s.duration_sec ?? 0).toFixed(1)}s · ${s.success ? "성공" : "실패"} · ${formatTime(s.created_at)}`}
            className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-mono ${
              s.success
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : "bg-red-50 text-red-700 border border-red-200"
            }`}
          >
            <span className="inline-flex items-center"><Icon name={ROLE_ICON[s.role] || "bot"} size={12} /></span>
            <span>{s.role}</span>
            <span className="text-gray-400">{(s.duration_sec ?? 0).toFixed(1)}s</span>
          </span>
        ))}
      </div>
    </li>
  );
}

function EditModal({
  editing, setEditing, err, saving, onSave, roles,
}: {
  editing: AgentRole; setEditing: (r: AgentRole | null) => void;
  err: string; saving: boolean; onSave: () => void; roles: AgentRole[];
}) {
  const exists = roles.some((r) => r.role === editing.role);
  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4" onClick={() => !saving && setEditing(null)}>
      <div className="bg-white rounded-xl max-w-lg w-full p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-bold mb-3">{exists ? "에이전트 편집" : "새 에이전트"}</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase">역할 ID *</label>
            <input
              value={editing.role}
              onChange={(e) => setEditing({ ...editing, role: e.target.value })}
              placeholder="예: main_coder"
              disabled={exists}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono disabled:bg-gray-50"
              style={{ color: "#e6e9ef" }}
            />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase">팀</label>
              <select
                value={editing.team || "dev"}
                onChange={(e) => setEditing({ ...editing, team: e.target.value as Team, sub_team: "general" })}
                className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                style={{ color: "#e6e9ef" }}
              >
                <option value="dev">개발</option>
                <option value="design">기획</option>
                <option value="art">아트</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase">분과</label>
              <input
                list={`subteam-list-${editing.team || "dev"}`}
                value={editing.sub_team || "general"}
                onChange={(e) => setEditing({ ...editing, sub_team: e.target.value.trim().toLowerCase() || "general" })}
                placeholder="general"
                className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono"
                style={{ color: "#e6e9ef" }}
              />
              <datalist id="subteam-list-dev">
                <option value="general" /><option value="ui" /><option value="server" /><option value="ingame" /><option value="outgame" />
              </datalist>
              <datalist id="subteam-list-art">
                <option value="general" /><option value="ui" /><option value="background" /><option value="illustration" />
              </datalist>
              <datalist id="subteam-list-design">
                <option value="general" /><option value="content" /><option value="level" />
              </datalist>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase">도구</label>
              <select
                value={editing.tool}
                onChange={(e) => setEditing({ ...editing, tool: e.target.value })}
                className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                style={{ color: "#e6e9ef" }}
              >
                <option value="claude">claude</option>
                <option value="litellm">litellm</option>
                <option value="openai">openai</option>
                <option value="anthropic">anthropic</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase">순서</label>
              <input
                type="number"
                value={editing.display_order ?? 99}
                onChange={(e) => setEditing({ ...editing, display_order: parseInt(e.target.value, 10) || 99 })}
                className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                style={{ color: "#e6e9ef" }}
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase">모델 *</label>
            <input
              value={editing.model}
              onChange={(e) => setEditing({ ...editing, model: e.target.value })}
              placeholder="예: claude-opus-4-7 또는 gpt-image-2"
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono"
              style={{ color: "#e6e9ef" }}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase">설명</label>
            <textarea
              value={editing.description}
              onChange={(e) => setEditing({ ...editing, description: e.target.value })}
              rows={2}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              style={{ color: "#e6e9ef" }}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5"><Icon name="tasks" size={14} /> 직무 기술서 (Persona / JD)</span>
              <span className="text-[10px] normal-case text-gray-400 font-normal">
                {(editing.persona || "").length}/4000자 · 채용공고 그대로 붙여넣어도 OK
              </span>
            </label>
            <textarea
              value={editing.persona || ""}
              onChange={(e) => setEditing({ ...editing, persona: e.target.value.slice(0, 4000) })}
              rows={8}
              placeholder={`예) 당신은 모바일 캐주얼 게임의 UI 아티스트입니다.\n\n핵심 책임:\n- ...\n\n전문 역량:\n- ...`}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono"
              style={{ color: "#e6e9ef" }}
            />
            <p className="text-[10px] text-gray-400 mt-0.5">
              호출 시 프롬프트 최상단에 주입되어 LLM이 그 직무 전문가처럼 행동. 비워두면 미주입.
            </p>
          </div>
          {err && <p className="text-xs text-red-600">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={() => setEditing(null)} disabled={saving} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">취소</button>
          <button onClick={onSave} disabled={saving || !editing.role.trim() || !editing.model.trim()}
                  className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40">
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Phase 3 보상 체계 — 팀·분과별 품질 점수 패널
// ─────────────────────────────────────────────────────────────────
interface ScoreRow {
  team: string;
  sub_team: string;
  count: number;
  avg: number | null;
  min?: number;
  max?: number;
  last?: string;
}
interface RecentScore {
  _id: string;
  task_id: string;
  team: string;
  sub_team: string;
  role: string;
  score: number;
  verdict: string;
  created_at: string;
}

const TEAM_COLOR_MAP: Record<string, string> = {
  dev:    "#22d3ee",
  art:    "#ec4899",
  design: "#f59e0b",
};
const TEAM_LABEL_MAP: Record<string, string> = { dev: "개발", art: "아트", design: "기획" };
const TEAM_ICON_MAP: Record<string, string> = { dev: "code", art: "palette", design: "ruler" };
const SUB_LABEL_MAP: Record<string, string> = {
  general: "공용", ui: "UI", server: "서버", ingame: "인게임", outgame: "아웃게임",
  background: "배경", illustration: "원화", content: "컨텐츠", level: "레벨",
};
function _scoreColor(avg: number | null): string {
  if (avg == null) return "#475569";
  if (avg >= 85) return "#10b981"; // green
  if (avg >= 70) return "#22d3ee"; // cyan
  if (avg >= 55) return "#f59e0b"; // amber
  return "#ef4444";                 // red — 모델 자동 승격 발동 임박/진행
}

function TeamScorePanel() {
  const [totals, setTotals] = useState<ScoreRow[]>([]);
  const [recent, setRecent] = useState<RecentScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch("/api/agents/scores");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();
        if (cancelled) return;
        setTotals(Array.isArray(j.totals) ? j.totals : []);
        setRecent(Array.isArray(j.recent) ? j.recent : []);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const id = setInterval(load, 30000); // 30초마다 갱신
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // team별로 그룹화
  const byTeam = useMemo(() => {
    const m = new Map<string, ScoreRow[]>();
    for (const t of totals) {
      const arr = m.get(t.team) || [];
      arr.push(t);
      m.set(t.team, arr);
    }
    return m;
  }, [totals]);

  const isEmpty = !loading && totals.length === 0;

  return (
    <div
      className="rounded-xl border-2 p-5 mb-5"
      style={{
        background: "linear-gradient(180deg, #0f172a 0%, #1e293b 100%)",
        borderColor: "#334155",
        color: "#e2e8f0",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-bold flex items-center gap-2"><Icon name="award" size={18} /> 팀 보상 점수 (Phase 3)</h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Reviewer가 매긴 quality_score · 평균 &lt; 65 + 표본 5+이면 다음 호출 모델 자동 승격
          </p>
        </div>
        {!loading && (
          <span className="text-[10px] text-slate-500">
            총 {recent.length > 0 ? `${totals.length}개 분과 / ${recent.reduce((s) => s + 1, 0)}+ 건` : "0건"}
          </span>
        )}
      </div>

      {loading && <div className="text-xs text-slate-400 py-4 text-center">로딩 중...</div>}
      {err && <div className="text-xs text-red-400 py-2">불러오기 실패: {err}</div>}
      {isEmpty && (
        <div className="text-xs text-slate-500 py-4 text-center">
          아직 누적된 점수가 없습니다. Reviewer가 작업을 완료하면 여기에 표시됩니다.
        </div>
      )}

      {!loading && !isEmpty && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {(["dev", "art", "design"] as const).map((team) => {
            const rows = byTeam.get(team) || [];
            const teamColor = TEAM_COLOR_MAP[team];
            return (
              <div
                key={team}
                className="rounded-lg p-3"
                style={{
                  background: `${teamColor}10`,
                  border: `1px dashed ${teamColor}40`,
                }}
              >
                <div className="text-xs font-bold mb-2 flex items-center gap-1.5" style={{ color: teamColor }}>
                  <Icon name={TEAM_ICON_MAP[team]} size={14} /> {TEAM_LABEL_MAP[team]}
                </div>
                {rows.length === 0 ? (
                  <p className="text-[11px] text-slate-500 italic">기록 없음</p>
                ) : (
                  <div className="space-y-1.5">
                    {rows.map((r) => {
                      const c = _scoreColor(r.avg);
                      const pct = r.avg == null ? 0 : Math.max(0, Math.min(100, r.avg));
                      const promotionRisk = r.count >= 5 && r.avg !== null && r.avg < 65;
                      return (
                        <div key={`${r.team}/${r.sub_team}`} className="flex items-center gap-2 text-[11px]">
                          <span className="w-14 shrink-0 truncate" title={r.sub_team}>
                            {SUB_LABEL_MAP[r.sub_team] || r.sub_team}
                          </span>
                          <div className="flex-1 h-1.5 rounded-full bg-slate-700 overflow-hidden">
                            <div
                              className="h-full transition-all"
                              style={{ width: `${pct}%`, background: c }}
                            />
                          </div>
                          <span className="w-12 text-right tabular-nums font-mono" style={{ color: c }}>
                            {r.avg == null ? "—" : r.avg.toFixed(1)}
                          </span>
                          <span className="w-10 text-right tabular-nums text-slate-500">
                            {r.count}건
                          </span>
                          {promotionRisk && (
                            <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/20 text-red-300" title="모델 자동 승격 발동">
                              ⬆
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 최근 점수 기록 */}
      {recent.length > 0 && (
        <details className="mt-4 text-[11px]">
          <summary className="cursor-pointer text-slate-400 hover:text-slate-200">
            최근 기록 ({recent.length}건)
          </summary>
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
            {recent.map((r) => {
              const c = _scoreColor(r.score);
              return (
                <div key={r._id} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-800/50">
                  <span className="font-mono text-slate-500 w-16 truncate" title={r.task_id}>
                    {String(r.task_id).slice(-8)}
                  </span>
                  <span className="text-slate-400 w-20 truncate inline-flex items-center gap-1">
                    {TEAM_ICON_MAP[r.team] && <Icon name={TEAM_ICON_MAP[r.team]} size={12} />}
                    {TEAM_LABEL_MAP[r.team] || r.team}
                  </span>
                  <span className="text-slate-400 w-16 truncate">{SUB_LABEL_MAP[r.sub_team] || r.sub_team}</span>
                  <span className="text-slate-500 truncate flex-1" title={r.role}>{r.role}</span>
                  <span className="font-mono w-10 text-right" style={{ color: c }}>{r.score}</span>
                  <span className="text-slate-500 w-12 text-right">{r.verdict}</span>
                  <span className="text-slate-600 text-[10px] w-24 text-right truncate">
                    {new Date(r.created_at).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              );
            })}
          </div>
        </details>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Phase 5 자가 진화 — 자동 학습된 프롬프트 패치 패널
// ─────────────────────────────────────────────────────────────────
interface Patch {
  _id: string;
  role: string;
  patch_text: string;
  rationale: string;
  addresses_category?: string;
  status: "active" | "reverted" | "bad_case";
  score_before?: number | null;
  score_after?: number | null;
  samples_after?: number;
  created_at?: string;
  reverted_at?: string;
  revert_reason?: string;
  bad_case_reason?: string;
  bad_case_note?: string;
  marked_bad_at?: string;
}

function PatchesPanel() {
  const [active, setActive] = useState<Patch[]>([]);
  const [reverted, setReverted] = useState<Patch[]>([]);
  const [badCases, setBadCases] = useState<Patch[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionPatch, setActionPatch] = useState<Patch | null>(null);

  const load = async () => {
    try {
      const r = await fetch("/api/agents/patches");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setActive(j.active || []);
      setReverted(j.reverted || []);
      setBadCases(j.bad_cases || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  async function applyAction(
    patchId: string,
    action: "revert" | "bad_case",
    reason: string,
    note: string,
  ) {
    const r = await fetch("/api/agents/patches", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: patchId, action, reason, note }),
    });
    if (r.ok) {
      setActionPatch(null);
      load();
    } else {
      alert("실패 (admin 권한 필요)");
    }
  }

  return (
    <div
      className="rounded-xl border-2 p-5 mb-5"
      style={{
        background: "linear-gradient(180deg, #0f172a 0%, #1e293b 100%)",
        borderColor: "#475569",
        color: "#e2e8f0",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-bold flex items-center gap-2"><Icon name="dna" size={18} /> 자가 진화 — 자동 학습 패치 (Phase 5)</h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            실패 누적 시 reflection LLM이 짧은 추가 지시를 자동 주입. 점수 악화 시 자동 revert.
            <br />
            <span className="text-amber-300">Bad Case</span>로 등록된 패치는 reflection이 비슷한 방향 다시 제안 안 함.
          </p>
        </div>
        <span className="text-[10px] text-slate-500">
          active {active.length} · reverted {reverted.length} · bad {badCases.length}
        </span>
      </div>

      {loading && <div className="text-xs text-slate-400 py-3">로딩 중...</div>}

      {!loading && active.length === 0 && (
        <div className="text-xs text-slate-500 py-3">
          아직 학습된 패치 없음. 같은 role+category 실패가 임계값(2건) 누적되면 자동 생성됩니다.
        </div>
      )}

      {!loading && active.length > 0 && (
        <div className="space-y-2">
          {active.map((p) => {
            const sb = p.score_before;
            const sa = p.score_after;
            const delta = (typeof sb === "number" && typeof sa === "number") ? (sa - sb) : null;
            const deltaColor = delta == null ? "#64748b" : delta > 0 ? "#10b981" : delta < -2 ? "#ef4444" : "#f59e0b";
            return (
              <div
                key={p._id}
                className="rounded-lg p-3 text-xs"
                style={{ background: "#0b1220", border: "1px solid #334155" }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-cyan-300">{p.role}</span>
                  {p.addresses_category && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300">
                      {p.addresses_category}
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-2">
                    <span className="text-slate-500">표본 {p.samples_after ?? 0}</span>
                    {delta != null && (
                      <span style={{ color: deltaColor }}>
                        Δ {delta >= 0 ? "+" : ""}{delta.toFixed(1)}
                      </span>
                    )}
                    <button
                      onClick={() => setActionPatch(p)}
                      className="text-[10px] text-amber-400 hover:text-amber-300 underline"
                    >
                      처리...
                    </button>
                  </span>
                </div>
                <div className="text-slate-200 mb-1">{p.patch_text}</div>
                {p.rationale && (
                  <div className="text-[11px] text-slate-500 italic">근거: {p.rationale}</div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Bad Case 섹션 — 영구 차단 (reflection이 다시 제안 안 함) */}
      {badCases.length > 0 && (
        <div className="mt-3 rounded-lg p-3" style={{ background: "#1a0e08", border: "1px solid #7c2d12" }}>
          <div className="text-[11px] font-bold text-amber-300 mb-2 flex items-center gap-1.5">
            <Icon name="ban" size={14} /> Bad Cases — 방향성 어긋남으로 영구 차단됨 ({badCases.length}개)
          </div>
          <div className="space-y-1.5 text-[11px]">
            {badCases.map((p) => (
              <div key={p._id} className="px-2 py-1 rounded" style={{ background: "#0b1220" }}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-slate-300">{p.role}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-300">
                    {p.bad_case_reason === "off_direction" ? "방향 어긋남" :
                     p.bad_case_reason === "wrong_result" ? "결과 불일치" : (p.bad_case_reason || "기타")}
                  </span>
                </div>
                <div className="text-slate-400 mt-0.5">{p.patch_text.slice(0, 200)}</div>
                {p.bad_case_note && (
                  <div className="text-[10px] text-slate-500 italic mt-0.5">메모: {p.bad_case_note}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {reverted.length > 0 && (
        <details className="mt-3 text-[11px]">
          <summary className="cursor-pointer text-slate-400">
            최근 revert된 패치 ({reverted.length}개) — 잠시 빼둔 상태, LLM이 다시 비슷한 방향 제안 가능
          </summary>
          <div className="mt-2 space-y-1">
            {reverted.map((p) => (
              <div key={p._id} className="px-2 py-1 rounded flex items-start gap-2" style={{ background: "#0b1220" }}>
                <span className="font-mono text-slate-400">{p.role}</span>
                <div className="flex-1 text-slate-500">
                  <span className="line-through">{p.patch_text.slice(0, 100)}</span>
                  {p.revert_reason && (
                    <div className="text-[10px] text-red-400/70 mt-0.5">↩ {p.revert_reason}</div>
                  )}
                </div>
                <button
                  onClick={() => setActionPatch(p)}
                  className="text-[10px] text-amber-400 hover:text-amber-300 underline shrink-0"
                  title="이 패치를 Bad Case로 영구 차단"
                >
                  Bad Case로
                </button>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* 처리 모달 — revert 또는 Bad Case 선택 */}
      {actionPatch && (
        <PatchActionModal
          patch={actionPatch}
          onClose={() => setActionPatch(null)}
          onApply={applyAction}
        />
      )}
    </div>
  );
}

function PatchActionModal({
  patch, onClose, onApply,
}: {
  patch: Patch;
  onClose: () => void;
  onApply: (patchId: string, action: "revert" | "bad_case", reason: string, note: string) => void;
}) {
  const [reason, setReason] = useState<"off_direction" | "wrong_result" | "other">("off_direction");
  const [note, setNote] = useState("");
  const isReverted = patch.status === "reverted";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="rounded-xl p-5 max-w-lg w-full text-sm"
        style={{ background: "#0f172a", border: "1px solid #475569", color: "#e2e8f0" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-bold mb-2">패치 처리</h3>
        <div className="text-[11px] text-slate-400 mb-3">
          역할 <span className="font-mono text-cyan-300">{patch.role}</span>의 패치:
        </div>
        <div className="text-xs p-2 rounded mb-4" style={{ background: "#0b1220", border: "1px solid #334155" }}>
          {patch.patch_text}
        </div>

        {!isReverted && (
          <div className="mb-4 p-3 rounded text-xs" style={{ background: "#1e293b" }}>
            <div className="font-semibold mb-1 text-slate-300">옵션 A — 잠시 빼기 (revert)</div>
            <div className="text-[11px] text-slate-400 mb-2">
              일시적 노이즈일 수도 있을 때. LLM은 비슷한 방향을 다시 제안할 수 있음.
            </div>
            <button
              onClick={() => onApply(patch._id, "revert", "", note)}
              className="px-3 py-1 rounded text-xs"
              style={{ background: "#475569", color: "#e2e8f0" }}
            >
              revert만
            </button>
          </div>
        )}

        <div className="mb-4 p-3 rounded text-xs" style={{ background: "#1a0e08", border: "1px solid #7c2d12" }}>
          <div className="font-semibold mb-1 text-amber-300">
            옵션 {isReverted ? "" : "B — "}Bad Case로 영구 차단
          </div>
          <div className="text-[11px] text-slate-400 mb-2">
            방향 자체가 잘못됐거나 결과가 의도와 어긋난 경우. reflection이 다시는 비슷한 방향 제안 안 함.
          </div>
          <label className="text-[11px] block mb-1 text-slate-300">사유</label>
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value as "off_direction" | "wrong_result" | "other")}
            className="w-full mb-2 px-2 py-1 rounded text-xs"
            style={{ background: "#0b1220", color: "#e2e8f0", border: "1px solid #334155" }}
          >
            <option value="off_direction">방향 자체가 어긋남 (제작 의도와 정반대 또는 무관)</option>
            <option value="wrong_result">결과 불일치 (의도한 출력과 다른 결과 유도)</option>
            <option value="other">기타 (메모로 명시)</option>
          </select>
          <label className="text-[11px] block mb-1 text-slate-300">메모 (선택, 최대 500자)</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value.slice(0, 500))}
            rows={2}
            className="w-full px-2 py-1 rounded text-xs mb-2"
            style={{ background: "#0b1220", color: "#e2e8f0", border: "1px solid #334155" }}
            placeholder="예: 페르소나 의도와 정반대 — 항상 X하지 말라고 했는데 패치는 X하라고 시킴"
          />
          <button
            onClick={() => onApply(patch._id, "bad_case", reason, note)}
            className="px-3 py-1 rounded text-xs font-semibold inline-flex items-center gap-1.5"
            style={{ background: "#dc2626", color: "white" }}
          >
            <Icon name="ban" size={14} /> Bad Case로 등록
          </button>
        </div>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="text-xs text-slate-400 hover:text-slate-200"
          >
            취소
          </button>
        </div>
      </div>
    </div>
  );
}
