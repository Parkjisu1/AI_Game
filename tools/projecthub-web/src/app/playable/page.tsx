"use client";
import { useEffect, useMemo, useState } from "react";
import JSZip from "jszip";

/**
 * CrewFlow 플레이어블 광고 생성기.
 *
 * ── 어떻게 도는가 ───────────────────────────────────────────────────────────
 * 유니티 빌드는 <b>레벨과 무관</b>하다. 레벨은 JSON 한 장(최대 18KB)이라
 * 빌드 1벌 + 레벨 300장으로 300종을 즉시 만든다. 레벨마다 빌드하면 한 편에 수 분이 들고
 * 서버에 유니티가 있어야 한다 — 성립하지 않는다.
 *
 * ── 미리보기와 다운로드가 다른 이유 ─────────────────────────────────────────
 * 미리보기: `/playable/index.html?level=NNN` 을 iframe 으로. 레벨을 fetch 로 채운다.
 * 다운로드: 레벨을 index.html 에 <b>박아</b> zip 을 만든다 — 광고망은 런타임 네트워크 요청을
 *           금지하므로 제출본은 파일만으로 자족해야 한다.
 *
 * zip 조립을 <b>브라우저</b>에서 하는 이유: Vercel 서버리스 응답 상한이 4.5MB 인데
 * 번들이 4.65MB 다. 서버로 보내면 상한에 걸린다. 클라이언트에서 만들면 서버 연산도 0이다.
 */

interface Level {
  id: number;
  cubes: number;
  cols: number;
  rows: number;
  colors: number;
  holders: number;
  queueColumns: number;
  bytes: number;
  estimatedSeconds: number;
}

const BASE = "/playable";

function fmtSec(s: number) {
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}분 ${s % 60}초` : `${s}초`;
}

export default function PlayablePage() {
  const [levels, setLevels] = useState<Level[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"id" | "cubes">("id");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/playable/levels")
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.message || d.error); return; }
        setLevels(d.levels);
        setSel(d.levels[0]?.id ?? null);
      })
      .catch(e => setError(String(e)));
  }, []);

  const shown = useMemo(() => {
    let out = levels;
    const n = parseInt(q, 10);
    if (q.trim()) {
      out = Number.isFinite(n)
        ? out.filter(l => String(l.id).includes(q.trim()))
        : out;
    }
    return [...out].sort((a, b) => (sort === "id" ? a.id - b.id : a.cubes - b.cubes));
  }, [levels, q, sort]);

  const current = levels.find(l => l.id === sel) || null;

  /**
   * 제출용 zip 을 브라우저에서 조립한다.
   *
   * 미리보기 index.html 에는 `?level=` 을 받아 fetch 하는 코드가 들어 있다.
   * 제출본에는 그게 있으면 안 되므로 <b>그 블록을 들어내고</b> 레벨을 문자열로 박는다.
   *
   * 잘라내는 자리는 pack.js 가 <b>주석으로 표시해</b> 둔다
   * (`CREW_PREVIEW_HOOK_BEGIN` ‥ `CREW_PREVIEW_HOOK_END`). 예전에는 코드 모양을 정규식으로
   * 맞혀서 들어냈는데, pack.js 를 조금만 손봐도 조용히 안 맞는다 — 그러면 <b>fetch 가 남은
   * 제출본</b>이 만들어지고, 그건 심사에서 떨어지는 게 아니라 <b>기기에서 빈 화면</b>이 된다.
   * 표시를 못 찾으면 zip 을 만들지 않고 실패시킨다.
   */
  async function download() {
    if (!current) return;
    setBusy(true);
    setNote(null);
    try {
      const id = String(current.id).padStart(3, "0");
      const [htmlRes, lvRes] = await Promise.all([
        fetch(`${BASE}/index.html`),
        fetch(`${BASE}/levels/Lv${id}.json`),
      ]);
      if (!htmlRes.ok || !lvRes.ok) throw new Error("자산을 못 받았다 (sync-playable 을 돌렸는지 확인)");

      let html = await htmlRes.text();
      const levelText = await lvRes.text();

      // ① 미리보기용 fetch 훅 제거 — 제출본에 남으면 규격 위반이다.
      const b = html.indexOf("/*CREW_PREVIEW_HOOK_BEGIN*/");
      const e = html.indexOf("/*CREW_PREVIEW_HOOK_END*/");
      if (b < 0 || e < 0 || e < b) {
        throw new Error("미리보기 훅 표시를 못 찾았다 — pack.js 와 배포본 버전이 어긋났다");
      }
      html = html.slice(0, b) + "Promise.resolve()" + html.slice(e + "/*CREW_PREVIEW_HOOK_END*/".length);

      // ② 레벨을 박는다. </script> 가 섞여도 파서가 끊기지 않게 이스케이프.
      const inline = `window.__crewLevel=${JSON.stringify(levelText).replace(/<\//g, "<\\/")};`;
      if (!html.includes("window.CREW_STORE_URL=")) throw new Error("주입 지점(CREW_STORE_URL)을 못 찾았다");
      html = html.replace("window.CREW_STORE_URL=", `${inline}window.CREW_STORE_URL=`);

      // ③ 나머지 3장은 그대로
      const names = ["WebGL.framework.js.unityweb", "WebGL.data.unityweb", "WebGL.wasm.unityweb"];
      const files = await Promise.all(
        names.map(n => fetch(`${BASE}/Build/${n}`).then(r => r.arrayBuffer())),
      );

      const zip = new JSZip();
      zip.file("index.html", html);
      const build = zip.folder("Build")!;
      names.forEach((n, i) => build.file(n, files[i]));

      const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE" });

      // ④ Meta 번들 규격 검사 — 내려받기 <b>전에</b> 한다. 규격을 어긴 파일을 손에 쥐여 주면
      //    광고 매니저에 올려 보고 나서야 알게 된다.
      const mb = blob.size / 1048576;
      const indexMb = new Blob([html]).size / 1048576;
      const fileCount = 1 + names.length;
      const checks: { label: string; ok: boolean; detail: string }[] = [
        { label: "ZIP 총합", ok: mb <= 5, detail: `${mb.toFixed(2)}MB / 5.00MB` },
        { label: "index.html", ok: indexMb <= 2, detail: `${indexMb.toFixed(2)}MB / 2.00MB` },
        { label: "파일 수", ok: fileCount <= 100, detail: `${fileCount} / 100` },
        { label: "루트 index.html", ok: true, detail: "있음" },
        // 유니티 로더가 Build/ 를 <b>상대 경로</b>로 부르는 것은 번들 내부라 허용된다.
        // 금지 대상은 <b>바깥 호스트로 나가는 리소스 로드</b>다.
        //
        // "html 안의 http 문자열"을 세면 안 된다 — 스토어 주소(CTA 폴백)와 유니티 로더의
        // 오류 안내에 박힌 <a href> 가 걸려 멀쩡한 제출본을 막는다. 둘 다 요청이 아니다.
        // 그래서 <b>실제로 요청을 일으키는 자리</b>만 본다.
        {
          label: "외부 요청",
          ok: !/(?:src|<link[^>]*href)\s*=\s*["']https?:|fetch\(\s*["']https?:|importScripts\(\s*["']https?:|new\s+Worker\(\s*["']https?:/i.test(html),
          detail: "없음",
        },
        { label: "레벨 인라인", ok: html.includes("window.__crewLevel="), detail: `Lv${id}` },
        { label: "미리보기 훅", ok: !html.includes("fetch('levels/"), detail: "제거됨" },
        { label: "CTA 브리지", ok: html.includes("CREW_STORE_URL"), detail: "FbPlayableAd 우선" },
      ];
      const failed = checks.filter(c => !c.ok);
      if (failed.length) {
        throw new Error("규격 미달 — " + failed.map(c => `${c.label} ${c.detail}`).join(" · "));
      }

      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `CrewFlow_Lv${id}.zip`;
      a.click();
      URL.revokeObjectURL(a.href);

      setNote(`✓ CrewFlow_Lv${id}.zip — ` + checks.map(c => `${c.label} ${c.detail}`).join(" · "));
    } catch (e) {
      setNote(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <div className="p-8 text-zinc-300">
        <h1 className="text-xl font-bold mb-3">플레이어블</h1>
        <div className="rounded-lg border border-amber-700/40 bg-amber-950/30 p-4 text-sm">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 text-zinc-200">
      <div className="mb-4">
        <h1 className="text-xl font-bold">플레이어블 광고 — Crew Flow</h1>
        <p className="text-sm text-zinc-400 mt-1">
          레벨을 고르면 그 구성 그대로 플레이어블이 만들어진다. 빌드는 하나를 돌려 쓴다.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6">
        {/* 목록 */}
        <div className="min-w-0">
          <div className="flex gap-2 mb-3">
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="레벨 번호"
              className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm"
            />
            <select
              value={sort}
              onChange={e => setSort(e.target.value as "id" | "cubes")}
              className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1.5 text-sm"
            >
              <option value="id">번호순</option>
              <option value="cubes">큐브 적은 순</option>
            </select>
          </div>

          <div className="h-[520px] overflow-y-auto rounded-lg border border-zinc-800 divide-y divide-zinc-800">
            {shown.map(l => (
              <button
                key={l.id}
                onClick={() => setSel(l.id)}
                className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                  l.id === sel ? "bg-emerald-900/30 text-emerald-200" : "hover:bg-zinc-900"
                }`}
              >
                <div className="flex justify-between">
                  <span className="font-medium">Lv{String(l.id).padStart(3, "0")}</span>
                  <span className="text-zinc-500">{l.cols}×{l.rows}</span>
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  큐브 {l.cubes} · 색 {l.colors} · 큐 {l.queueColumns}열 · 약 {fmtSec(l.estimatedSeconds)}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 미리보기 */}
        <div className="min-w-0">
          {current && (
            <>
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <span className="text-sm">
                  <b>Lv{String(current.id).padStart(3, "0")}</b>
                  <span className="text-zinc-500">
                    {" "}· {current.cols}×{current.rows} · 큐브 {current.cubes} · 홀더 {current.holders}
                  </span>
                </span>
                <button
                  onClick={download}
                  disabled={busy}
                  className="ml-auto px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-sm font-medium"
                >
                  {busy ? "만드는 중…" : "제출용 ZIP 내려받기"}
                </button>
              </div>

              {note && (
                <div className="mb-3 text-xs rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2">
                  {note}
                </div>
              )}

              {/* 받아서 바로 눌러 보는 사람이 가장 먼저 부딪히는 벽이라, 내려받기 버튼 <b>옆</b>에 적는다.
                  압축을 풀고 index.html 을 더블클릭하면 유니티 로더가 Build/*.unityweb 를 못 받아
                  로딩 바에서 멈춘다 — 번들이 아니라 브라우저 규칙이다(광고망은 HTTPS 로 서빙한다). */}
              <div className="mb-3 text-xs rounded-lg border border-amber-800/60 bg-amber-950/30 px-3 py-2 text-amber-200/90 max-w-xl leading-relaxed">
                받은 ZIP 은 <b>웹서버로 열어야 한다</b>. 압축을 풀고 <code>index.html</code> 을 더블클릭하면
                (<code>file://</code>) 유니티 WebGL 이 자기 파일을 못 받아 멈춘다 — 번들 문제가 아니라 브라우저
                규칙이고, 메타에 올리면 그쪽이 HTTPS 로 서빙하므로 그대로 돈다. 로컬 확인은 압축 푼 폴더에서{" "}
                <code className="px-1 py-0.5 rounded bg-black/40">npx serve .</code> 로. 그냥 눈으로만 볼
                거면 아래 미리보기가 같은 빌드다.
              </div>

              <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-3 inline-block">
                <iframe
                  key={current.id}
                  src={`${BASE}/index.html?level=${current.id}`}
                  className="block rounded-lg bg-black"
                  style={{ width: 360, height: 640, border: 0 }}
                />
              </div>

              <p className="text-xs text-zinc-500 mt-3 max-w-xl leading-relaxed">
                예상 시간은 레벨끼리 비교하라고 있는 값이다. 가장 작은 레벨도 큐브가 320개라
                광고 길이(15~30초) 안에 <b>클리어되지 않는다</b> — 레벨 선택은 어떤 그림이
                나오느냐를 고르는 것이다. CTA 는 몇 초 뒤 뜨므로 광고로는 성립한다.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
