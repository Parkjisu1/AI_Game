"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Icon from "@/components/Icon";

/**
 * clean 인스턴스 전용 AI 팀 화면 — 직군(카테고리) → 역할 계층 브라우저 (잡포털 직종별 구조).
 * 좌: 직군 목록(+건수) · 중: 역할 카드 · 우: 상세(설명·직군·페르소나 편집 + 담당 작업 연결).
 * 작업 보드에서 AI 담당을 역할 단위로 지정(ai_role)하며, 여기서 역할별 담당 작업이 보인다.
 */

interface Role { role: string; description?: string; persona?: string; category?: string; model?: string; tool?: string }
interface Task { _id: string; title?: string; status?: string; assignee?: string; ai_role?: string }

const CATEGORY_PRESETS = ["개발", "결제·정산", "데이터", "기획", "디자인", "운영·CS", "QA", "법무·컴플라이언스", "마케팅"];
const STATUS_LABEL: Record<string, string> = { todo: "할 일", in_progress: "진행 중", review: "리뷰", done: "완료" };
const UNCAT = "미분류";
const WIRE_COLORS = ["#4b8bfa", "#3fb950", "#f0883e", "#bc8cff", "#4dd0e1", "#e3b341"];

interface Rule {
  id: string; name?: string; enabled: boolean;
  match: { project?: string; keyword?: string };
  assign: { assignee?: string; ai_role?: string; reviewer?: string };
}
const whoShort = (v?: string) => (!v ? "" : v === "hermes" ? "AI" : v.split("@")[0]);

export default function CleanAgents() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [running, setRunning] = useState(0);
  const [live, setLive] = useState(false);
  const [cat, setCat] = useState<string>("");           // "" = 전체
  const [selRole, setSelRole] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "new">("view");
  // 편집 폼 상태
  const [fId, setFId] = useState("");
  const [fCat, setFCat] = useState("");
  const [fDesc, setFDesc] = useState("");
  const [fPersona, setFPersona] = useState("");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    fetch("/api/agents/roles").then((r) => r.json()).then((d) => setRoles(Array.isArray(d) ? d : d.roles || [])).catch(() => {});
    fetch("/api/tasks").then((r) => r.json()).then((d) => Array.isArray(d) && setTasks(d)).catch(() => {});
    fetch("/api/agents/node-runs").then((r) => r.json()).then((d) => setRunning((d.running || []).length)).catch(() => {});
    fetch("/api/assistant/status").then((r) => r.json()).then((d) => setLive(Array.isArray(d?.workers) && d.workers.length > 0)).catch(() => setLive(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  // ── 배선(라우팅) 규칙 ──
  const [rules, setRules] = useState<Rule[]>([]);
  const [wireOpen, setWireOpen] = useState(false);
  const [members, setMembers] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [wProject, setWProject] = useState("");
  const [wKeyword, setWKeyword] = useState("");
  const [wAssign, setWAssign] = useState("");
  const [wReviewer, setWReviewer] = useState("");

  useEffect(() => {
    fetch("/api/routing").then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d?.rules) { setRules(d.rules); if (d.rules.length > 0) setWireOpen(true); }
    }).catch(() => {});
    fetch("/api/admin/allowed-users").then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d) return;
      const set = new Set<string>([...(d.envEmails || []), ...(d.emails || [])].map((e: string) => e.toLowerCase()));
      setMembers([...set].filter((e) => !e.endsWith("@gameberry.co.kr")));
    }).catch(() => {});
    fetch("/api/projects").then((r) => r.json()).then((d) => {
      setProjects(((d?.projects || []) as { id: string }[]).map((p) => p.id));
    }).catch(() => {});
  }, []);

  const saveRules = async (next: Rule[]) => {
    setRules(next);
    await fetch("/api/routing", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rules: next }),
    }).catch(() => {});
  };
  const addRule = () => {
    if (!wAssign) return;
    const a = wAssign.startsWith("ai:")
      ? { assignee: "hermes", ai_role: wAssign.slice(3) }
      : { assignee: wAssign };
    const rule: Rule = {
      id: Math.random().toString(36).slice(2, 10),
      enabled: true,
      match: { project: wProject, keyword: wKeyword.trim() },
      assign: { ...a, reviewer: wReviewer },
    };
    saveRules([...rules, rule]);
    setWProject(""); setWKeyword(""); setWAssign(""); setWReviewer("");
  };
  const moveRule = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= rules.length) return;
    const next = [...rules];
    [next[i], next[j]] = [next[j], next[i]];
    saveRules(next);
  };

  const catOf = (r: Role) => (r.category || "").trim() || UNCAT;
  const categories = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of roles) m.set(catOf(r), (m.get(catOf(r)) || 0) + 1);
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0], "ko"));
  }, [roles]);
  const shown = useMemo(() => roles.filter((r) => !cat || catOf(r) === cat), [roles, cat]);
  const sel = useMemo(() => roles.find((r) => r.role === selRole) || null, [roles, selRole]);

  const aiTasksOf = useCallback((role: string) =>
    tasks.filter((t) => t.assignee === "hermes" && t.ai_role === role), [tasks]);

  // 선택 → 폼 채우기
  useEffect(() => {
    if (mode === "new") { setFId(""); setFCat(cat && cat !== UNCAT ? cat : ""); setFDesc(""); setFPersona(""); setErr(""); return; }
    if (sel) { setFId(sel.role); setFCat(sel.category || ""); setFDesc(sel.description || ""); setFPersona(sel.persona || ""); setErr(""); }
  }, [sel, mode, cat]);

  const save = async () => {
    setErr(""); setSaving(true);
    try {
      const id = (mode === "new" ? fId : sel?.role || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
      if (!/^[a-z][a-z0-9_]*$/.test(id)) { setErr("역할 ID는 영문 소문자로 시작, 소문자·숫자·언더스코어만 (예: backend_dev)"); return; }
      const res = await fetch("/api/agents/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: id, category: fCat.trim(), description: fDesc.trim(), persona: fPersona,
          tool: sel?.tool || "openai", model: sel?.model || "gpt-4o", team: "dev",
        }),
      }).catch(() => null);
      if (!res?.ok) {
        const j = await res?.json().catch(() => ({}));
        setErr((j as { error?: string })?.error || "저장 실패");
        return;
      }
      setMode("view"); setSelRole(id);
      load();
    } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!sel) return;
    const n = aiTasksOf(sel.role).length;
    if (!confirm(`역할 "${sel.role}"을(를) 삭제할까요?${n > 0 ? `\n(이 역할이 담당 중인 작업 ${n}건은 남습니다)` : ""}`)) return;
    await fetch(`/api/agents/roles?role=${encodeURIComponent(sel.role)}`, { method: "DELETE" }).catch(() => {});
    setSelRole(null);
    load();
  };

  const detailOpen = mode === "new" || !!sel;

  // 업무 흐름 단계별 실측 카운트
  const flow = useMemo(() => {
    const ai = tasks.filter((t) => t.assignee === "hermes");
    return {
      total: tasks.length,
      aiWait: ai.filter((t) => (t.status || "todo") === "todo").length,
      aiRun: ai.filter((t) => t.status === "in_progress").length,
      review: tasks.filter((t) => t.status === "review").length,
      done: tasks.filter((t) => t.status === "done").length,
    };
  }, [tasks]);

  const FlowStep = ({ no, title, sub, count, active }: { no: string; title: string; sub: string; count?: string; active?: boolean }) => (
    <div className={`flex-1 min-w-[150px] rounded-lg border px-3 py-2.5 ${active ? "border-gray-300 bg-gray-50" : "border-gray-200 bg-white"}`}>
      <div className="flex items-center gap-1.5 text-[12px] font-bold text-gray-900">
        <span className="w-[18px] h-[18px] rounded-full bg-gray-100 text-gray-500 text-[10px] flex items-center justify-center shrink-0">{no}</span>
        {title}
        {count !== undefined && <span className="ml-auto text-[11px] font-semibold" style={{ color: "#6ca0f8" }}>{count}</span>}
      </div>
      <div className="mt-1 text-[11px] text-gray-500 leading-snug">{sub}</div>
    </div>
  );

  const detailPane = (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto thin-scroll px-5 py-4">
        <button onClick={() => { setSelRole(null); setMode("view"); }} className="lg:hidden mb-3 text-[13px] text-gray-500">← 목록</button>
        {mode === "new" ? (
          <h2 className="text-base font-bold text-gray-900 mb-4">새 역할</h2>
        ) : (
          <div className="flex items-center gap-2.5 mb-4">
            <span className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center text-gray-600"><Icon name="cpu" size={18} /></span>
            <div>
              <h2 className="text-base font-bold text-gray-900 leading-none">{sel?.role}</h2>
              <div className="text-[12px] text-gray-500 mt-1">{catOf(sel || {} as Role)}</div>
            </div>
          </div>
        )}

        <div className="space-y-3.5">
          {mode === "new" && (
            <div>
              <div className="text-[12px] text-gray-500 mb-1">역할 ID</div>
              <input value={fId} onChange={(e) => setFId(e.target.value)} placeholder="backend_dev"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-[13px] font-mono" />
            </div>
          )}
          <div>
            <div className="text-[12px] text-gray-500 mb-1">직군</div>
            <input value={fCat} onChange={(e) => setFCat(e.target.value)} list="cat-presets" placeholder="예: 개발"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-[13px]" />
            <datalist id="cat-presets">
              {CATEGORY_PRESETS.map((c) => <option key={c} value={c} />)}
            </datalist>
          </div>
          <div>
            <div className="text-[12px] text-gray-500 mb-1">설명</div>
            <input value={fDesc} onChange={(e) => setFDesc(e.target.value)} placeholder="예: Express API 개발·버그 수정"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-[13px]" />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[12px] text-gray-500">페르소나 (직무 기술서)</span>
              <span className="text-[11px] text-gray-400">{fPersona.length}/4000</span>
            </div>
            <textarea value={fPersona} onChange={(e) => setFPersona(e.target.value.slice(0, 4000))} rows={8}
              placeholder={"이 역할이 일하는 방식·규칙·맥락을 적어주세요.\n예)\n- NewPlay 웹스토어 백엔드 담당. TypeScript/Express/TypeORM.\n- 결제 로직 변경 시 반드시 테스트 코드 포함.\n- 응답은 PR 단위로, 변경 요약을 한국어로 작성."}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-[13px] leading-relaxed resize-y" />
            <div className="text-[11px] text-gray-400 mt-1">AI 워커가 이 역할로 일할 때 시스템 프롬프트에 주입됩니다</div>
          </div>
        </div>

        {mode === "view" && sel && (
          <div className="mt-6">
            <div className="text-[12px] text-gray-500 mb-2">담당 중인 작업 <span className="text-gray-400">{aiTasksOf(sel.role).length}</span></div>
            {aiTasksOf(sel.role).length === 0 ? (
              <div className="text-[13px] text-gray-400 py-3">
                아직 없음 — 작업 보드에서 담당을 <span className="font-medium text-gray-600">AI · {sel.role}</span>로 지정하면 여기 연결됩니다
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {aiTasksOf(sel.role).map((t) => (
                  <Link key={t._id} href="/tasks" className="flex items-center gap-2.5 py-2 hover:bg-gray-50 -mx-1.5 px-1.5 rounded-md">
                    <span className="flex-1 min-w-0 text-[13px] text-gray-900 truncate">{t.title || "제목 없음"}</span>
                    <span className="text-[11px] text-gray-400 shrink-0">{STATUS_LABEL[t.status || "todo"]}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <div className="border-t border-gray-200 px-5 py-3 flex items-center gap-2">
        {mode === "view" && sel && (
          <button onClick={remove} className="px-3 py-2 rounded-lg text-[13px] text-gray-400 hover:text-red-500 hover:bg-gray-100">삭제</button>
        )}
        {err && <span className="text-[12px] text-red-500 truncate">{err}</span>}
        <div className="ml-auto flex gap-2">
          {mode === "new" && (
            <button onClick={() => setMode("view")} className="px-3 py-2 rounded-lg text-[13px] text-gray-500 hover:bg-gray-100">취소</button>
          )}
          <button onClick={save} disabled={saving}
            className="px-4 py-2 rounded-lg text-[13px] font-semibold text-white disabled:opacity-50" style={{ background: "#2f6fed" }}>
            {mode === "new" ? "역할 만들기" : "저장"}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-3">
      {/* ── 업무 흐름 — 작업이 어떤 프로세스로 진행되는지 ── */}
      <div className="glass p-3.5">
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-[13px] font-bold text-gray-900">업무 흐름</span>
          <span className="text-[11px] text-gray-400">담당으로 지정한 역할의 AI가 그 작업을 받습니다</span>
        </div>
        <div className="flex items-stretch gap-1.5 overflow-x-auto no-scrollbar">
          <FlowStep no="1" title="작업 등록" sub="작업 보드·음성·대시보드에서 누구나 등록" count={`${flow.total}`} />
          <span className="self-center text-gray-300 shrink-0">→</span>
          <FlowStep no="2" title="담당 배정" sub="AI 역할(이 화면에서 구성) 또는 팀원 지정" />
          <span className="self-center text-gray-300 shrink-0">→</span>
          <FlowStep no="3" title="AI 처리" sub={live ? "역할의 페르소나대로 자동 수행" : "워커 미연결 — 지정된 작업은 대기"} count={`대기 ${flow.aiWait} · 실행 ${flow.aiRun}`} active={flow.aiWait + flow.aiRun > 0} />
          <span className="self-center text-gray-300 shrink-0">→</span>
          <FlowStep no="4" title="검수" sub="검수자 지정 시 승인해야 완료 처리" count={`${flow.review}`} active={flow.review > 0} />
          <span className="self-center text-gray-300 shrink-0">→</span>
          <FlowStep no="5" title="완료" sub="완료 이력으로 축적" count={`${flow.done}`} />
        </div>
      </div>

      {/* ── 배선 — 담당 미지정 작업의 자동 배정 규칙 (위에서부터 첫 매칭 적용) ── */}
      <div className="glass p-3.5">
        <button onClick={() => setWireOpen((v) => !v)} className="w-full flex items-center justify-between">
          <span className="text-[13px] font-bold text-gray-900">
            배선 <span className="text-gray-400 font-normal">{rules.length}</span>
          </span>
          <span className="text-[11px] text-gray-400">
            담당 없이 등록된 작업을 조건에 따라 자동 배정 · {wireOpen ? "접기 ▲" : "펼치기 ▼"}
          </span>
        </button>

        {wireOpen && (
          <div className="mt-3 space-y-1.5">
            {rules.map((r, i) => {
              const color = WIRE_COLORS[i % WIRE_COLORS.length];
              const cond = [r.match.project || "모든 프로젝트", r.match.keyword ? `"${r.match.keyword}"` : ""].filter(Boolean).join(" · ");
              const target = r.assign.assignee === "hermes" ? `AI${r.assign.ai_role ? ` · ${r.assign.ai_role}` : ""}` : whoShort(r.assign.assignee);
              return (
                <div key={r.id} className={`flex items-center gap-0 rounded-lg border border-gray-200 px-3 py-2 ${r.enabled ? "" : "opacity-45"}`}>
                  <span className="text-[10px] text-gray-400 w-5 shrink-0">{i + 1}</span>
                  <span className="shrink-0 rounded-md px-2 py-1 text-[12px] font-medium bg-gray-100 text-gray-700 max-w-[180px] truncate">{cond}</span>
                  <svg width="46" height="10" className="shrink-0 mx-0.5"><line x1="2" y1="5" x2="40" y2="5" stroke={color} strokeWidth="2" /><circle cx="42" cy="5" r="3" fill={color} /></svg>
                  <span className="shrink-0 rounded-md px-2 py-1 text-[12px] font-semibold" style={{ background: `${color}22`, color }}>{target}</span>
                  {r.assign.reviewer && (
                    <>
                      <svg width="34" height="10" className="shrink-0 mx-0.5"><line x1="2" y1="5" x2="28" y2="5" stroke={color} strokeWidth="1.5" strokeDasharray="3 3" /><circle cx="30" cy="5" r="2.5" fill="none" stroke={color} strokeWidth="1.5" /></svg>
                      <span className="shrink-0 rounded-md px-2 py-1 text-[12px] bg-gray-100 text-gray-600 truncate">검수 {whoShort(r.assign.reviewer)}</span>
                    </>
                  )}
                  <span className="ml-auto flex items-center gap-1 shrink-0">
                    <button onClick={() => moveRule(i, -1)} className="text-gray-300 hover:text-gray-500 text-[11px] px-0.5" title="위로">▲</button>
                    <button onClick={() => moveRule(i, 1)} className="text-gray-300 hover:text-gray-500 text-[11px] px-0.5" title="아래로">▼</button>
                    <button onClick={() => saveRules(rules.map((x) => x.id === r.id ? { ...x, enabled: !x.enabled } : x))}
                      className={`text-[11px] px-1.5 py-0.5 rounded ${r.enabled ? "bg-gray-100 text-gray-600" : "text-gray-400"}`}>
                      {r.enabled ? "켜짐" : "꺼짐"}
                    </button>
                    <button onClick={() => saveRules(rules.filter((x) => x.id !== r.id))} className="text-gray-300 hover:text-red-500"><Icon name="x" size={13} /></button>
                  </span>
                </div>
              );
            })}

            {/* 새 배선 */}
            <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-3 py-2">
              <select value={wProject} onChange={(e) => setWProject(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-1.5 py-1">
                <option value="">모든 프로젝트</option>
                {projects.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <input value={wKeyword} onChange={(e) => setWKeyword(e.target.value)} placeholder="키워드 (선택)"
                className="w-32 rounded-md border border-gray-300 px-2 py-1 text-[12px]" />
              <span className="text-gray-300">→</span>
              <select value={wAssign} onChange={(e) => setWAssign(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-1.5 py-1">
                <option value="">담당 선택</option>
                {roles.map((r) => <option key={r.role} value={`ai:${r.role}`}>AI · {r.role}</option>)}
                {members.map((m) => <option key={m} value={m}>{whoShort(m)}</option>)}
              </select>
              <select value={wReviewer} onChange={(e) => setWReviewer(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-1.5 py-1">
                <option value="">검수 없음</option>
                {members.map((m) => <option key={m} value={m}>검수 {whoShort(m)}</option>)}
              </select>
              <button onClick={addRule} disabled={!wAssign}
                className="ml-auto px-3 py-1.5 rounded-md text-[12px] font-semibold text-white disabled:opacity-40" style={{ background: "#2f6fed" }}>
                배선 추가
              </button>
            </div>
            <div className="text-[11px] text-gray-400 px-1">위에서부터 첫 번째로 맞는 규칙이 적용됩니다 · 담당을 직접 지정한 작업에는 개입하지 않습니다</div>
          </div>
        )}
      </div>

      <div className="flex h-[calc(100vh-230px)] gap-0 glass overflow-hidden">
      {/* ── 좌: 직군 ── */}
      <div className="hidden lg:flex w-52 shrink-0 flex-col border-r border-gray-200">
        <div className="px-3.5 h-12 flex items-center justify-between border-b border-gray-200 shrink-0">
          <span className="text-[14px] font-bold text-gray-900">AI 팀</span>
          <span className="inline-flex items-center gap-1 text-[11px] text-gray-500">
            <span className={live ? "dot dot-run" : "dot dot-err"} />{live ? `${running} 실행` : "워커 대기"}
          </span>
        </div>
        <div className="flex-1 overflow-y-auto thin-scroll p-2">
          <button onClick={() => { setMode("new"); setSelRole(null); }}
            className="w-full mb-2 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] text-gray-600 hover:bg-gray-100">
            <Icon name="plus" size={14} /> 역할 추가
          </button>
          <div className="px-2.5 mb-1 text-[11px] font-semibold text-gray-400">직군</div>
          <button onClick={() => setCat("")}
            className={`w-full text-left flex items-center justify-between rounded-md px-2.5 py-1.5 text-[13px] ${!cat ? "bg-gray-100 font-semibold text-gray-900" : "text-gray-600 hover:bg-gray-50"}`}>
            <span>전체</span><span className="text-[11px] text-gray-400">{roles.length}</span>
          </button>
          {categories.map(([c, n]) => (
            <button key={c} onClick={() => setCat(c)}
              className={`w-full text-left flex items-center justify-between rounded-md px-2.5 py-1.5 text-[13px] ${cat === c ? "bg-gray-100 font-semibold text-gray-900" : "text-gray-600 hover:bg-gray-50"}`}>
              <span className="truncate">{c}</span><span className="text-[11px] text-gray-400">{n}</span>
            </button>
          ))}
        </div>
        <div className="border-t border-gray-200 p-2">
          <Link href="/agents/cost" className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] text-gray-600 hover:bg-gray-50">
            <Icon name="dollar" size={14} /> 비용
          </Link>
        </div>
      </div>

      {/* ── 중: 역할 목록 ── */}
      <div className={`${detailOpen ? "hidden lg:flex" : "flex"} w-full lg:w-[340px] shrink-0 flex-col border-r border-gray-200`}>
        <div className="px-4 h-12 flex items-center justify-between border-b border-gray-200 shrink-0">
          <span className="text-[14px] font-bold text-gray-900">{cat || "전체 역할"} <span className="text-gray-400 font-normal">{shown.length}</span></span>
          <button onClick={() => { setMode("new"); setSelRole(null); }} className="lg:hidden p-1.5 text-gray-500"><Icon name="plus" size={16} /></button>
        </div>
        <div className="flex-1 overflow-y-auto thin-scroll p-2.5 space-y-1.5">
          {shown.length === 0 ? (
            <div className="py-14 text-center">
              <div className="text-[13px] text-gray-400 mb-2">아직 역할이 없습니다</div>
              <button onClick={() => { setMode("new"); setSelRole(null); }} className="text-[13px] font-medium" style={{ color: "#4b8bfa" }}>+ 첫 역할 만들기</button>
            </div>
          ) : shown.map((r) => {
            const n = aiTasksOf(r.role).length;
            const on = selRole === r.role && mode === "view";
            return (
              <button key={r.role} onClick={() => { setSelRole(r.role); setMode("view"); }}
                className={`w-full text-left rounded-lg border px-3 py-2.5 transition-colors ${on ? "border-gray-300 bg-gray-100" : "border-gray-200 bg-white hover:bg-gray-50"}`}>
                <div className="flex items-center gap-2">
                  <span className="w-7 h-7 rounded-md bg-gray-100 flex items-center justify-center text-gray-600 shrink-0"><Icon name="cpu" size={13} /></span>
                  <span className="flex-1 min-w-0 text-[13px] font-semibold text-gray-900 truncate">{r.role}</span>
                  {n > 0 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded shrink-0" style={{ background: "rgba(75,139,250,0.15)", color: "#6ca0f8" }}>작업 {n}</span>
                  )}
                </div>
                {r.description && <div className="mt-1 pl-9 text-[12px] text-gray-500 truncate">{r.description}</div>}
                <div className="mt-1 pl-9 flex items-center gap-2 text-[11px] text-gray-400">
                  <span>{catOf(r)}</span>
                  {r.persona ? <span className="text-gray-400">· 페르소나 있음</span> : <span className="text-gray-300">· 페르소나 없음</span>}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── 우: 상세/편집 (데스크톱) ── */}
      <div className="hidden lg:flex flex-1 min-w-0 flex-col">
        {detailOpen ? detailPane : (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
            <div className="text-[13px] text-gray-400 mb-1.5">역할을 선택하면 페르소나·직군을 편집할 수 있습니다</div>
            {!live && <div className="text-[12px] text-gray-500">AI 워커 미연결 — AI 담당 작업은 대기 상태로 쌓이며, 워커 연결 시 자동 처리됩니다</div>}
          </div>
        )}
      </div>

      {/* ── 모바일 상세 오버레이 ── */}
      {detailOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex flex-col" style={{ background: "#131417" }}>
          {detailPane}
        </div>
      )}
      </div>
    </div>
  );
}
