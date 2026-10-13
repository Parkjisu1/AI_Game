"use client";

import { useEffect, useState, type FormEvent } from "react";

type Report = { technical_pass: boolean; art_approved: boolean; engine_verified: boolean; issues: string[]; review_required: string[];
  lods: { level: number; triangles: number; bones: number; materials: number; max_influences: number }[]; texture_method: string; rig_method: string };
type Job = { _id: string; title: string; brief: string; profile: string; status: string; stage: string; mode: string; extension?: string;
  artifacts_ready: boolean; created_at: string; error?: string; report?: Report; build_path?: string };
const labels: Record<string, string> = { queued: "대기", running: "제작 중", needs_modeling: "모델링 필요", needs_review: "검수 필요", failed: "실행 실패", interrupted: "중단 확인 필요" };
const stages = ["레퍼런스·예산", "형태·토폴로지", "UV·텍스처", "리깅·동작", "LOD·패키징", "아트·엔진 검수"];
const fileUrl = (id: string, file: string) => `/api/assets-3d/${id}/files/${file}`;

export default function AssetStudio() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  async function refresh() {
    const response = await fetch("/api/assets-3d", { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error("작업 목록을 불러오지 못했습니다.");
    const data = await response.json();
    setJobs(data.jobs || []); setOnline(!!data.worker?.online);
  }
  useEffect(() => {
    let alive = true;
    const load = async () => { try { if (alive) await refresh(); } catch (err) { if (alive) setError(String((err as Error).message)); } };
    void load();
    const timer = setInterval(load, 10000);
    return () => { alive = false; clearInterval(timer); };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    await send(new FormData(form));
  }
  async function send(form: FormData) {
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch("/api/assets-3d", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "작업을 저장하지 못했습니다.");
      setSelected(data.id);
      setNotice(data.status === "needs_modeling" ? "레퍼런스를 저장했습니다. 흰 배경의 정면·후면 A 포즈 이미지를 함께 올리면 자동 초안 제작을 시작합니다." : "제작 대기열에 등록했습니다. 완료 후 품질 검사와 다운로드가 표시됩니다.");
      await refresh();
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  const current = jobs.find(job => job._id === selected) || jobs[0];
  return <div className="space-y-7" style={{ color: "var(--text, #dedede)" }}>
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs tracking-[.2em] opacity-60">PROJECT HUB / ASSET STUDIO</p><h1 className="text-3xl font-semibold mt-2">3D 모델 제작실</h1><p className="mt-2 text-sm opacity-70">레퍼런스에서 게임용 모델 팩까지, 제작과 검수 기록을 한곳에.</p></div>
      <span className="rounded-full border px-3 py-2 text-xs">{online ? "● 제작 워커 연결됨" : "○ 제작 워커 연결 대기"}</span>
    </div>
    <div className="grid grid-cols-2 md:grid-cols-6 gap-2">{stages.map((stage, i) => <div key={stage} className="rounded-lg border p-3"><span className="text-xs opacity-50">0{i+1}</span><p className="text-sm mt-1">{stage}</p></div>)}</div>
    <div className="grid lg:grid-cols-[360px_1fr] gap-6">
      <div className="space-y-5">
        <form onSubmit={submit} className="rounded-xl border p-5 space-y-4">
          <h2 className="font-semibold text-lg">새 제작 요청</h2>
          <label className="block text-sm">이름<input name="title" required maxLength={120} placeholder="바람 검객" className="mt-1 w-full rounded border p-2 bg-transparent" /></label>
          <label className="block text-sm">제작 의도<textarea name="brief" maxLength={6000} rows={4} placeholder="스타일, 장비, 필요한 동작, 목표 게임 화면을 적어 주세요." className="mt-1 w-full rounded border p-2 bg-transparent" /></label>
          <label className="block text-sm">목표<select name="profile" className="mt-1 w-full rounded border p-2 bg-transparent"><option value="pc">PC · LOD0 30,000 tri 목표</option><option value="mobile">모바일 · LOD0 12,000 tri 목표</option></select></label>
          <label className="block text-sm">모델 또는 레퍼런스<input type="file" name="file" required accept=".blend,.glb,.fbx,.obj,.png,.jpg,.jpeg,.webp" className="block mt-2 text-xs w-full" /></label>
          <label className="block text-sm">후면 이미지 · 이미지 제작 시 필요<input type="file" name="back" accept=".png,.jpg,.jpeg,.webp" className="block mt-2 text-xs w-full" /></label>
          <p className="text-xs opacity-65 leading-relaxed">합계 100MB 이하. 이미지 제작은 흰 배경·전신·같은 A 포즈의 정면과 후면을 사용합니다. 형태 생성 → 표면 정리 → UV·텍스처 베이크 → 자동 리깅 → LOD·팩을 만들며, 얼굴·손·관절 검수가 필요합니다. 텍스처를 포함한 .blend·GLB 업로드는 기존 재질·리그를 보존합니다.</p>
          <button disabled={busy} className="rounded-lg w-full px-4 py-2.5 font-medium bg-teal-700 text-white disabled:opacity-50">{busy ? "저장 중…" : "제작 요청 등록"}</button>
        </form>
        <div className="rounded-xl border p-5 space-y-3"><h2 className="font-semibold">Wind Ronin 예제</h2>
          <a href="/asset-studio/style-comparison.html" className="block rounded-lg border p-3 text-sm font-medium">원화와 수정본 비교 · 실제 3D 회전·동작·모델 팩</a>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/asset-studio/wind-ronin-sheet.png" alt="야스오의 스타일을 참고한 독자 검객의 정면·측면·후면 제작 레퍼런스" className="rounded-lg w-full" />
          <p className="text-xs opacity-70 leading-relaxed">야스오를 참고한 독자 검객. 레퍼런스 시트는 아트 목표이며, 예제 3D 팩은 제작 흐름 검증용입니다. 최종 퀄리티 승인을 의미하지 않습니다.</p>
          <button disabled={busy} onClick={async () => {
            setBusy(true);setError("");
            try {
              const form = new FormData();form.set("title", "Wind Ronin · 이미지 기반 검객");form.set("profile", "pc");
              form.set("brief", "야스오를 참고한 독자 검객. 얼굴·의상·웨이트·엔진 검수 필요.");
              for (const side of ["front", "back"]) {
                const response = await fetch(`/asset-studio/wind-ronin-${side}.png`);
                if (!response.ok) throw new Error("예제 이미지를 불러오지 못했습니다.");
                form.set(side === "front" ? "file" : "back", new File([await response.blob()], `${side}.png`, { type: "image/png" }));
              }
              await send(form);
            } catch (err) {setError((err as Error).message);setBusy(false);}
          }} className="rounded-lg border w-full p-2 text-sm disabled:opacity-50">레퍼런스로 3D 초안 제작</button>
          <a href="/asset-studio/workflow.md" className="block text-sm underline">제작 기준·조사 출처 보기</a>
        </div>
      </div>
      <div className="space-y-4">
        {error && <p role="alert" className="rounded-lg border border-red-400 p-3 text-sm">{error}</p>}
        {notice && <p role="status" className="rounded-lg border border-teal-500 p-3 text-sm">{notice}</p>}
        <div className="rounded-xl border p-5"><h2 className="font-semibold mb-4">제작 기록</h2>
          {!jobs.length && <p className="text-sm opacity-60">첫 모델을 올리거나 예제 팩을 생성해 주세요.</p>}
          <div className="space-y-2">{jobs.map(job => <button key={job._id} onClick={() => setSelected(job._id)} className={`w-full text-left rounded-lg border p-3 ${current?._id === job._id ? "border-teal-500" : "border-transparent"}`}><div className="flex justify-between gap-3"><span className="text-sm font-medium">{job.title}</span><span className="text-xs shrink-0 opacity-70">{labels[job.status] || job.status}</span></div><p className="text-xs mt-1 opacity-50">{new Date(job.created_at).toLocaleString("ko-KR")} · {job.profile.toUpperCase()}</p></button>)}</div>
        </div>
        {current && <div className="rounded-xl border p-5 space-y-4">
          <div><h2 className="font-semibold text-xl">{current.title}</h2><p className="text-sm opacity-65 mt-1">{current.brief || "제작 흐름 검증 예제"}</p></div>
          {current.status === "needs_modeling" && <><p className="text-sm">레퍼런스를 바탕으로 형태·얼굴·손·의상을 제작해야 합니다. 아직 3D 모델이 만들어지지 않았습니다.</p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={fileUrl(current._id, `input${current.extension}`)} alt="업로드한 제작 레퍼런스" className="max-h-96 rounded-lg object-contain" /></>}
          {current.status === "queued" && <p className="text-sm opacity-70">{current.stage === "waiting_for_build_pc" ? "빌드 컴퓨터의 Unity 작업이 끝나기를 기다립니다." : "빌드 컴퓨터 작업 대기 중입니다."}</p>}
          {current.status === "running" && <p role="status" className="text-sm opacity-70">{current.stage === "image_reconstruction" ? "Mother에서 이미지로 3D 형태를 생성하고 있습니다." : "빌드 컴퓨터에서 메시·텍스처·리깅·모델 팩을 처리하고 있습니다."}</p>}
          {current.error && <pre className="text-xs whitespace-pre-wrap break-words rounded border p-3 max-h-40 overflow-auto">{current.error}</pre>}
          {current.artifacts_ready && <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={fileUrl(current._id, "preview.png")} alt="실제 Blender 렌더 결과" className="w-full max-h-[560px] object-contain rounded-lg bg-slate-200" />
            <div className="flex flex-wrap gap-2"><a className="rounded-lg bg-teal-700 text-white px-4 py-2 text-sm" href={fileUrl(current._id,"model-pack.zip")}>모델 팩 ZIP 다운로드</a><a className="rounded-lg border px-4 py-2 text-sm" href={fileUrl(current._id,"character_LOD0.glb")}>GLB</a><a className="rounded-lg border px-4 py-2 text-sm" href={fileUrl(current._id,"report.json")}>검사 보고서</a><a className="rounded-lg border px-4 py-2 text-sm" href={fileUrl(current._id,"research.json")}>참고 지식</a></div>
          </>}
          {current.report && <>
            <p className="text-sm">기술 검사: {current.report.technical_pass ? "통과" : "수정 필요"} · 아트 검수: {current.report.art_approved ? "승인" : "필요"} · 엔진 검증: {current.report.engine_verified ? "완료" : "미실시"}</p>
            <table className="w-full text-sm text-left"><thead><tr><th className="p-2">LOD</th><th>삼각형</th><th>본</th><th>재질</th></tr></thead><tbody>{current.report.lods.map(lod => <tr key={lod.level} className="border-t"><td className="p-2">LOD{lod.level}</td><td>{lod.triangles.toLocaleString()}</td><td>{lod.bones}</td><td>{lod.materials}</td></tr>)}</tbody></table>
            {!!current.report.issues.length && <ul className="list-disc pl-5 text-sm space-y-1">{current.report.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
            <details className="text-sm"><summary className="cursor-pointer">남은 품질 검수</summary><ul className="list-disc pl-5 mt-2 space-y-1">{current.report.review_required.map(item => <li key={item}>{item}</li>)}</ul><p className="text-xs opacity-60 mt-3">{current.report.texture_method}<br />{current.report.rig_method}</p></details>
          </>}
        </div>}
      </div>
    </div>
  </div>;
}
