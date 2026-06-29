"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";

// 음성 업무 — 회의/지시 녹음 → STT → 요약 + task 분해 → 검토/편집 → 선택 생성.
// 안전: 잘못 인식돼도 이 화면에서 사람이 보고 고른 것만 task가 됨(human-in-loop).

interface DraftTask { title: string; description: string; team?: string; sel: boolean; }
interface RecentCmd { title?: string; created_at?: string; status?: string; }
interface Meeting { _id: string; summary: string; transcript: string; tasks: { title: string; description: string; team?: string }[]; created_at: string; }

const TEAM_LABEL: Record<string, string> = { dev: "dev", art: "art", design: "design", chat: "chat" };
const TEAM_ICON: Record<string, string> = { dev: "code", art: "palette", design: "ruler", chat: "chat" };

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

export default function VoicePage() {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [transcript, setTranscript] = useState("");
  const [summary, setSummary] = useState("");
  const [tasks, setTasks] = useState<DraftTask[]>([]);
  const [created, setCreated] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [showHelp, setShowHelp] = useState(false);
  const [recent, setRecent] = useState<RecentCmd[]>([]);
  const [kind, setKind] = useState<"meeting" | "query" | "">("");
  const [answer, setAnswer] = useState("");
  const [qstatus, setQstatus] = useState("");
  const [evidence, setEvidence] = useState<string[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const mrRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRecent = () => {
    fetch("/api/tasks").then((r) => r.json()).then((d) => {
      if (Array.isArray(d)) {
        const v = d.filter((t) => t.created_via === "voice")
          .sort((a, b) => Date.parse(b.created_at || "") - Date.parse(a.created_at || ""))
          .slice(0, 5);
        setRecent(v);
      }
    }).catch(() => {});
  };
  const loadMeetings = () => {
    fetch("/api/meetings").then((r) => r.json()).then((d) => setMeetings(d.meetings || [])).catch(() => {});
  };
  useEffect(() => { loadRecent(); loadMeetings(); }, []);

  const openMeeting = (m: Meeting) => {
    setKind("meeting"); setAnswer(""); setEvidence([]); setCreated(0); setErr("");
    setSummary(m.summary); setTranscript(m.transcript);
    setTasks((m.tasks || []).map((t) => ({ ...t, sel: true })));
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const delMeeting = async (id: string) => {
    await fetch(`/api/meetings?id=${id}`, { method: "DELETE" }).catch(() => {});
    loadMeetings();
  };

  const start = async () => {
    setErr(""); setTranscript(""); setSummary(""); setTasks([]); setCreated(0); setAnswer(""); setEvidence([]); setKind("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        upload(blob);
      };
      mr.start();
      mrRef.current = mr;
      setRecording(true);
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } catch (e) {
      const nm = (e as { name?: string })?.name || "";
      if (nm === "NotFoundError" || nm === "DevicesNotFoundError")
        setErr("마이크 장치가 없습니다 (데스크톱). 폰에서 녹음하거나, 아래 '오디오 파일 업로드'로 진행하세요.");
      else if (nm === "NotAllowedError" || nm === "PermissionDeniedError")
        setErr("마이크 권한 거부됨 — 브라우저 주소창 권한에서 마이크 허용 후 다시 시도.");
      else
        setErr(`마이크 접근 실패 (${nm}): ${String(e)}`);
    }
  };

  const stop = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setRecording(false);
    mrRef.current?.stop();
  };

  const upload = async (blob: Blob, name?: string) => {
    setBusy(true); setErr("");
    try {
      let fname = name && name.includes(".") ? name : "";
      if (!fname) {
        const t = blob.type;
        const ext = (t.includes("mpeg") || t.includes("mp3")) ? "mp3" : t.includes("wav") ? "wav"
          : (t.includes("mp4") || t.includes("m4a")) ? "m4a" : t.includes("ogg") ? "ogg" : "webm";
        fname = `meeting.${ext}`;
      }
      const fd = new FormData();
      fd.append("audio", blob, fname);
      const r = await fetch("/api/voice", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) { setErr(j.error + (j.detail ? ` — ${j.detail}` : "")); return; }
      setTranscript(j.transcript || "");
      setKind(j.kind || "meeting");
      if (j.kind === "query") {
        setAnswer(j.answer || ""); setQstatus(j.status || ""); setEvidence(j.evidence || []);
        setTasks((j.suggestions || []).map((t: { title: string; description: string }) => ({ title: t.title, description: t.description, sel: false })));
      } else {
        setSummary(j.summary || "");
        setTasks((j.tasks || []).map((t: { title: string; description: string; team?: string }) => ({ ...t, sel: true })));
        loadMeetings();
      }
    } catch (e) {
      setErr("업로드/분석 실패: " + String(e));
    } finally {
      setBusy(false);
    }
  };

  const createSelected = async () => {
    setBusy(true);
    let n = 0;
    for (const t of tasks) {
      if (!t.sel || !t.title.trim()) continue;
      const body: Record<string, unknown> = {
        title: t.title.trim(), description: t.description.trim(),
        assignee: "hermes", status: "todo", priority: "medium", created_via: "voice",
      };
      if (t.team && ["dev", "art", "design"].includes(t.team)) { body.team = t.team; body.team_override = true; }
      try {
        const r = await fetch("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (r.ok) n++;
      } catch { /* skip */ }
    }
    setCreated(n);
    setBusy(false);
    loadRecent();
  };

  const upd = (i: number, patch: Partial<DraftTask>) => setTasks((ts) => ts.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const mmss = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  const selCount = tasks.filter((t) => t.sel).length;

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Icon name="mic" size={22} /> 음성 명령</h1>
          <p className="text-sm text-gray-500 mt-1">말하면 AI가 <b>업무 지시</b>인지 <b>코드 상태 질문</b>인지 스스로 구분해 처리합니다. 결과를 검토·선택해 Hermes에 보냅니다.</p>
        </div>
        <button onClick={() => setShowHelp(true)} aria-label="안내" title="안내"
          className="shrink-0 w-7 h-7 rounded-full border border-gray-300 text-gray-400 hover:text-gray-200 hover:border-gray-400 flex items-center justify-center"><Icon name="help" size={15} /></button>
      </div>

      {showHelp && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 fade-in" onClick={() => setShowHelp(false)}>
          <div className="bg-white rounded-xl max-w-md w-full p-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold text-sm flex items-center gap-1.5"><Icon name="help" size={16} /> 안내</h3>
              <button onClick={() => setShowHelp(false)} className="text-gray-400 hover:text-gray-200"><Icon name="x" size={18} /></button>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">STT는 완벽하지 않습니다(고유명사·다화자). 각 업무를 검토·편집한 뒤 선택하세요. 생성된 업무도 Hermes 검증 게이트(컴파일·회귀·Reviewer)를 거쳐 배포 전 Slack 승인됩니다.</p>
          </div>
        </div>
      )}

      {/* 녹음 패널 — 글로우 마이크 */}
      <div className="rounded-2xl border border-gray-200 bg-white p-8 flex flex-col items-center gap-4 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(ellipse 60% 50% at 50% 20%, rgba(59,130,246,0.10), transparent 70%)" }} />
        <div className="relative">
          {recording && <span className="absolute inset-0 rounded-full bg-rose-500/30 animate-ping" />}
          {!recording ? (
            <button onClick={start} disabled={busy} aria-label="녹음 시작"
              className="relative w-32 h-32 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-xl ring-4 ring-blue-500/20 active:scale-95 disabled:opacity-50 flex items-center justify-center transition-transform">
              <Icon name="mic" size={52} />
            </button>
          ) : (
            <button onClick={stop} aria-label="정지"
              className="relative w-32 h-32 rounded-full bg-rose-500 text-white shadow-xl ring-4 ring-rose-500/30 flex items-center justify-center">
              <span className="w-8 h-8 rounded-md bg-white" />
            </button>
          )}
        </div>
        <div className="relative text-sm text-gray-500 inline-flex items-center gap-1.5 min-h-[20px]">
          {recording ? (<><span className="text-rose-500"><Icon name="dot" size={9} /></span> 녹음 중 {mmss} · 다시 누르면 정지</>)
            : busy ? (<><Icon name="clock" size={14} /> 전사·분석 중…</>)
            : "버튼을 눌러 말하면 명령을 인식합니다"}
        </div>
        {!recording && !busy && (
          <label className="relative text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 cursor-pointer inline-flex items-center gap-1.5">
            <Icon name="music" size={14} /> 오디오 파일 업로드
            <input type="file" accept="audio/*" className="hidden" disabled={busy}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f, f.name); }} />
          </label>
        )}
      </div>

      {err && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{err}</div>}

      {kind === "query" && answer && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${qstatus === "implemented" ? "bg-emerald-50 text-emerald-700" : qstatus === "partial" ? "bg-amber-50 text-amber-700" : "bg-rose-50 text-rose-700"}`}>
              {qstatus === "implemented" ? "구현됨" : qstatus === "partial" ? "부분 구현" : "미구현/확인불가"}
            </span>
            <span className="text-sm font-semibold flex items-center gap-1.5"><Icon name="search" size={14} /> 코드 기반 답변</span>
          </div>
          <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{answer}</div>
          {evidence.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {evidence.map((e, i) => <span key={i} className="text-[11px] px-2 py-0.5 rounded-full border border-gray-200 text-gray-500">{e}</span>)}
            </div>
          )}
          <div className="text-[11px] text-gray-400 mt-2">근거: 실제 코드 그래프(DNA) · 정적 구조 기준 (런타임 동작은 빌드/플레이 필요)</div>
        </div>
      )}

      {summary && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4">
          <div className="font-semibold text-sm mb-1.5 flex items-center gap-1.5"><Icon name="doc" size={15} /> 회의 요약</div>
          <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{summary}</div>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="font-semibold text-sm">{kind === "query" ? "제안 작업" : "도출된 업무"} <span className="text-gray-400 font-normal">({selCount}/{tasks.length} 선택)</span></div>
            <button onClick={createSelected} disabled={busy || selCount === 0}
              className="text-sm px-3 py-1.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-40">선택 {selCount}건 던지기</button>
          </div>
          {tasks.map((t, i) => (
            <div key={i} className={`rounded-xl border p-3 transition-opacity ${t.sel ? "border-gray-300 bg-white" : "border-gray-200 bg-gray-50 opacity-60"}`}>
              <div className="flex items-start gap-2.5">
                <input type="checkbox" checked={t.sel} onChange={(e) => upd(i, { sel: e.target.checked })} className="mt-1.5 accent-blue-500" />
                <div className="flex-1 space-y-1.5">
                  <input value={t.title} onChange={(e) => upd(i, { title: e.target.value })}
                    className="w-full text-sm font-semibold border-b border-gray-200 focus:border-blue-400 outline-none py-0.5 bg-transparent" />
                  <textarea value={t.description} onChange={(e) => upd(i, { description: e.target.value })} rows={2}
                    className="w-full text-xs text-gray-600 border border-gray-100 rounded-lg p-2 outline-none focus:border-blue-300" />
                  {t.team && <span className="inline-flex items-center gap-1 text-[11px] text-gray-400"><Icon name={TEAM_ICON[t.team] || "bot"} size={12} /> {TEAM_LABEL[t.team] || t.team}</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {created > 0 && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 flex items-center gap-1.5">
          <Icon name="check" size={15} /> {created}건 생성 완료 — <a href="/tasks" className="underline">작업 보드</a>에서 확인. Hermes가 순서대로 처리합니다.
        </div>
      )}

      {transcript && (
        <details className="rounded-2xl border border-gray-200 bg-white p-4 text-xs text-gray-500">
          <summary className="cursor-pointer font-medium text-gray-600">전사 원문 보기</summary>
          <div className="mt-2 whitespace-pre-wrap leading-relaxed">{transcript}</div>
        </details>
      )}

      {/* 저장된 회의 (영구) — 다시 열어 업무 선택·생성 */}
      {meetings.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4">
          <div className="font-semibold text-sm mb-2 flex items-center gap-1.5"><Icon name="doc" size={15} /> 저장된 회의</div>
          <ul className="divide-y divide-gray-100">
            {meetings.map((m) => (
              <li key={m._id} className="py-2.5 flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{m.summary ? m.summary.split("\n")[0] : "(요약 없음)"}</div>
                  <div className="text-[11px] text-gray-400 mt-0.5">{timeAgo(m.created_at)} · 업무 {m.tasks.length}건</div>
                </div>
                <button onClick={() => openMeeting(m)} className="text-xs px-2.5 py-1 rounded-lg border border-gray-200 hover:bg-gray-50 shrink-0">열기</button>
                <button onClick={() => delMeeting(m._id)} aria-label="삭제" className="text-gray-300 hover:text-rose-500 shrink-0 mt-0.5"><Icon name="x" size={15} /></button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 최근 음성 명령 (실데이터 — created_via=voice) */}
      {recent.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4">
          <div className="font-semibold text-sm mb-2 flex items-center gap-1.5"><Icon name="clock" size={15} /> 최근 음성 명령</div>
          <ul className="divide-y divide-gray-100">
            {recent.map((c, i) => (
              <li key={i} className="flex items-center gap-2 py-2 text-sm">
                <span className="text-gray-400 text-xs w-4 shrink-0">{i + 1}</span>
                <a href="/tasks" className="flex-1 truncate hover:underline">{c.title}</a>
                <span className="text-[11px] text-gray-400 shrink-0">{timeAgo(c.created_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
