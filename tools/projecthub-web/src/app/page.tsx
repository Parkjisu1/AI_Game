"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";

// JARVIS 스타일 대시보드 — 실데이터(tasks·roles·sessions·node-runs)만 사용.
// projects/CPU/AI추천은 실데이터 없음 → 표시 안 함(가짜 수치 미사용).

interface Task { _id?: string; title?: string; status?: string; priority?: string; assignee?: string; team?: string; updated_at?: string; }
interface Role { role: string; team?: string; description?: string; }
interface Sess { task_id?: string; task_title?: string; role?: string; model?: string; success?: boolean; created_at?: string; }
interface Asset { _id?: string; images?: { filename: string }[]; }
interface Project { id: string; name: string; subtitle?: string; icon?: string; progress: number; done: number; total: number; href: string; }

const AGENT_CARDS: { role: string; name: string; desc: string; icon: string; color: string }[] = [
  { role: "translator", name: "Translator", desc: "기획 분석 · 라우팅", icon: "target", color: "#a855f7" },
  { role: "lead", name: "Lead", desc: "PM · 작업 조율", icon: "brain", color: "#8b5cf6" },
  { role: "main_coder", name: "Developer", desc: "코드 개발", icon: "code", color: "#22d3ee" },
  { role: "validator", name: "Validator", desc: "QA · 검증", icon: "search", color: "#10b981" },
  { role: "reviewer", name: "Reviewer", desc: "코드 리뷰 게이트", icon: "eye", color: "#f59e0b" },
  { role: "optimizer", name: "Optimizer", desc: "성능 최적화", icon: "zap", color: "#ec4899" },
];

const QUICK_CHIPS = [
  "새 게임 기획해줘", "UI 디자인 만들어줘", "버그 수정해줘", "밸런스 분석해줘", "빌드 & 배포해줘",
];

const TEAM_BADGE: Record<string, { label: string; cls: string }> = {
  dev: { label: "개발", cls: "bg-cyan-50 text-cyan-700" },
  art: { label: "아트", cls: "bg-pink-50 text-pink-700" },
  design: { label: "기획", cls: "bg-amber-50 text-amber-700" },
  chat: { label: "대화", cls: "bg-gray-100 text-gray-500" },
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

export default function Dashboard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [running, setRunning] = useState<number>(0);
  const [live, setLive] = useState(false);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [cmd, setCmd] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    fetch("/api/tasks").then((r) => r.json()).then((d) => Array.isArray(d) && setTasks(d)).catch(() => {});
    fetch("/api/agents/roles").then((r) => r.json()).then((d) => setRoles(Array.isArray(d) ? d : d.roles || [])).catch(() => {});
    fetch("/api/agents/sessions?limit=8").then((r) => r.json()).then((d) => setSessions(d.sessions || [])).catch(() => {});
    fetch("/api/agents/node-runs").then((r) => r.json()).then((d) => { const n = (d.running || []).length; setRunning(n); setLive(true); }).catch(() => {});
    fetch("/api/designs?limit=8").then((r) => r.json()).then((d) => setAssets(Array.isArray(d) ? d : d.designs || [])).catch(() => {});
    fetch("/api/projects").then((r) => r.json()).then((d) => setProjects(d.projects || [])).catch(() => {});
  }, []);

  const stat = {
    inProgress: tasks.filter((t) => t.status === "in_progress").length,
    done: tasks.filter((t) => t.status === "done").length,
    todo: tasks.filter((t) => t.status === "todo").length,
    review: tasks.filter((t) => t.status === "review").length,
    urgent: tasks.filter((t) => t.priority === "urgent").length,
  };
  const todoList = tasks.filter((t) => t.status === "todo" || t.status === "in_progress").slice(0, 6);
  const roleSet = new Set(roles.map((r) => r.role));

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
    { label: "전행 중", value: stat.inProgress, icon: "box", color: "text-blue-600" },
    { label: "완료", value: stat.done, icon: "check", color: "text-emerald-600" },
    { label: "할 일", value: stat.todo, icon: "clock", color: "text-amber-600" },
    { label: "긴급", value: stat.urgent, icon: "ban", color: "text-rose-600" },
  ];

  return (
    <div className="space-y-5">
      {/* 히어로 */}
      <div className="rounded-2xl border border-gray-200 bg-white p-5 sm:p-7 relative overflow-hidden">
        <div className="absolute right-4 top-4 hidden sm:flex items-center gap-1.5 text-xs text-emerald-500">
          <span className={`w-2 h-2 rounded-full ${live ? "bg-emerald-500 animate-pulse" : "bg-gray-400"}`} /> {live ? "LIVE" : "오프라인"}
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold">안녕하세요, <span className="text-blue-500">Boss</span>.</h1>
        <p className="text-sm sm:text-base text-gray-500 mt-1">오늘도 멋진 하루가 될 겁니다.</p>

        {/* 명령 입력 바 */}
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2">
          <Icon name="search" size={16} />
          <input
            value={cmd} onChange={(e) => setCmd(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitCmd(); }}
            placeholder="명령을 입력하거나 마이크를 사용하세요…"
            className="flex-1 bg-transparent text-sm outline-none border-0"
          />
          <button onClick={() => router.push("/voice")} title="음성 명령"
            className="w-9 h-9 rounded-full bg-blue-500 text-white flex items-center justify-center shrink-0 hover:bg-blue-600"><Icon name="mic" size={16} /></button>
        </div>
        {/* 빠른 명령 칩 */}
        <div className="mt-3 flex flex-wrap gap-2">
          {QUICK_CHIPS.map((c) => (
            <button key={c} onClick={() => setCmd(c)}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 text-gray-600">{c}</button>
          ))}
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cards.map((c) => (
          <Link key={c.label} href="/tasks" className="rounded-xl border border-gray-200 bg-white p-4 hover:shadow-md transition-shadow min-w-0">
            <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1"><Icon name={c.icon} size={14} /> {c.label}</div>
            <div className={`text-2xl sm:text-3xl font-bold ${c.color}`}>{c.value}</div>
          </Link>
        ))}
      </div>

      {/* AI 에이전트 팀 */}
      <div className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold flex items-center gap-1.5"><Icon name="cpu" size={16} /> AI 에이전트 팀</h2>
          <Link href="/agents" className="text-xs text-blue-500 hover:underline">전체 보기 →</Link>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
          {AGENT_CARDS.map((a) => {
            const present = roleSet.size === 0 || roleSet.has(a.role);
            return (
              <Link key={a.role} href="/agents" className="rounded-xl border border-gray-200 p-3 hover:shadow-md transition-shadow min-w-0">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center mb-2" style={{ background: a.color + "22", color: a.color }}><Icon name={a.icon} size={18} /></div>
                <div className="text-sm font-semibold truncate">{a.name}</div>
                <div className="text-[11px] text-gray-500 truncate">{a.desc}</div>
                <div className="flex items-center gap-1 mt-1.5 text-[10px] text-emerald-500"><span className={`w-1.5 h-1.5 rounded-full ${present ? "bg-emerald-500" : "bg-gray-400"}`} /> {present ? "온라인" : "미설정"}</div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* 최근 프로젝트 (실데이터 — 진행률 = task 완료율) */}
      {projects.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5">
          <h2 className="text-sm font-bold flex items-center gap-1.5 mb-3"><Icon name="folder" size={16} /> 최근 프로젝트</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {projects.map((p) => (
              <Link key={p.id} href={p.href} className="rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0"><Icon name={p.icon || "balloon"} size={18} /></span>
                  <div className="min-w-0"><div className="font-semibold truncate">{p.name}</div><div className="text-[11px] text-gray-500 truncate">{p.subtitle}</div></div>
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500 mb-1"><span>진행률 (작업 {p.done}/{p.total})</span><span className="font-bold text-blue-600">{p.progress}%</span></div>
                <div className="h-2 rounded-full bg-gray-100 overflow-hidden"><div className="h-full bg-blue-500" style={{ width: `${p.progress}%` }} /></div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 최근 에셋 */}
      {assets.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold flex items-center gap-1.5"><Icon name="image" size={16} /> 최근 에셋</h2>
            <Link href="/gallery" className="text-xs text-blue-500 hover:underline">갤러리 →</Link>
          </div>
          <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
            {assets.slice(0, 8).map((a, i) => (
              a.images?.[0]?.filename ? (
                // eslint-disable-next-line @next/next/no-img-element
                <Link key={i} href="/gallery" className="aspect-square rounded-lg overflow-hidden border border-gray-100 bg-gray-50 block">
                  <img src={`/api/designs/image/${a.images[0].filename}`} alt="" className="w-full h-full object-cover" />
                </Link>
              ) : null
            ))}
          </div>
        </div>
      )}

      {/* 본문 + 우측 레일 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 실시간 활동 */}
        <div className="lg:col-span-2 rounded-2xl border border-gray-200 bg-white p-4 sm:p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold flex items-center gap-1.5"><Icon name="signal" size={16} /> 실시간 활동</h2>
            <Link href="/agents" className="text-xs text-blue-500 hover:underline">모든 활동 →</Link>
          </div>
          {sessions.length === 0 ? (
            <div className="text-sm text-gray-400 py-6 text-center">최근 활동 없음</div>
          ) : (
            <ul className="space-y-2">
              {sessions.map((s, i) => (
                <li key={i} className="flex items-center gap-3 rounded-lg border border-gray-100 p-2.5">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${s.success === false ? "bg-rose-500" : "bg-emerald-500"}`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{s.role || "agent"} <span className="text-gray-400 font-normal">— {s.task_title || s.task_id || ""}</span></div>
                  </div>
                  <span className="text-[11px] text-gray-400 shrink-0">{timeAgo(s.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 우측: 빠른 작업 + 시스템 상태 */}
        <div className="space-y-4">
          <div className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5">
            <h2 className="text-sm font-bold flex items-center gap-1.5 mb-3"><Icon name="zap" size={16} /> 빠른 작업</h2>
            <div className="space-y-2">
              {[
                { href: "/tasks", label: "새 작업", desc: "작업 추가/관리", icon: "tasks" },
                { href: "/voice", label: "음성 명령", desc: "말로 업무 지시", icon: "mic" },
                { href: "/gallery", label: "디자인 갤러리", desc: "에셋 보기", icon: "image" },
                { href: "/balloonflow", label: "BalloonFlow", desc: "코드 그래프 · QA", icon: "balloon" },
              ].map((q) => (
                <Link key={q.href} href={q.href} className="flex items-center gap-3 rounded-lg border border-gray-100 p-2.5 hover:bg-gray-50">
                  <span className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0"><Icon name={q.icon} size={16} /></span>
                  <div className="min-w-0"><div className="text-sm font-medium">{q.label}</div><div className="text-[11px] text-gray-500 truncate">{q.desc}</div></div>
                </Link>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5">
            <h2 className="text-sm font-bold flex items-center gap-1.5 mb-3"><Icon name="signal" size={16} /> 시스템 상태</h2>
            <div className="flex items-center gap-2 text-sm">
              <span className={`w-2.5 h-2.5 rounded-full ${live ? "bg-emerald-500 animate-pulse" : "bg-gray-400"}`} />
              <span className="font-medium">{live ? "Hermes 가동 중" : "상태 불명"}</span>
            </div>
            <div className="grid grid-cols-3 gap-2 mt-3 text-center">
              <div className="rounded-lg border border-gray-100 p-2"><div className="text-lg font-bold text-blue-600">{running}</div><div className="text-[10px] text-gray-500">실행 중</div></div>
              <div className="rounded-lg border border-gray-100 p-2"><div className="text-lg font-bold text-amber-600">{stat.review}</div><div className="text-[10px] text-gray-500">리뷰</div></div>
              <div className="rounded-lg border border-gray-100 p-2"><div className="text-lg font-bold">{tasks.length}</div><div className="text-[10px] text-gray-500">전체</div></div>
            </div>
          </div>
        </div>
      </div>

      {/* 오늘의 할 일 */}
      <div className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold flex items-center gap-1.5"><Icon name="check" size={16} /> 진행할 작업</h2>
          <Link href="/tasks" className="text-xs text-blue-500 hover:underline">전체 보기 →</Link>
        </div>
        {todoList.length === 0 ? (
          <div className="text-sm text-gray-400 py-4 text-center">진행할 작업이 없습니다</div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {todoList.map((t) => (
              <li key={t._id} className="flex items-center gap-3 py-2.5">
                <span className={`w-2 h-2 rounded-full shrink-0 ${t.status === "in_progress" ? "bg-blue-500" : "bg-gray-300"}`} />
                <Link href="/tasks" className="text-sm flex-1 truncate hover:underline">{t.title}</Link>
                {t.team && TEAM_BADGE[t.team] && <span className={`text-[10px] px-1.5 py-0.5 rounded ${TEAM_BADGE[t.team].cls} shrink-0`}>{TEAM_BADGE[t.team].label}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
