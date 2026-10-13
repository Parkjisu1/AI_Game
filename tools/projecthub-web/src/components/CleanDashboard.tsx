"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";

/**
 * clean 인스턴스 전용 대시보드 — Flex형 사무 레이아웃.
 * 헤더 → 지표 4칸 → (좌 2/3) 진행 작업·최근 활동 / (우 1/3) 작업 요청·AI 팀.
 * JARVIS 연출(오비탈/웨이브폼/원형 게이지/플로팅 마이크) 없음.
 */

interface Task { _id?: string; title?: string; status?: string; priority?: string; assignee?: string; progress?: number; updated_at?: string }
interface Role { role: string; team?: string }
interface Sess { task_title?: string; task_id?: string; role?: string; success?: boolean; created_at?: string }

const STATUS: Record<string, { label: string; color: string }> = {
  todo: { label: "할 일", color: "#9b9ea4" },
  in_progress: { label: "진행 중", color: "#4b8bfa" },
  review: { label: "리뷰", color: "#e3b341" },
  done: { label: "완료", color: "#3fb950" },
};

function timeAgo(iso?: string) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}

export default function CleanDashboard() {
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
    fetch("/api/agents/node-runs").then((r) => r.json()).then((d) => setRunning((d.running || []).length)).catch(() => {});
    fetch("/api/assistant/status").then((r) => r.json()).then((d) => setLive(Array.isArray(d?.workers) && d.workers.length > 0)).catch(() => setLive(false));
  }, []);

  const stat = {
    total: tasks.length,
    inProgress: tasks.filter((t) => t.status === "in_progress").length,
    done: tasks.filter((t) => t.status === "done").length,
    urgent: tasks.filter((t) => t.priority === "urgent").length,
  };
  const activeTasks = tasks.filter((t) => t.status === "in_progress" || t.status === "review").slice(0, 6);

  const submitCmd = async () => {
    if (!cmd.trim() || sending) return;
    setSending(true);
    try {
      await fetch("/api/tasks", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: cmd.trim(), status: "todo", priority: "medium", created_via: "dashboard" }),
      });
      router.push("/tasks");
    } catch { setSending(false); }
  };

  const cards = [
    { label: "전체 작업", value: stat.total, color: "var(--text)" },
    { label: "진행 중", value: stat.inProgress, color: "#4b8bfa" },
    { label: "완료", value: stat.done, color: "#3fb950" },
    { label: "긴급", value: stat.urgent, color: "#f0883e" },
  ];

  return (
    <div className="space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-900">대시보드</h1>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] bg-gray-100 text-gray-600">
          <span className={live ? "dot dot-run" : "dot dot-err"} />
          {live ? `AI 워커 온라인 · ${running}개 실행 중` : "AI 워커 오프라인"}
        </span>
      </div>

      {/* 지표 4칸 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {cards.map((c) => (
          <Link key={c.label} href="/tasks" className="glass p-4 block hover:bg-gray-50">
            <div className="text-[12px] text-gray-500">{c.label}</div>
            <div className="mt-1 text-[26px] font-bold leading-none" style={{ color: c.color }}>{c.value}</div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 좌 2/3 */}
        <div className="lg:col-span-2 space-y-4">
          {/* 진행 중인 작업 */}
          <div className="glass p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[13px] font-bold text-gray-900">진행 중인 작업</span>
              <Link href="/tasks" className="text-[12px] text-gray-500 hover:text-gray-700">전체 보기 →</Link>
            </div>
            {activeTasks.length === 0 ? (
              <div className="py-10 text-center">
                <div className="text-[13px] text-gray-400 mb-2">진행 중인 작업이 없습니다</div>
                <Link href="/tasks" className="text-[13px] font-medium" style={{ color: "#4b8bfa" }}>작업 보드에서 시작하기</Link>
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {activeTasks.map((t) => {
                  const sm = STATUS[t.status || "todo"] || STATUS.todo;
                  return (
                    <Link key={t._id} href="/tasks" className="flex items-center gap-3 py-2.5 hover:bg-gray-50 -mx-2 px-2 rounded-md">
                      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: sm.color }} />
                      <span className="flex-1 min-w-0 text-[13px] font-medium text-gray-900 truncate">{t.title || "제목 없음"}</span>
                      <span className="text-[11px] font-medium shrink-0" style={{ color: sm.color }}>{sm.label}</span>
                      <span className="text-[11px] text-gray-400 shrink-0 w-14 text-right">{timeAgo(t.updated_at)}</span>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          {/* 최근 활동 */}
          <div className="glass p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[13px] font-bold text-gray-900">최근 활동</span>
              <Link href="/agents" className="text-[12px] text-gray-500 hover:text-gray-700">전체 →</Link>
            </div>
            {sessions.length === 0 ? (
              <div className="text-[13px] text-gray-400 py-6 text-center">아직 활동 기록이 없습니다</div>
            ) : (
              <ul className="divide-y divide-gray-100">
                {sessions.map((s, i) => (
                  <li key={i} className="flex items-center gap-3 py-2">
                    <span className={`dot ${s.success === false ? "dot-err" : "dot-ok"}`} />
                    <span className="flex-1 min-w-0 truncate text-[13px]">
                      <span className="font-medium text-gray-900">{s.role || "agent"}</span>
                      <span className="text-gray-500"> — {s.task_title || s.task_id || ""}</span>
                    </span>
                    <span className="text-[11px] text-gray-400 shrink-0">{timeAgo(s.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* 우 1/3 */}
        <div className="space-y-4">
          {/* 작업 요청 */}
          <div className="glass p-4">
            <div className="text-[13px] font-bold text-gray-900 mb-2.5">작업 요청</div>
            <div className="flex gap-2">
              <input
                value={cmd} onChange={(e) => setCmd(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") submitCmd(); }}
                placeholder="할 일을 입력하세요…"
                className="flex-1 min-w-0 rounded-lg border border-gray-300 px-3 py-2 text-[13px]"
              />
              <button onClick={submitCmd} disabled={sending}
                className="shrink-0 px-3.5 py-2 rounded-lg text-[13px] font-semibold text-white disabled:opacity-50"
                style={{ background: "#2f6fed" }}>
                등록
              </button>
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {["진행 상황 보고", "코드 리뷰", "회의 요약", "배포 점검"].map((c) => (
                <button key={c} onClick={() => setCmd(c)}
                  className="text-[12px] px-2.5 py-1 rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50">{c}</button>
              ))}
            </div>
          </div>

          {/* AI 팀 */}
          <div className="glass p-4">
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[13px] font-bold text-gray-900">AI 팀</span>
              <Link href="/agents" className="text-[12px] text-gray-500 hover:text-gray-700">관리 →</Link>
            </div>
            {roles.length === 0 ? (
              <div className="text-[13px] text-gray-400 py-4 text-center">AI 역할이 아직 구성되지 않았습니다</div>
            ) : (
              <div className="flex items-center gap-3 text-[13px]">
                <span className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center text-gray-600"><Icon name="cpu" size={16} /></span>
                <span className="text-gray-600">등록된 역할</span>
                <span className="ml-auto font-bold text-gray-900">{roles.length}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
