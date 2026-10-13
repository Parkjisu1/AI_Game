"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Icon from "@/components/Icon";

/**
 * clean 인스턴스 전용 작업 화면 — Flex형 3-패널.
 * 좌: 프로젝트/상태 필터 · 중: 우선순위 그룹 목록 · 우: 상세.
 * 모바일: 목록 단일 패널 + 상세는 전체 오버레이.
 * API: GET/POST/PATCH /api/tasks, GET /api/projects (기존 계약 그대로).
 */

interface Comment { id?: string; text: string; author?: string; created_at?: string }
interface Task {
  _id: string;
  title?: string;
  description?: string;
  status?: string;
  priority?: string;
  /** "hermes" = AI 담당, 그 외 = 팀원 이메일 */
  assignee?: string;
  /** AI 담당일 때의 역할 ID (AI 팀 페이지의 역할과 연결) */
  ai_role?: string;
  /** 검수자 이메일 (선택) */
  reviewer?: string;
  project?: string;
  comments?: Comment[];
  created_at?: string;
  updated_at?: string;
  created_by_email?: string;
}
interface ProjItem { id: string; name: string; subtitle?: string; total?: number }

const PRIORITIES = [
  { key: "urgent", label: "긴급", color: "#f0883e", icon: "zap" },
  { key: "high", label: "높음", color: "#e3b341", icon: "arrowup" },
  { key: "medium", label: "중간", color: "#9b9ea4", icon: "menu" },
  { key: "low", label: "낮음", color: "#5f6267", icon: "dot" },
];
const STATUS: Record<string, { label: string; color: string }> = {
  todo: { label: "할 일", color: "#9b9ea4" },
  in_progress: { label: "진행 중", color: "#4b8bfa" },
  review: { label: "리뷰", color: "#e3b341" },
  done: { label: "완료", color: "#3fb950" },
};
const FILTERS = [
  { key: "", label: "전체" },
  { key: "todo", label: "할 일" },
  { key: "in_progress", label: "진행 중" },
  { key: "review", label: "리뷰" },
  { key: "done", label: "완료" },
];
const SORTS = [
  { key: "recent", label: "최신순" },
  { key: "oldest", label: "오래된순" },
  { key: "title", label: "제목순" },
];

const AI_ASSIGNEE = "hermes"; // AI 담당 태스크 표준값 (워커 연결 시 이 값으로 claim)
const who = (v?: string) => (!v ? "" : v === AI_ASSIGNEE ? "AI" : v.split("@")[0]);

/** 담당 select 값 인코딩: "" | "hermes" | "ai:<role>" | 이메일 → PATCH/POST 필드로 변환 */
const assigneeValue = (t: { assignee?: string; ai_role?: string }) =>
  t.assignee === AI_ASSIGNEE ? (t.ai_role ? `ai:${t.ai_role}` : AI_ASSIGNEE) : (t.assignee || "");
const decodeAssignee = (v: string): { assignee: string; ai_role: string } =>
  v.startsWith("ai:") ? { assignee: AI_ASSIGNEE, ai_role: v.slice(3) }
  : v === AI_ASSIGNEE ? { assignee: AI_ASSIGNEE, ai_role: "" }
  : { assignee: v, ai_role: "" };

function timeAgo(iso?: string) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}
function fmtDate(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const days = ["일", "월", "화", "수", "목", "금", "토"];
  const h = d.getHours();
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${days[d.getDay()]}) ${h < 12 ? "오전" : "오후"} ${h % 12 || 12}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function FlexTasks() {
  const sp = useSearchParams();
  const [projects, setProjects] = useState<ProjItem[]>([]);
  const [project, setProject] = useState<string>(sp.get("project") || "");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState("");
  const [selId, setSelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newPriority, setNewPriority] = useState("medium");
  const [newDesc, setNewDesc] = useState("");
  const [newAssignee, setNewAssignee] = useState("");
  const [newReviewer, setNewReviewer] = useState("");
  const [commentText, setCommentText] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("recent");
  const [members, setMembers] = useState<string[]>([]);
  const [aiRoles, setAiRoles] = useState<string[]>([]);

  useEffect(() => {
    // AI 역할 목록 (AI 팀 페이지에서 구성) — 담당을 역할 단위로 지정
    fetch("/api/agents/roles").then((r) => r.json())
      .then((d) => setAiRoles(((Array.isArray(d) ? d : d.roles || []) as { role: string }[]).map((x) => x.role)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    // 담당/검수자 후보 = 허용 사용자 목록 (전원 관리자라 조회 가능; 실패 시 빈 목록)
    fetch("/api/admin/allowed-users")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        const set = new Set<string>([...(d.envEmails || []), ...(d.emails || [])].map((e: string) => e.toLowerCase()));
        // 운영 계정(게임팀 소유자)은 담당/검수 후보에서 제외 — 팀 내부 인원만 노출
        setMembers([...set].filter((e) => !e.endsWith("@gameberry.co.kr")));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/projects")
      .then((r) => r.json())
      .then((d) => {
        const list: ProjItem[] = Array.isArray(d?.projects) ? d.projects : [];
        setProjects(list);
        setProject((p) => p || list[0]?.id || "");
      })
      .catch(() => {});
  }, []);

  const load = useCallback(() => {
    if (!project) return;
    fetch(`/api/tasks?project=${encodeURIComponent(project)}`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d) && setTasks(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project]);
  useEffect(() => { setLoading(true); load(); }, [load]);

  // 로그인 사용자 (검수 게이트용)
  const [me, setMe] = useState("");
  useEffect(() => {
    fetch("/api/auth/session").then((r) => r.json())
      .then((d) => setMe(String(d?.user?.email || "").toLowerCase())).catch(() => {});
  }, []);

  // 실시간 동기화 — 다른 팀원·AI의 변경(SSE) + 창 복귀 시 재조회.
  // 여러 명이 동시에 써도 각자 화면이 곧바로 갱신되어 낡은 화면 기준의 충돌을 방지한다.
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | null = null;
    const bump = () => { if (t) clearTimeout(t); t = setTimeout(load, 400); };
    const es = new EventSource("/api/tasks/stream");
    es.addEventListener("insert", bump);
    es.addEventListener("update", bump);
    es.addEventListener("delete", bump);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => { es.close(); window.removeEventListener("focus", onFocus); if (t) clearTimeout(t); };
  }, [load]);

  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return tasks.filter((t) => {
      if (filter && (t.status || "todo") !== filter) return false;
      if (!kw) return true;
      return `${t.title || ""} ${t.description || ""} ${t.assignee || ""}`.toLowerCase().includes(kw);
    });
  }, [tasks, filter, q]);
  const grouped = useMemo(() => {
    const cmp = (a: Task, b: Task) => {
      if (sort === "title") return (a.title || "").localeCompare(b.title || "", "ko");
      const ta = new Date(a.updated_at || a.created_at || 0).getTime();
      const tb = new Date(b.updated_at || b.created_at || 0).getTime();
      return sort === "oldest" ? ta - tb : tb - ta;
    };
    return PRIORITIES.map((p) => ({
      ...p,
      items: filtered.filter((t) => (t.priority || "medium") === p.key).sort(cmp),
    })).filter((g) => g.items.length > 0);
  }, [filtered, sort]);
  const sel = useMemo(() => tasks.find((t) => t._id === selId) || null, [tasks, selId]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { "": tasks.length };
    for (const t of tasks) { const s = t.status || "todo"; c[s] = (c[s] || 0) + 1; }
    return c;
  }, [tasks]);

  const patch = async (body: Record<string, unknown>) => {
    await fetch("/api/tasks", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => {});
    load();
  };

  const create = async () => {
    if (!newTitle.trim()) return;
    await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: newTitle.trim(),
        description: newDesc.trim() || undefined,
        priority: newPriority,
        status: "todo",
        ...(newAssignee ? decodeAssignee(newAssignee) : {}),
        reviewer: newReviewer || undefined,
        project,
        created_via: "flex_board",
      }),
    }).catch(() => {});
    setNewTitle(""); setNewDesc(""); setNewPriority("medium"); setNewAssignee(""); setNewReviewer(""); setCreating(false);
    load();
  };

  const addComment = async () => {
    if (!sel || !commentText.trim()) return;
    await patch({ _id: sel._id, add_comment: { text: commentText.trim() } });
    setCommentText("");
  };

  // 상태 전환 버튼 (Flex 우하단 액션). 검수자가 지정된 작업의 "완료"는 검수자 본인만 누를 수 있다.
  const actionsFor = (t: Task) => {
    const s = t.status || "todo";
    const gated = !!(t.reviewer && me && t.reviewer.toLowerCase() !== me);
    const btn = (label: string, to: string, primary = false, disabled = false, title?: string) => (
      <button
        key={to}
        onClick={() => patch({ _id: t._id, status: to })}
        disabled={disabled}
        title={title}
        className={`px-3.5 py-2 rounded-lg text-[13px] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
          primary ? "text-white" : "text-gray-700 border border-gray-300 hover:bg-gray-100"
        }`}
        style={primary ? { background: to === "done" ? "#2ea043" : "#2f6fed" } : undefined}
      >
        {label}
      </button>
    );
    const doneBtn = (label: string) =>
      btn(label, "done", true, gated, gated ? `검수자(${who(t.reviewer)})만 완료 처리할 수 있습니다` : undefined);
    if (s === "todo") return [btn("작업 시작", "in_progress", true)];
    if (s === "in_progress") return t.reviewer
      ? [btn("검수 요청", "review", true)]
      : [btn("리뷰 요청", "review"), doneBtn("작업 완료")];
    if (s === "review") return [btn("작업 재개", "in_progress"), doneBtn(t.reviewer ? "검수 승인 · 완료" : "작업 완료")];
    return [btn("다시 열기", "todo")];
  };

  const removeTask = async (t: Task) => {
    if (!confirm(`"${t.title || "제목 없음"}" 작업을 삭제할까요?`)) return;
    await fetch(`/api/tasks/${t._id}`, { method: "DELETE" }).catch(() => {});
    setSelId(null);
    load();
  };

  const prioMeta = (k?: string) => PRIORITIES.find((p) => p.key === (k || "medium")) || PRIORITIES[2];

  const detailPane = sel && (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto thin-scroll px-6 py-5">
        {/* 모바일 뒤로가기 */}
        <button onClick={() => setSelId(null)} className="md:hidden mb-3 text-[13px] text-gray-500 flex items-center gap-1">
          ← 목록
        </button>
        <h2 className="text-xl font-bold text-gray-900 leading-snug">{sel.title || "제목 없음"}</h2>
        <div className="mt-1.5 text-[12px] text-gray-500">{fmtDate(sel.created_at || sel.updated_at)}</div>

        <div className="mt-5">
          <div className="text-[12px] text-gray-500 mb-1.5">우선 순위</div>
          <div className="flex gap-1.5">
            {PRIORITIES.map((p) => {
              const on = (sel.priority || "medium") === p.key;
              return (
                <button
                  key={p.key}
                  onClick={() => patch({ _id: sel._id, priority: p.key })}
                  className={`px-2.5 py-1 rounded-md text-[12px] font-medium border transition-colors ${
                    on ? "border-transparent" : "border-gray-200 text-gray-500 hover:bg-gray-50"
                  }`}
                  style={on ? { background: `${p.color}26`, color: p.color } : undefined}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <div className="text-[12px] text-gray-500 mb-1.5">상태</div>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium"
              style={{ background: `${STATUS[sel.status || "todo"]?.color}26`, color: STATUS[sel.status || "todo"]?.color }}>
              {STATUS[sel.status || "todo"]?.label || sel.status}
            </span>
          </div>
          <div>
            <div className="text-[12px] text-gray-500 mb-1.5">담당</div>
            <select value={assigneeValue(sel)} onChange={(e) => patch({ _id: sel._id, ...decodeAssignee(e.target.value) })}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-[12px]">
              <option value="">없음</option>
              {(aiRoles.length === 0 || (sel.assignee === AI_ASSIGNEE && !sel.ai_role)) && <option value={AI_ASSIGNEE}>AI</option>}
              {aiRoles.map((r) => <option key={r} value={`ai:${r}`}>AI · {r}</option>)}
              {sel.assignee === AI_ASSIGNEE && sel.ai_role && !aiRoles.includes(sel.ai_role) && (
                <option value={`ai:${sel.ai_role}`}>AI · {sel.ai_role}</option>
              )}
              {members.map((m) => <option key={m} value={m}>{who(m)}</option>)}
              {sel.assignee && sel.assignee !== AI_ASSIGNEE && !members.includes(sel.assignee) && (
                <option value={sel.assignee}>{who(sel.assignee)}</option>
              )}
            </select>
          </div>
          <div>
            <div className="text-[12px] text-gray-500 mb-1.5">검수자</div>
            <select value={sel.reviewer || ""} onChange={(e) => patch({ _id: sel._id, reviewer: e.target.value })}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-[12px]">
              <option value="">없음</option>
              {members.map((m) => <option key={m} value={m}>{who(m)}</option>)}
              {sel.reviewer && !members.includes(sel.reviewer) && <option value={sel.reviewer}>{who(sel.reviewer)}</option>}
            </select>
          </div>
        </div>

        {sel.description && (
          <div className="mt-6">
            <div className="text-[12px] text-gray-500 mb-1.5">내용</div>
            <div className="text-[14px] text-gray-800 leading-relaxed whitespace-pre-wrap">{sel.description}</div>
          </div>
        )}

        <div className="mt-6">
          <div className="text-[12px] text-gray-500 mb-2">코멘트</div>
          <div className="space-y-2">
            {(sel.comments || []).map((c, i) => (
              <div key={c.id || i} className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5">
                <div className="text-[13px] text-gray-800 whitespace-pre-wrap">{c.text}</div>
                <div className="mt-1 text-[11px] text-gray-400">{c.author || "익명"} · {timeAgo(c.created_at)}</div>
              </div>
            ))}
            {(sel.comments || []).length === 0 && (
              <div className="text-[13px] text-gray-400 py-2">코멘트가 없습니다</div>
            )}
          </div>
          <div className="mt-2.5 flex gap-2">
            <input
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addComment(); }}
              placeholder="코멘트 입력…"
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-[13px]"
            />
            <button onClick={addComment} className="px-3 py-2 rounded-lg text-[13px] font-medium text-gray-700 border border-gray-300 hover:bg-gray-100">
              등록
            </button>
          </div>
        </div>
      </div>
      {/* 하단 액션 바 (Flex 우하단) — 좌측 삭제, 우측 상태 전환 */}
      <div className="border-t border-gray-200 px-6 py-3 flex items-center gap-2 bg-white">
        <button onClick={() => removeTask(sel)} className="px-3 py-2 rounded-lg text-[13px] text-gray-400 hover:text-red-500 hover:bg-gray-100">
          삭제
        </button>
        {sel.reviewer && sel.status === "review" && (
          <span className="text-[12px] text-gray-500">검수 대기 — {who(sel.reviewer)}</span>
        )}
        <div className="ml-auto flex gap-2">{actionsFor(sel)}</div>
      </div>
    </div>
  );

  return (
    <div className="flex h-[calc(100vh-56px)] md:h-screen md:-my-6 -mx-4 sm:-mx-6 md:-mx-8">
      {/* ── 좌: 필터 패널 ── */}
      <div className="hidden md:flex w-52 shrink-0 flex-col border-r border-gray-200 py-4 px-2">
        <div className="px-2.5 mb-1 text-[15px] font-bold text-gray-900">작업</div>
        <button
          onClick={() => { setCreating(true); setSelId(null); }}
          className="mx-1 mt-2 mb-3 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] text-gray-600 hover:bg-gray-100"
        >
          <Icon name="plus" size={15} /> 새 작업
        </button>
        <div className="px-2.5 mb-1 text-[11px] font-semibold text-gray-400">프로젝트</div>
        <div className="space-y-0.5 mb-4">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => { setProject(p.id); setSelId(null); }}
              className={`w-full text-left flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] ${
                project === p.id ? "bg-gray-100 font-semibold text-gray-900" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <Icon name="box" size={14} /> {p.name}
            </button>
          ))}
        </div>
        <div className="px-2.5 mb-1 text-[11px] font-semibold text-gray-400">상태</div>
        <div className="space-y-0.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`w-full text-left flex items-center justify-between rounded-md px-2.5 py-1.5 text-[13px] ${
                filter === f.key ? "bg-gray-100 font-semibold text-gray-900" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <span>{f.label}</span>
              <span className="text-[11px] text-gray-400">{counts[f.key] || 0}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ── 중: 작업 목록 ── */}
      <div className={`${sel ? "hidden md:flex" : "flex"} w-full md:w-[400px] shrink-0 flex-col border-r border-gray-200`}>
        <div className="flex items-center justify-between px-4 h-12 border-b border-gray-200 shrink-0">
          <span className="text-[14px] font-bold text-gray-900">
            {projects.find((p) => p.id === project)?.name || "작업"} <span className="text-gray-400 font-normal">{filtered.length}</span>
          </span>
          <div className="flex items-center gap-1">
            {/* 모바일 프로젝트 전환 */}
            <select value={project} onChange={(e) => setProject(e.target.value)} className="md:hidden text-[12px] rounded-md border border-gray-300 px-1.5 py-1">
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button onClick={() => setCreating(true)} className="md:hidden p-1.5 text-gray-500"><Icon name="plus" size={16} /></button>
            <button onClick={load} className="p-1.5 text-gray-400 hover:text-gray-600" title="새로고침"><Icon name="undo" size={14} /></button>
          </div>
        </div>
        {/* 검색 + 정렬 */}
        <div className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-200 shrink-0">
          <div className="flex-1 flex items-center gap-1.5 rounded-md border border-gray-300 px-2 py-1.5">
            <Icon name="search" size={13} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="검색…"
              className="flex-1 min-w-0 bg-transparent text-[13px] outline-none border-0" style={{ background: "transparent" }} />
            {q && <button onClick={() => setQ("")} className="text-gray-400"><Icon name="x" size={12} /></button>}
          </div>
          <select value={sort} onChange={(e) => setSort(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-1.5 py-1.5 shrink-0">
            {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </div>
        {/* 모바일 상태 필터 */}
        <div className="md:hidden flex gap-1 px-3 py-2 border-b border-gray-200 overflow-x-auto no-scrollbar shrink-0">
          {FILTERS.map((f) => (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className={`px-2.5 py-1 rounded-full text-[12px] whitespace-nowrap ${filter === f.key ? "bg-gray-200 font-semibold text-gray-900" : "text-gray-500"}`}>
              {f.label} {counts[f.key] || 0}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto thin-scroll">
          {creating && (
            <div className="m-3 bg-white border border-gray-200 rounded-lg p-3 space-y-2">
              <input autoFocus value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
                placeholder="작업 제목" className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-[13px]" />
              <textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
                placeholder="내용 (선택)" rows={3} className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-[13px] resize-none" />
              <div className="flex flex-wrap items-center gap-1.5">
                <select value={newPriority} onChange={(e) => setNewPriority(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-2 py-1">
                  {PRIORITIES.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                </select>
                <select value={newAssignee} onChange={(e) => setNewAssignee(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-2 py-1">
                  <option value="">담당 없음</option>
                  {aiRoles.length === 0 && <option value={AI_ASSIGNEE}>AI</option>}
                  {aiRoles.map((r) => <option key={r} value={`ai:${r}`}>AI · {r}</option>)}
                  {members.map((m) => <option key={m} value={m}>{who(m)}</option>)}
                </select>
                <select value={newReviewer} onChange={(e) => setNewReviewer(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-2 py-1">
                  <option value="">검수 없음</option>
                  {members.map((m) => <option key={m} value={m}>검수: {who(m)}</option>)}
                </select>
                <div className="ml-auto flex gap-1.5">
                  <button onClick={() => setCreating(false)} className="px-2.5 py-1.5 rounded-md text-[12px] text-gray-500 hover:bg-gray-100">취소</button>
                  <button onClick={create} className="px-3 py-1.5 rounded-md text-[12px] font-semibold text-white" style={{ background: "#2f6fed" }}>등록</button>
                </div>
              </div>
            </div>
          )}

          {loading ? (
            <div className="py-16 text-center text-[13px] text-gray-400">불러오는 중…</div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center">
              <div className="text-[13px] text-gray-400 mb-3">작업이 없습니다</div>
              <button onClick={() => setCreating(true)} className="text-[13px] font-medium" style={{ color: "#4b8bfa" }}>+ 첫 작업 만들기</button>
            </div>
          ) : (
            grouped.map((g) => (
              <div key={g.key}>
                <div className="sticky top-0 z-10 mx-3 mt-3 mb-1.5 px-3 py-1.5 rounded-lg flex items-center gap-2 text-[12px] font-bold"
                  style={{ background: "#232428", color: g.color, border: "1px solid #2a2c31" }}>
                  <Icon name={g.icon} size={13} /> {g.label} <span className="font-normal opacity-70">{g.items.length}</span>
                </div>
                {g.items.map((t) => (
                  <button key={t._id} onClick={() => { setSelId(t._id); setCreating(false); }}
                    className={`w-full text-left mx-3 mb-1.5 block rounded-lg border px-3 py-2.5 transition-colors ${
                      selId === t._id ? "border-gray-300 bg-gray-100" : "border-gray-200 bg-white hover:bg-gray-50"
                    }`}
                    style={{ width: "calc(100% - 24px)" }}>
                    <div className="flex items-start gap-1.5">
                      <span className="mt-0.5 shrink-0" style={{ color: g.color }}><Icon name={g.icon} size={13} /></span>
                      <span className="flex-1 min-w-0 text-[13px] font-medium text-gray-900 leading-snug line-clamp-2">{t.title || "제목 없음"}</span>
                    </div>
                    {t.description && <div className="mt-1 text-[12px] text-gray-500 line-clamp-1 pl-5">{t.description}</div>}
                    <div className="mt-1.5 pl-5 flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 min-w-0">
                        <span className="text-[11px] font-medium shrink-0" style={{ color: STATUS[t.status || "todo"]?.color }}>
                          {STATUS[t.status || "todo"]?.label}
                        </span>
                        {t.assignee && (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded truncate ${t.assignee === AI_ASSIGNEE ? "" : "bg-gray-100 text-gray-500"}`}
                            style={t.assignee === AI_ASSIGNEE ? { background: "rgba(75,139,250,0.15)", color: "#6ca0f8" } : undefined}>
                            {t.assignee === AI_ASSIGNEE ? (t.ai_role ? `AI · ${t.ai_role}` : "AI") : who(t.assignee)}
                          </span>
                        )}
                      </span>
                      <span className="text-[11px] text-gray-400 shrink-0">{timeAgo(t.updated_at || t.created_at)}</span>
                    </div>
                  </button>
                ))}
              </div>
            ))
          )}
          <div className="h-6" />
        </div>
      </div>

      {/* ── 우: 상세 (데스크톱) ── */}
      <div className="hidden md:flex flex-1 min-w-0 flex-col">
        {sel ? detailPane : (
          <div className="flex-1 flex items-center justify-center text-[13px] text-gray-400">작업을 선택하세요</div>
        )}
      </div>

      {/* ── 모바일 상세: 전체 화면 ── */}
      {sel && (
        <div className="md:hidden fixed inset-0 z-40 flex flex-col" style={{ background: "#131417" }}>
          {detailPane}
        </div>
      )}
    </div>
  );
}
