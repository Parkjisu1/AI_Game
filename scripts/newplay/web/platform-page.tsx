"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Md from "@/components/Md";

/**
 * 플랫폼 현황 — webstore 가 어떤 기능으로 구성돼 있는지 + 지금 살아 있는지 한 화면에서 본다.
 *
 * 두 축을 한 화면에 둔 이유: "구성"만 보면 지금 도는지 모르고, "상태"만 보면 무엇이 도는지 모른다.
 * 상단은 10초마다 갱신되는 실시간, 하단은 커밋 때만 바뀌는 구성도(스냅샷)다.
 *
 * 해상도: 모바일 1열 → 태블릿 2열 → 데스크톱 3~4열. 구성도는 좁은 화면에서 세로로 쌓인다.
 */

type Svc = { name: string; label: string; ok: boolean; detail: string; ms: number };
type FileItem = { path: string; kind: string; lang: string; lines: number; symbols: string[] };
type Mod = { name: string; files: number; lines: number; kinds: Record<string, number>; items: FileItem[] };
type Area = { area: string; files: number; lines: number; modules: Mod[] };
type Screen = { path: string; component: string; section: string; params: string[] };
type Env = { key: string; label: string; url: string };
type Comp = {
  project: string; sha: string; generatedAt: string; liveBaseUrl?: string; screens?: Screen[]; envs?: Env[];
  totals: { files: number; chunks: number; lines: number; areas: number; modules: number };
  kindCount: Record<string, number>;
  tree: Area[];
  apis: { path: string; module: string; handlers: string[] }[];
  entities: { path: string; name: string }[];
};
type Payload = {
  services: Svc[];
  kb: { points?: number; dim?: number };
  tasks: { todo: number; in_progress: number; review: number; done: number;
           recent: { _id: string; title: string; status: string; team?: string; sub_team?: string; updated_at?: string }[] };
  sessions: { _id: string; role: string; model: string; success: boolean; duration_sec: number; created_at: string; task_title?: string }[];
  composition: Comp | null;
};

const KIND_LABEL: Record<string, string> = {
  api: "API", service: "서비스", entity: "엔티티", component: "컴포넌트",
  test: "테스트", infra: "인프라", doc: "문서", style: "스타일",
  migration: "마이그레이션", code: "기타 코드",
};

const KIND_COLOR: Record<string, string> = {
  api: "bg-blue-100 text-blue-700", entity: "bg-purple-100 text-purple-700",
  component: "bg-emerald-100 text-emerald-700", test: "bg-amber-100 text-amber-700",
  infra: "bg-slate-200 text-slate-700", doc: "bg-gray-100 text-gray-600",
  style: "bg-pink-100 text-pink-700", migration: "bg-orange-100 text-orange-700",
  service: "bg-cyan-100 text-cyan-700", code: "bg-gray-100 text-gray-600",
};

function ago(iso?: string) {
  if (!iso) return "-";
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}초 전`;
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}

export default function PlatformPage() {
  const [d, setD] = useState<Payload | null>(null);
  const [err, setErr] = useState("");
  const [area, setArea] = useState("");
  const [mod, setMod] = useState("");
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<"tree" | "api" | "entity" | "screen" | "doc">("screen");
  // 산출물(문서) — design·data 결과는 미리보기에 나올 수 없어 여기서 읽고 판정한다.
  type DocItem = { _id: string; title: string; team?: string; sub_team?: string; deliverable_role?: string;
                   deliverable_at?: string; chars: number; criteria: { total: number; ok: number; ng: number } };
  type Crit = { id: string; text: string; state: string; judged_by?: string };
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [docId, setDocId] = useState("");
  const [docBody, setDocBody] = useState<{ deliverable?: string; acceptance_criteria?: Crit[]; title?: string } | null>(null);
  const loadDocs = () => fetch("/api/platform/deliverables")
    .then((r) => r.json()).then((j) => setDocs(Array.isArray(j?.items) ? j.items : [])).catch(() => {});
  useEffect(() => { loadDocs(); }, []);
  useEffect(() => {
    if (!docId) { setDocBody(null); return; }
    fetch(`/api/platform/deliverables?id=${docId}`).then((r) => r.json())
      .then((j) => setDocBody(j?.item || null)).catch(() => setDocBody(null));
  }, [docId]);
  const [mockMsg, setMockMsg] = useState("");
  const [making, setMaking] = useState(false);
  // 설계 문서 → 화면 목업 dev 태스크. 태스크 하나를 만들 뿐 레포엔 아무것도 쓰지 않는다.
  const makeMockup = async () => {
    if (!docId) return;
    setMaking(true); setMockMsg("목업 태스크 생성 중…");
    try {
      const r = await fetch("/api/platform/mockup", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: docId }),
      });
      const j = await r.json();
      setMockMsg(j?.ok
        ? `${j.reused ? "이미 있는 목업 태스크입니다" : "목업 태스크를 만들었습니다"} — 작업 보드에서 진행되며, 끝나면 앱 화면 → 수정안에서 볼 수 있습니다. ${j.warning || ""}`
        : `실패: ${j?.error || "알 수 없음"}`);
    } catch (e) {
      setMockMsg("실패: " + String((e as Error).message || e));
    } finally { setMaking(false); }
  };

  const judge = async (cid: string, state: string) => {
    if (!docId) return;
    await fetch("/api/platform/deliverables", {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: docId, cid, state }),
    }).catch(() => {});
    // 낙관적 갱신 대신 다시 읽는다 — 판정은 사람이 믿어야 하는 값이라 화면과 DB 가 어긋나면 안 된다.
    const j = await fetch(`/api/platform/deliverables?id=${docId}`).then((r) => r.json()).catch(() => null);
    if (j?.item) setDocBody(j.item);
    loadDocs();
  };
  const [screen, setScreen] = useState("");
  // 실제 앱을 어느 폭으로 볼지 — 해상도 대응 확인용
  const [device, setDevice] = useState<"mobile" | "tablet" | "desktop">("desktop");
  // 미리보기 박스의 실제 폭 — 프리셋이 이보다 넓으면 축소해서 전체를 보여준다.
  const frameBoxRef = useRef<HTMLDivElement | null>(null);
  const [boxW, setBoxW] = useState(0);
  useEffect(() => {
    // 좁은 화면에서 데스크톱 1440 으로 시작하면 왼쪽 귀퉁이만 보인다.
    if (typeof window !== "undefined" && window.innerWidth < 640) setDevice("mobile");
    const measure = () => setBoxW(frameBoxRef.current?.clientWidth ?? 0);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  // 어느 환경을 볼지 — 운영 / QA. 배포되지 않은 작업본은 어디에도 없다.
  const [env, setEnv] = useState("prod");
  // 수정안 미리보기 상태 — 어떤 패치가 언제 적용돼 빌드됐는지
  const [prev, setPrev] = useState<{ ok: boolean; patch: string; files: number; baseSha: string; finishedAt: string; error?: string } | null>(null);
  const [cands, setCands] = useState<{ _id: string; title: string; status?: string; team?: string; patch_files?: string[]; patch_role?: string; patch_at?: string; previewable?: boolean; reason?: string }[]>([]);
  const [building, setBuilding] = useState("");
  const [buildMsg, setBuildMsg] = useState("");
  const [nonce, setNonce] = useState(0);   // 빌드 후 iframe 을 강제로 다시 그린다

  const loadPreview = () => fetch("/api/platform/preview")
    .then((r) => r.json())
    .then((j) => { setPrev(j?.state || null); setCands(Array.isArray(j?.candidates) ? j.candidates : []); })
    .catch(() => {});
  useEffect(() => { loadPreview(); }, []);

  // 헤르메스 제안을 미리보기로 빌드한다. 운영·QA 에는 아무 영향이 없다.
  const buildPreview = async (taskId: string, label: string) => {
    setBuilding(taskId || "reset");
    setBuildMsg(`${label} 빌드 중…`);
    try {
      const r = await fetch("/api/platform/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(taskId ? { taskId } : { reset: true }),
      });
      const j = await r.json();
      setBuildMsg(j?.ok ? `${label} 반영 완료` : `실패: ${j?.error || j?.state?.error || "알 수 없음"}`);
      await loadPreview();
      setEnv("preview");
      setNonce((n) => n + 1);
    } catch (e) {
      setBuildMsg("실패: " + String((e as Error).message || e));
    } finally {
      setBuilding("");
    }
  };

  // 최초 1회는 구성도까지, 이후 10초 폴링은 상태만 받는다(구성도 약 220KB 재전송 방지).
  const load = (live: boolean) => fetch(`/api/platform/overview${live ? "?live=1" : ""}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
    .then((j) => {
      setD((prev) => (live && prev ? { ...j, composition: prev.composition } : j));
      setErr("");
    })
    .catch((e) => setErr(String(e.message || e)));

  useEffect(() => {
    load(false);
    const id = setInterval(() => load(true), 10000);
    return () => clearInterval(id);
  }, []);

  const comp = d?.composition || null;
  const areas = comp?.tree || [];
  const curArea = useMemo(
    () => areas.find((a) => a.area === area) || areas[0] || null,
    [areas, area],
  );
  const mods = useMemo(() => {
    const list = curArea?.modules || [];
    if (!q.trim()) return list;
    const k = q.trim().toLowerCase();
    return list.filter((m) =>
      m.name.toLowerCase().includes(k) ||
      m.items.some((f) => f.path.toLowerCase().includes(k) || f.symbols.some((s) => s.toLowerCase().includes(k))));
  }, [curArea, q]);
  const curMod = useMemo(
    () => mods.find((m) => m.name === mod) || mods[0] || null,
    [mods, mod],
  );

  const files = useMemo(() => {
    const list = curMod?.items || [];
    if (!q.trim()) return list;
    const k = q.trim().toLowerCase();
    return list.filter((f) => f.path.toLowerCase().includes(k) || f.symbols.some((s) => s.toLowerCase().includes(k)));
  }, [curMod, q]);

  if (err) {
    return <div className="glass p-4 text-sm text-red-600">불러오기 실패: {err}</div>;
  }
  if (!d) {
    return <div className="glass p-4 text-sm text-gray-500">불러오는 중…</div>;
  }

  return (
    <div className="w-full min-w-0 space-y-4 overflow-x-hidden">
      {/* ── 실시간 상태 ─────────────────────────────── */}
      <section>
        <h2 className="mb-2 text-[13px] font-bold text-gray-900">실시간 상태</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
          {d.services.map((s) => (
            <div key={s.name} className="glass p-3">
              <div className="flex items-center gap-1.5">
                <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${s.ok ? "bg-emerald-500" : "bg-red-500"}`} />
                <span className="min-w-0 truncate text-[12px] font-semibold text-gray-900">{s.label}</span>
              </div>
              <div className="mt-1 truncate text-[11px] text-gray-500" title={s.detail}>{s.detail}</div>
              <div className="mt-0.5 text-[10px] text-gray-400">{s.ms}ms</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 작업 / 활동 ─────────────────────────────── */}
      <section className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="glass p-3.5">
          <h3 className="mb-2 text-[13px] font-bold text-gray-900">작업 현황</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([["todo", "대기"], ["in_progress", "진행"], ["review", "검수"], ["done", "완료"]] as const).map(([k, label]) => (
              <div key={k} className="rounded border border-gray-200 p-2 text-center">
                <div className="text-lg font-bold text-gray-900">{d.tasks[k]}</div>
                <div className="text-[11px] text-gray-500">{label}</div>
              </div>
            ))}
          </div>
          <ul className="mt-2.5 space-y-1">
            {d.tasks.recent.map((t) => (
              <li key={t._id} className="flex items-center gap-2 text-[11px]">
                <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-gray-600">{t.status}</span>
                <span className="min-w-0 flex-1 truncate text-gray-800">{t.title}</span>
                <span className="ml-auto shrink-0 text-gray-400">{ago(t.updated_at)}</span>
              </li>
            ))}
            {!d.tasks.recent.length && <li className="text-[11px] text-gray-400">아직 작업이 없습니다.</li>}
          </ul>
        </div>

        <div className="glass p-3.5">
          <h3 className="mb-2 text-[13px] font-bold text-gray-900">최근 AI 실행</h3>
          <ul className="space-y-1">
            {d.sessions.map((s) => (
              <li key={s._id} className="flex items-center gap-2 text-[11px]">
                <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${s.success ? "bg-emerald-500" : "bg-red-500"}`} />
                <span className="shrink-0 font-medium text-gray-800">{s.role}</span>
                <span className="hidden shrink-0 text-gray-400 sm:inline">{s.model}</span>
                <span className="min-w-0 flex-1 truncate text-gray-500">{s.task_title || ""}</span>
                <span className="ml-auto shrink-0 text-gray-400">{Math.round(s.duration_sec)}s · {ago(s.created_at)}</span>
              </li>
            ))}
            {!d.sessions.length && <li className="text-[11px] text-gray-400">실행 기록이 없습니다.</li>}
          </ul>
        </div>
      </section>

      {/* ── 구성도 ─────────────────────────────────── */}
      {!comp ? (
        <div className="glass p-4 text-sm text-gray-500">
          구성도 스냅샷이 없습니다. <code className="rounded bg-gray-100 px-1">node ~/newplay-index/build-platform-map.js</code> 로 생성하세요.
        </div>
      ) : (
        <section className="glass p-3.5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-bold text-gray-900">플랫폼 구성 — {comp.project}</h3>
            <span className="text-[11px] text-gray-400">
              파일 {comp.totals.files.toLocaleString()} · 모듈 {comp.totals.modules} · {comp.totals.lines.toLocaleString()}줄
              {comp.sha ? ` · ${comp.sha.slice(0, 7)}` : ""} · {ago(comp.generatedAt)} 기준
            </span>
            <input
              value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="모듈·파일·심볼 검색"
              className="ml-auto w-full rounded border border-gray-300 px-2 py-1 text-[12px] sm:w-56"
            />
          </div>

          {/* 종류 분포 */}
          <div className="mt-2 flex flex-wrap gap-1">
            {Object.entries(comp.kindCount).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
              <span key={k} className={`rounded px-1.5 py-0.5 text-[10px] ${KIND_COLOR[k] || "bg-gray-100 text-gray-600"}`}>
                {KIND_LABEL[k] || k} {v}
              </span>
            ))}
          </div>

          {/* 탭 */}
          <div className="mt-3 flex gap-1 border-b border-gray-200">
            {([["screen", `앱 화면 (${comp.screens?.length ?? 0})`], ["doc", `산출물 (${docs.length})`], ["tree", "모듈 구조"], ["api", `API (${comp.apis.length})`], ["entity", `엔티티 (${comp.entities.length})`]] as const).map(([k, label]) => (
              <button
                key={k} onClick={() => setTab(k)}
                className={`px-2.5 py-1.5 text-[12px] ${tab === k ? "border-b-2 border-gray-900 font-semibold text-gray-900" : "text-gray-500"}`}
              >{label}</button>
            ))}
          </div>

          {tab === "screen" && (() => {
            const deployed: Env[] = comp.envs?.length ? comp.envs : [{ key: "prod", label: "운영", url: comp.liveBaseUrl || "" }];
            // "수정안" 은 배포된 환경이 아니라 이 서버에서 빌드한 결과다. 항상 선택지로 둔다.
            const envs: Env[] = [...deployed, { key: "preview", label: "수정안", url: "" }];
            const curEnv = envs.find((e) => e.key === env) || envs[0];
            const base = curEnv?.url || "";
            const list = (comp.screens || []).filter(
              (sc) => !q.trim() || sc.path.toLowerCase().includes(q.toLowerCase()) || sc.component.toLowerCase().includes(q.toLowerCase()));
            const cur = list.find((sc) => sc.path === screen) || list[0] || null;
            // :gameSlug 같은 동적 구간은 그대로 열 수 없다. 예시값을 넣어 링크를 만든다.
            const resolved = cur ? cur.path.replace(/:[A-Za-z0-9_]+/g, "demo") : "";
            const url = curEnv?.key === "preview"
              ? (cur ? "/preview" + resolved : "/preview/")
              : (base && cur ? base.replace(/\/$/, "") + resolved : "");
            const W = { mobile: 390, tablet: 820, desktop: 1440 }[device];
            const H = { mobile: 844, tablet: 900, desktop: 810 }[device];
            // 박스보다 넓은 프리셋은 축소해 전체를 보여준다(가로 스크롤보다 이쪽이 읽기 쉽다).
            const scale = boxW > 0 && W > boxW ? boxW / W : 1;
            return (
              <div className="mt-2.5 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
                <div className="max-h-[300px] w-full min-w-0 overflow-y-auto rounded border border-gray-200 xl:max-h-[760px]">
                  {list.map((sc) => (
                    <button
                      key={sc.path} onClick={() => setScreen(sc.path)}
                      className={`flex w-full items-center gap-1.5 border-b border-gray-100 px-2.5 py-1.5 text-left last:border-0 ${cur?.path === sc.path ? "bg-gray-100 font-semibold" : ""}`}
                    >
                      <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${sc.section === "admin" ? "bg-slate-200 text-slate-700" : sc.section === "auth" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                        {sc.section}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[12px] text-gray-900">{sc.path}</span>
                      <span className="ml-auto hidden shrink-0 text-[10px] text-gray-400 sm:inline">{sc.component}</span>
                    </button>
                  ))}
                  {!list.length && <div className="p-3 text-[11px] text-gray-400">화면 없음</div>}
                </div>

                <div className="min-w-0 w-full">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {envs.map((e) => (
                      <button key={e.key} onClick={() => setEnv(e.key)}
                        className={`rounded px-2 py-1 text-[11px] ${curEnv?.key === e.key ? (e.key === "prod" ? "bg-red-600 text-white" : "bg-blue-600 text-white") : "bg-gray-100 text-gray-700"}`}>
                        {e.label}
                      </button>
                    ))}
                    <span className="mx-1 h-4 w-px bg-gray-300" />
                    {(["mobile", "tablet", "desktop"] as const).map((dv) => (
                      <button key={dv} onClick={() => setDevice(dv)}
                        className={`rounded px-2 py-1 text-[11px] ${device === dv ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-700"}`}>
                        {dv === "mobile" ? "모바일 390" : dv === "tablet" ? "태블릿 820" : "데스크톱 1440"}
                      </button>
                    ))}
                    {url && (
                      <a href={url} target="_blank" rel="noopener noreferrer"
                        className="ml-auto truncate text-[11px] text-blue-600 underline">새 탭에서 열기 ↗</a>
                    )}
                  </div>
                  {cur?.params?.length ? (
                    <div className="mt-1.5 text-[11px] text-amber-700">
                      동적 구간 {cur.params.join(", ")} 은(는) 예시값 <code className="rounded bg-amber-50 px-1">demo</code> 로 대체했습니다 — 실제 값으로 바꿔야 화면이 정상 표시됩니다.
                    </div>
                  ) : null}
                  {curEnv?.key === "preview" && (
                    <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12px] font-semibold text-gray-900">헤르메스 제안</span>
                        <button
                          onClick={() => buildPreview("", "원본")}
                          disabled={!!building}
                          className="rounded bg-gray-200 px-2 py-1 text-[11px] text-gray-800 disabled:opacity-50"
                        >원본으로 되돌리기</button>
                        {buildMsg && <span className="text-[11px] text-gray-600">{buildMsg}</span>}
                      </div>
                      <ul className="mt-1.5 space-y-1">
                        {cands.map((t) => {
                          const ok = t.previewable !== false;
                          return (
                            <li key={t._id} className={`flex flex-wrap items-center gap-1.5 ${ok ? "" : "opacity-60"}`}>
                              {ok ? (
                                <button
                                  onClick={() => buildPreview(t._id, t.title.slice(0, 20))}
                                  disabled={!!building}
                                  className="shrink-0 rounded bg-blue-600 px-2 py-0.5 text-[11px] text-white disabled:opacity-50"
                                >{building === t._id ? "빌드 중…" : "미리보기"}</button>
                              ) : (
                                <span className="shrink-0 rounded bg-gray-200 px-2 py-0.5 text-[11px] text-gray-500">미리보기 불가</span>
                              )}
                              <span className="min-w-0 flex-1 truncate text-[11px] text-gray-800">{t.title}</span>
                              <span className="shrink-0 text-[10px] text-gray-400">
                                {ok ? `${(t.patch_files || []).length}개 파일` : t.reason}
                              </span>
                            </li>
                          );
                        })}
                        {!cands.length && (
                          <li className="text-[11px] text-gray-400">
                            아직 패치를 낸 태스크가 없습니다. 헤르메스에 코드 수정을 요청하면 여기에 나타납니다.
                          </li>
                        )}
                      </ul>
                    </div>
                  )}
                  <div className="mt-1.5 truncate text-[11px] text-gray-500">{url || "(서비스 URL 미설정)"}</div>
                  <div ref={frameBoxRef} className="mt-1.5 w-full overflow-hidden rounded border border-gray-200 bg-gray-50 p-2">
                    {url ? (
                      <div style={{ height: H * scale, overflow: "hidden" }}>
                        <iframe
                          key={url + device + nonce}
                          src={url}
                          title={cur?.path || "preview"}
                          width={W} height={H}
                          style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}
                          className="block border-0 bg-white"
                          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                          loading="lazy"
                        />
                      </div>
                    ) : (
                      <div className="p-6 text-center text-[12px] text-gray-400">서비스 URL 이 설정되지 않았습니다.</div>
                    )}
                  </div>
                  <div className="mt-1 text-[10px] text-gray-400">
                    {scale < 1 && `화면 폭에 맞춰 ${Math.round(scale * 100)}% 로 축소해 보여줍니다 (실제 ${W}px 기준). `}
                    {curEnv?.key === "prod"
                      ? "실제 운영 서비스입니다. 로그인이 필요한 화면은 비로그인 상태로 보입니다."
                      : curEnv?.key === "qa"
                      ? "QA 환경입니다. 여기에 배포된 변경은 운영에 올리기 전에 확인할 수 있습니다."
                      : `이 서버에서 직접 빌드한 수정안입니다 — 운영·QA 어디에도 반영되지 않습니다. ${prev ? `적용 패치: ${prev.patch === "none" ? "없음(원본 그대로)" : prev.patch} · ${prev.files}개 파일 · base ${prev.baseSha}` : "아직 빌드된 미리보기가 없습니다."}`}
                  </div>
                </div>
              </div>
            );
          })()}

          {tab === "doc" && (() => {
            const cur = docs.find((x) => x._id === docId) || docs[0] || null;
            if (docId === "" && cur) setTimeout(() => setDocId(cur._id), 0);
            const crits: Crit[] = docBody?.acceptance_criteria || [];
            return (
              <div className="mt-2.5 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
                <div className="max-h-[300px] w-full min-w-0 overflow-y-auto rounded border border-gray-200 xl:max-h-[820px]">
                  {docs.map((d2) => (
                    <button key={d2._id} onClick={() => setDocId(d2._id)}
                      className={`w-full border-b border-gray-100 px-2.5 py-1.5 text-left last:border-0 ${cur?._id === d2._id ? "bg-gray-100" : ""}`}>
                      <div className="flex items-center gap-1.5">
                        <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600">{d2.team}/{d2.sub_team}</span>
                        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-gray-900">{d2.title}</span>
                      </div>
                      <div className="mt-0.5 text-[10px] text-gray-400">
                        {d2.deliverable_role} · {(d2.chars / 1000).toFixed(1)}K자
                        {d2.criteria.total > 0 && ` · 확인 ${d2.criteria.ok}/${d2.criteria.total}`}
                        {d2.criteria.ng > 0 && ` · 아니오 ${d2.criteria.ng}`}
                      </div>
                    </button>
                  ))}
                  {!docs.length && <div className="p-3 text-[11px] text-gray-400">아직 산출물이 없습니다. design·data 태스크가 끝나면 여기에 쌓입니다.</div>}
                </div>

                <div className="min-w-0 w-full">
                  {!docBody ? (
                    <div className="rounded border border-gray-200 p-4 text-[12px] text-gray-400">문서를 선택하세요.</div>
                  ) : (
                    <>
                      {!!crits.length && (
                        <div className="mb-2 rounded border border-gray-200 bg-gray-50 p-2.5">
                          <div className="text-[12px] font-semibold text-gray-900">확인 항목 — 맞으면 예, 틀리면 아니오</div>
                          <div className="mt-0.5 text-[10px] text-gray-500">
                            가정이 틀리면 결과가 통째로 바뀝니다. 항목별로 판정해 주세요.
                          </div>
                          <ul className="mt-1.5 space-y-1">
                            {crits.map((c2) => (
                              <li key={c2.id} className="flex flex-wrap items-start gap-1.5">
                                <span className="flex shrink-0 gap-1">
                                  <button onClick={() => judge(c2.id, c2.state === "ok" ? "pending" : "ok")}
                                    className={`rounded px-1.5 py-0.5 text-[11px] ${c2.state === "ok" ? "bg-emerald-600 text-white" : "bg-gray-200 text-gray-600"}`}>예</button>
                                  <button onClick={() => judge(c2.id, c2.state === "ng" ? "pending" : "ng")}
                                    className={`rounded px-1.5 py-0.5 text-[11px] ${c2.state === "ng" ? "bg-red-600 text-white" : "bg-gray-200 text-gray-600"}`}>아니오</button>
                                </span>
                                <span className={`min-w-0 flex-1 text-[12px] ${c2.state === "ng" ? "text-red-700 line-through" : "text-gray-800"}`}>{c2.text}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <button onClick={makeMockup} disabled={making}
                          className="rounded bg-gray-900 px-2.5 py-1 text-[11px] text-white disabled:opacity-50">
                          {making ? "생성 중…" : "이 설계로 목업 만들기"}
                        </button>
                        <span className="min-w-0 flex-1 text-[11px] text-gray-600">{mockMsg}</span>
                      </div>
                      <div className="max-h-[720px] w-full min-w-0 overflow-auto rounded border border-gray-200 p-3">
                        <Md text={docBody.deliverable || ""} />
                      </div>
                    </>
                  )}
                </div>
              </div>
            );
          })()}

          {tab === "tree" && (
            <>
              <div className="mt-2.5 flex flex-wrap gap-1">
                {areas.map((a) => (
                  <button
                    key={a.area}
                    onClick={() => { setArea(a.area); setMod(""); }}
                    className={`rounded px-2 py-1 text-[11px] ${curArea?.area === a.area ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-700"}`}
                  >{a.area} <span className="opacity-60">{a.files}</span></button>
                ))}
              </div>

              {/* 좁은 화면: 세로 스택 / 넓은 화면: 모듈 목록 + 상세 2열 */}
              <div className="mt-2.5 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
                <div className="max-h-[420px] w-full min-w-0 overflow-y-auto rounded border border-gray-200">
                  {mods.map((m) => (
                    <button
                      key={m.name} onClick={() => setMod(m.name)}
                      className={`flex w-full items-center gap-2 border-b border-gray-100 px-2.5 py-1.5 text-left text-[12px] last:border-0 ${curMod?.name === m.name ? "bg-gray-100 font-semibold" : ""}`}
                    >
                      <span className="min-w-0 flex-1 truncate text-gray-800">{m.name}</span>
                      <span className="ml-auto shrink-0 text-[10px] text-gray-400">{m.files}개 · {m.lines.toLocaleString()}줄</span>
                    </button>
                  ))}
                  {!mods.length && <div className="p-3 text-[11px] text-gray-400">검색 결과 없음</div>}
                </div>

                <div className="max-h-[420px] w-full min-w-0 overflow-auto rounded border border-gray-200">
                  {files.map((f) => (
                    <div key={f.path} className="border-b border-gray-100 px-2.5 py-1.5 last:border-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${KIND_COLOR[f.kind] || "bg-gray-100 text-gray-600"}`}>
                          {KIND_LABEL[f.kind] || f.kind}
                        </span>
                        <span className="break-all text-[12px] text-gray-900">{f.path}</span>
                        <span className="ml-auto shrink-0 text-[10px] text-gray-400">{f.lines}줄</span>
                      </div>
                      {!!f.symbols.length && (
                        <div className="mt-0.5 break-all text-[11px] text-gray-500">{f.symbols.join(", ")}</div>
                      )}
                    </div>
                  ))}
                  {!files.length && <div className="p-3 text-[11px] text-gray-400">파일 없음</div>}
                </div>
              </div>
            </>
          )}

          {tab === "api" && (
            <div className="mt-2.5 max-h-[480px] w-full min-w-0 overflow-auto rounded border border-gray-200">
              {comp.apis
                .filter((a) => !q.trim() || a.path.toLowerCase().includes(q.toLowerCase()) || a.handlers.some((h) => h.toLowerCase().includes(q.toLowerCase())))
                .map((a) => (
                  <div key={a.path} className="border-b border-gray-100 px-2.5 py-1.5 last:border-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="shrink-0 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] text-blue-700">{a.module}</span>
                      <span className="break-all text-[12px] text-gray-900">{a.path}</span>
                    </div>
                    {!!a.handlers.length && (
                      <div className="mt-0.5 break-all text-[11px] text-gray-500">{a.handlers.join(", ")}</div>
                    )}
                  </div>
                ))}
            </div>
          )}

          {tab === "entity" && (
            <div className="mt-2.5 grid max-h-[480px] grid-cols-2 gap-1 overflow-auto sm:grid-cols-3 lg:grid-cols-5">
              {comp.entities
                .filter((e) => !q.trim() || e.name.toLowerCase().includes(q.toLowerCase()))
                .map((e) => (
                  <div key={e.path} className="rounded border border-gray-200 px-2 py-1.5" title={e.path}>
                    <div className="truncate text-[12px] font-medium text-gray-900">{e.name}</div>
                  </div>
                ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
