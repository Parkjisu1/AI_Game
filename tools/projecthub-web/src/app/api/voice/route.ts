import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { getDb } from "@/lib/mongodb";
import { sendDmToEmail, buildMeetingSummaryPayload } from "@/lib/slack";
import fs from "fs";
import path from "path";

// 파일 업로드(multipart) + 외부 STT/LLM 호출 → Node 런타임 + 충분한 타임아웃 필요.
// 긴 회의(20~40분) STT 전사 + gpt-4o 분석은 60s를 쉽게 넘김 → 300s로 상향.
export const runtime = "nodejs";
export const maxDuration = 300;

// OpenAI 오디오 API의 실제 상한은 요청 본문 26,214,400 bytes (실측: 초과 시 413
// "Maximum content size limit (26214400) exceeded"). multipart 오버헤드 여유를 두고 차단한다.
const STT_MAX_BYTES = 25_000_000;

// 실측(2026-07-21)으로 확인된 STT 모델별 한계 — 이 값이 이 파일의 모든 분기 근거다.
//   gpt-4o-mini-transcribe : 23분 OK / 24분부터 HTTP 400 input_too_large
//                            ("Total number of tokens in instructions + audio is too large")
//                            → 용량과 무관한 '길이' 상한. 폰 녹음은 0.5~1MB/분이라
//                              용량 가드(25MB)에 걸리기 한참 전에 이쪽이 먼저 터진다.
//   whisper-1              : 길이 상한 없음. 45분/20.6MB까지 정상, 25MB 초과 시에만 413.
// 따라서 짧으면 품질 좋은 gpt-4o-mini-transcribe, 길이 초과면 whisper-1로 폴백한다.
const STT_PRIMARY = "gpt-4o-mini-transcribe";
const STT_FALLBACK = "whisper-1";

// 통합 음성 처리 — STT 후 AI가 스스로 분류:
//   kind="query"   → 코드/기능 상태 질문: DNA graph.json(실제코드) 근거로만 답 (거짓없음)
//   kind="meeting" → 회의/업무 지시: 요약 + task 분해 + meeting_transcripts 영구저장
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";

// STT 바이어스 힌트 — 팀원 이름·약어·도메인 용어를 미리 알려 전사 오인(상점→승점, 임우현→이모현,
// 10배수→시배수, PR/tier 깨짐, hue게이팅→휴베이팅)을 줄인다. 팀/용어 변경 시 이 상수만 갱신.
// gpt-4o-mini-transcribe의 prompt 파라미터로 전달.
const STT_PROMPT =
  "BalloonFlow 팀 회의. 팀원: 박지수(지수), 임우현(우현), 신다희(다희), 오동한(동한), 형철, 임형철. " +
  "용어: 상점, 번들, 티어(tier), 상품, 스토어 빌드, 배포, 스모크 테스트, QA, 프리팹, PR, " +
  "레일, 다트, 기믹, 큐, 10배수, 색상 일치, hue 게이팅, 양자화, 픽셀포지, 헤르메스, MCP, 유니티 에디터, " +
  "레벨, 밸런스, 마일스톤, 모션, 리니어.";

interface GNode { cls: string; system: string; refsIn: number; refsOut: number; }
function loadGraph(): { nodes: GNode[]; systems?: { name: string; count: number }[] } | null {
  try { return JSON.parse(fs.readFileSync(path.join(process.cwd(), "public", "balloonflow-graph.json"), "utf-8")); }
  catch { return null; }
}

const SYS = `당신은 BalloonFlow 팀의 음성 비서다. 사용자 발화를 듣고 **스스로 분류**해 처리한다.

1) 분류 kind:
   - "query": 어떤 기능/코드가 구현됐는지·되는지·있는지 등을 **묻는** 경우.
   - "meeting": 회의 내용 정리거나 해야 할 업무 지시인 경우.

2) kind="query"면 — 아래 [코드 인덱스](실제 코드 추출, 거짓 없음)에 **근거해서만**:
   - status: "implemented"|"partial"|"not_found" (인덱스에 없으면 지어내지 말고 "not_found")
   - answer(한국어), evidence(["ClassName (system)", ...] 실제 존재하는 것만)
   - 정적 구조만 본다 → answer에 "런타임 동작은 정적분석으로 확인 불가(빌드/플레이 필요)" 1줄 포함
   - suggestions: 후속작업 0~3개 [{title,description}]

3) kind="meeting"이면 — 회의록을 **빠짐없이 구조화**한다 (발화에 근거, 추측 금지, 누락 없이):
   - summary: 안건별 **상세** 요약. 각 안건마다 핵심 논의·결정·배경/수치/트레이드오프를 모두 보존.
     길이 제한 없음, 마크다운 불릿(•) 사용. "3~6줄" 같은 압축 금지 — 20분 회의면 그만큼 길게.
   - **decisions와 tasks를 반드시 분리한다**:
     · decision = 회의에서 **내려진/합의된 결론·방침** (예: "빌드 오늘 16시 배포 결정", "필드기믹은 화~수 확인 후 판단").
       summary에 녹이지 말고 decisions 배열에 **분리 명시**. 명시적 결정이 없으면 [].
     · task = **누가 실행해야 하는 액션** (예: "필드기믹 AI 가능여부 확인", "빌드 배포 실행").
     · **같은 사안이 decisions와 tasks 양쪽에 동시에 나올 수 있다(중복 OK·권장)**. "하기로 함"이라는 결론은 decisions에, 그 실행은 tasks에 각각 둔다.
       예) "빌드를 오늘 16시 배포하기로 함" → decisions 1건 **AND** tasks "빌드 배포 실행" 1건.
       예) "색상일치+10배수를 프롬프트로 개선하기로 함" → decisions 1건 **AND** tasks 1건.
       결정을 summary에만 녹이거나, task로만 빼는 것 둘 다 금지.
   - decisions: [{decision, context}]
   - tasks: **모든** 실행 가능한 업무 (계획·서술·예외처리에 묻힌 것까지 빠짐없이)
     [{title, description, team:"dev"|"art"|"design"|"chat",
       owner(언급된 담당자를 **발화 그대로** 예:"형철님", 없으면 빈 문자열 "" — "unknown"/추측 금지),
       due(기한을 **발화에 나온 표현 그대로** 예:"화~수","오늘 16시","이번 주". **달력 날짜(2026-..)로 변환·추측 절대 금지**. 없으면 ""),
       priority:"high"|"medium"|"low"}]
   - open_questions: 미결·확인 필요 항목 [문자열]
   - risks: 언급된 리스크/주의사항 [문자열]
   team 분류 정확히: art=이미지/색상/아트 생성, design=기획/레벨/밸런스/프롬프트 엔지니어링,
   dev=엔지니어링/코드/빌드/광고SDK/기믹 처리, chat=단순 공유.

**출력 전 최종 자가점검 (필수)**:
   - 각 decision이 실행을 수반하면(배포/릴리즈/수정/생성/적용 등) 대응하는 task가 tasks에 반드시 있는가?
     예: "16시 빌드 배포 확정" 결정 → "빌드 배포 실행" task가 있어야 함. 없으면 추가하라.
   - 색상/스프라이트/아이콘/이미지 관련은 art, 레벨/밸런스/기획은 design으로 분류했는가(무조건 dev로 몰지 말 것)?

반드시 JSON만: {"kind":"query|meeting","answer":"","status":"","evidence":[],"suggestions":[],"summary":"","decisions":[],"tasks":[],"open_questions":[],"risks":[]}`;

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!OPENAI_API_KEY) return NextResponse.json({ error: "서버에 OPENAI_API_KEY 미설정" }, { status: 500 });

  const ctype = req.headers.get("content-type") || "";
  const clen = req.headers.get("content-length") || "?";
  let audio: File | null = null;
  try {
    const form = await req.formData();
    audio = form.get("audio") as File | null;
  } catch (e) {
    const msg = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
    console.error("[voice] formData parse failed:", msg, "| content-type:", ctype, "| content-length:", clen);
    // 이 경로의 실제 원인은 거의 항상 "body가 상한에서 잘려 multipart가 깨진 것"이다.
    // (next.config.ts experimental.proxyClientMaxBodySize 참조 — 기본 10MB에서 잘렸었다.)
    // "form 파싱 실패"만 띄우면 사용자가 무엇을 해야 할지 알 수 없으므로 크기를 근거로 안내한다.
    const n = Number(clen);
    const tooBig = Number.isFinite(n) && n > STT_MAX_BYTES;
    return NextResponse.json({
      error: tooBig
        ? `녹음 파일이 상한(25MB)을 넘어 업로드가 잘렸습니다 (${(n / 1024 / 1024).toFixed(1)}MB). 회의를 나눠 녹음해 주세요.`
        : "업로드가 중간에 끊겨 form 파싱에 실패했습니다 — 네트워크 상태 확인 후 재시도해 주세요.",
      detail: msg, ctype, clen,
    }, { status: tooBig ? 413 : 400 });
  }
  if (!audio) return NextResponse.json({ error: "오디오 없음 (audio 필드 비어있음)", ctype, clen }, { status: 400 });

  // 단계별 로그 — 실패 시 journalctl로 어느 구간에서 끊겼는지 특정 가능해야 한다.
  // (이전엔 로그가 없어 "요약이 안 된다"는 신고를 서버에서 재현·추적할 수 없었음)
  const t0 = Date.now();
  const who = (session.user.email || "").toLowerCase();
  console.log(`[voice] start user=${who} file=${(audio as File).name} size=${audio.size} type=${audio.type}`);

  if (audio.size > STT_MAX_BYTES) {
    const mb = (audio.size / 1024 / 1024).toFixed(1);
    console.error(`[voice] REJECTED oversize size=${audio.size}`);
    return NextResponse.json({
      error: `녹음 파일이 너무 큽니다 (${mb}MB, 상한 25MB). 회의를 나눠 녹음하거나, 긴 구간은 파일 업로드로 나눠서 올려주세요.`,
    }, { status: 413 });
  }

  // 1) STT — primary 실패(길이 초과) 시 fallback 모델로 자동 재시도.
  //    fetch를 try로 감싼다: 이전엔 감싸지 않아 undici 타임아웃(UND_ERR_HEADERS_TIMEOUT,
  //    기본 300s) 발생 시 핸들러 전체가 500으로 죽고 로그도 DB 기록도 남지 않았다.
  async function transcribe(model: string): Promise<{ ok: true; text: string } | { ok: false; status: number; detail: string }> {
    const f = new FormData();
    f.append("file", audio as File, (audio as File).name || "audio.webm");
    f.append("model", model);
    f.append("language", "ko");
    f.append("prompt", STT_PROMPT);
    try {
      const res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
        method: "POST", headers: { Authorization: `Bearer ${OPENAI_API_KEY}` }, body: f,
      });
      if (!res.ok) return { ok: false, status: res.status, detail: (await res.text()).slice(0, 300) };
      return { ok: true, text: ((await res.json()).text || "").trim() };
    } catch (e) {
      const msg = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
      return { ok: false, status: 0, detail: `네트워크/타임아웃 — ${msg}` };
    }
  }

  // 대용량 업로드는 간헐적으로 전송이 끊긴다(실측: 30·45분은 성공했으나 24분에서 1회 fetch failed).
  // 네트워크성 실패(status 0)에 한해 1회 재시도한다. HTTP 오류는 재시도해도 같으므로 제외.
  async function transcribeWithRetry(model: string) {
    const first = await transcribe(model);
    if (first.ok || first.status !== 0) return first;
    console.warn(`[voice] STT ${model} 네트워크 실패 → 1회 재시도: ${first.detail}`);
    return transcribe(model);
  }

  let sttModel = STT_PRIMARY;
  let stt = await transcribeWithRetry(STT_PRIMARY);
  // 길이 초과(input_too_large)는 파일을 줄여도 해결되지 않고 모델 교체로만 해결된다.
  if (!stt.ok && /input_too_large|too large for this model/i.test(stt.detail)) {
    console.warn(`[voice] STT primary 길이초과 → ${STT_FALLBACK} 폴백 (size=${audio.size})`);
    sttModel = STT_FALLBACK;
    stt = await transcribeWithRetry(STT_FALLBACK);
  }
  if (!stt.ok) {
    const hint = /maximum content size|413/i.test(stt.detail) || stt.status === 413
      ? "녹음 파일이 상한(25MB)을 넘었습니다 — 회의를 나눠 녹음해 주세요."
      : stt.status === 0
        ? "전사 서버 응답 지연 — 잠시 후 재시도."
        : "전사 서버 오류 — 잠시 후 재시도.";
    console.error(`[voice] STT FAILED model=${sttModel} http=${stt.status} size=${audio.size} detail=${stt.detail}`);
    return NextResponse.json({ error: `STT 실패 (${hint})`, detail: stt.detail }, { status: 502 });
  }
  const transcript: string = stt.text;
  console.log(`[voice] STT ok model=${sttModel} chars=${transcript.length} elapsed=${Date.now() - t0}ms`);
  if (!transcript) {
    console.error("[voice] STT returned empty text — 무음/마이크 미입력 의심");
    return NextResponse.json({ kind: "meeting", transcript: "", summary: "(전사 결과 없음)", tasks: [] });
  }

  // 2) 코드 인덱스 (query 근거용 — 항상 제공해 자동분류 + 답변)
  const graph = loadGraph();
  const index = graph?.nodes
    ? graph.nodes.slice().sort((a, b) => (b.refsIn || 0) - (a.refsIn || 0)).map((n) => `${n.cls} [${n.system}] in=${n.refsIn} out=${n.refsOut}`).join("\n")
    : "(코드 인덱스 없음)";
  const sysLine = (graph?.systems || []).map((s) => `${s.name}(${s.count})`).join(", ");

  // 3) 분류 + 처리
  interface MTask { title: string; description: string; team?: string; owner?: string; due?: string; priority?: string }
  interface MDecision { decision: string; context?: string }

  // 긴 전사는 구간 분할 후 병합한다(map-reduce).
  // 실측(2026-07-21, 69분·20,675자 회의록): 통째로 넣으면 tasks 5 / decisions 2 / 요약 278자로
  // 대부분 누락되지만, 4,000자 구간으로 나누면 tasks 29 / decisions 17 / 요약 2,161자를 회수한다.
  // 원인은 컨텍스트 한계가 아니라(입력 14,957토큰 중 출력 606토큰만 사용) 긴 입력에서 모델이
  // 공격적으로 압축하는 성향이다. 따라서 상한을 늘리는 것으로는 해결되지 않는다.
  const CHUNK_CHARS = 4000;
  const CHUNK_OVERLAP = 300;   // 구간 경계에 걸친 항목 유실 방지 (중복은 아래에서 제거)
  const CHUNK_THRESHOLD = 6000; // 이보다 짧으면 단일 호출이 더 정확하고 빠르다

  // 제목 기준 중복 제거 — 구간 겹침·재언급으로 같은 업무가 여러 번 잡힌다.
  // 사람이 화면에서 취사선택하므로, 놓치는 쪽이 더 해롭다 → 임계값을 높게(0.8) 잡아 보수적으로만 제거.
  const words = (s: string) => new Set(String(s).toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/).filter(Boolean));
  const similar = (a: string, b: string) => {
    const A = words(a), B = words(b);
    if (!A.size || !B.size) return false;
    let inter = 0;
    for (const w of A) if (B.has(w)) inter++;
    return inter / new Set([...A, ...B]).size >= 0.8;
  };
  const dedupe = <T,>(items: T[], key: (t: T) => string): T[] => {
    const kept: T[] = [];
    for (const it of items) if (!kept.some((k) => similar(key(k), key(it)))) kept.push(it);
    return kept;
  };
  let out = {
    kind: "meeting", answer: "", status: "not_found", evidence: [] as string[],
    suggestions: [] as { title: string; description: string }[],
    summary: "", decisions: [] as MDecision[], tasks: [] as MTask[],
    open_questions: [] as string[], risks: [] as string[],
  };
  // 분석 실패 사유를 사용자에게 그대로 전달 — 이전엔 원인 불문 "(분석 실패)" 한 줄이라
  // 요약이 왜 비었는지 알 수 없었다. 아래 3가지를 각각 구분해 표면화한다.
  let analysisError: string | null = null;

  const norm = (v: unknown) => String(v || "");
  const asObjArr = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v as Record<string, unknown>[] : []);
  const asStrArr = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);
  const toTasks = (v: unknown): MTask[] => asObjArr(v).map((t) => ({
    title: norm(t?.title), description: norm(t?.description),
    team: ["dev", "art", "design", "chat"].includes(String(t?.team)) ? String(t?.team) : "dev",
    owner: norm(t?.owner), due: norm(t?.due),
    priority: ["high", "medium", "low"].includes(String(t?.priority)) ? String(t?.priority) : "medium",
  })).filter((t) => t.title);
  const toDecisions = (v: unknown): MDecision[] =>
    asObjArr(v).map((d) => ({ decision: norm(d?.decision), context: norm(d?.context) })).filter((d) => d.decision);

  // 단일 분석 호출 — 실패 종류를 구분해 analysisError에 남기고 throw한다.
  async function analyze(userContent: string, maxTok: number): Promise<Record<string, unknown>> {
    const aRes = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        // 회의 요약 품질 위해 gpt-4o (긴 회의록 + 상세 구조화). query 근거 답변도 더 정확.
        model: "gpt-4o",
        messages: [{ role: "system", content: SYS }, { role: "user", content: userContent }],
        temperature: 0.2,
        // 명시하지 않으면 모델 기본 상한에 의존해 잘림 시점이 불투명해진다. 상한을 고정하고
        // 잘렸을 때(finish_reason=length)를 아래에서 명시적으로 잡는다.
        max_tokens: maxTok,
        response_format: { type: "json_object" },
      }),
    });
    // ① HTTP 실패(429/500 등)를 검사하지 않으면 choices가 없어 "{}"로 파싱되고,
    //    요약·task가 조용히 빈 채로 성공처럼 반환된다 (에러 표시조차 안 됨).
    if (!aRes.ok) {
      const detail = (await aRes.text()).slice(0, 300);
      analysisError = `분석 API 오류 (HTTP ${aRes.status}) — 잠시 후 재시도`;
      console.error(`[voice] ANALYSIS HTTP ${aRes.status} detail=${detail}`);
      throw new Error(analysisError);
    }
    const aJson = await aRes.json();
    const choice = aJson.choices?.[0];
    const content: string = choice?.message?.content || "";
    // ② 출력이 상한에서 잘리면 JSON이 깨진다 → 원인을 명확히 알린다.
    if (choice?.finish_reason === "length") {
      analysisError = "회의가 너무 길어 요약이 중간에 잘렸습니다 — 회의를 나눠서 분석해 주세요";
      console.error(`[voice] ANALYSIS TRUNCATED completion_tokens=${aJson.usage?.completion_tokens} transcript_chars=${transcript.length}`);
      throw new Error(analysisError);
    }
    if (!content) {
      analysisError = "분석 응답이 비었습니다 — 잠시 후 재시도";
      console.error(`[voice] ANALYSIS EMPTY CONTENT finish_reason=${choice?.finish_reason}`);
      throw new Error(analysisError);
    }
    return JSON.parse(content);
  }

  try {
    if (transcript.length > CHUNK_THRESHOLD) {
      // 긴 발화는 회의로 확정한다 (질문형 발화는 짧다) → 구간 분할 병렬 추출 후 병합.
      const chunks: string[] = [];
      for (let i = 0; i < transcript.length; i += CHUNK_CHARS - CHUNK_OVERLAP) chunks.push(transcript.slice(i, i + CHUNK_CHARS));
      const results = await Promise.all(chunks.map((c, i) =>
        analyze(`발화(회의 ${i + 1}/${chunks.length} 구간): ${c}`, 4000)
          .catch((e) => { console.error(`[voice] chunk ${i + 1}/${chunks.length} 실패: ${e instanceof Error ? e.message : String(e)}`); return null; })
      ));
      const okResults = results.filter((r): r is Record<string, unknown> => r !== null);
      if (!okResults.length) throw new Error(analysisError || "모든 구간 분석 실패");

      out = {
        kind: "meeting", answer: "", status: "not_found", evidence: [], suggestions: [],
        summary: okResults.map((p) => norm(p.summary)).filter(Boolean).join("\n"),
        decisions: dedupe(okResults.flatMap((p) => toDecisions(p.decisions)), (d) => d.decision).slice(0, 40),
        tasks: dedupe(okResults.flatMap((p) => toTasks(p.tasks)), (t) => t.title).slice(0, 50),
        open_questions: dedupe(okResults.flatMap((p) => asStrArr(p.open_questions)), (s) => s).slice(0, 25),
        risks: dedupe(okResults.flatMap((p) => asStrArr(p.risks)), (s) => s).slice(0, 25),
      };
      // 일부 구간만 실패하면 결과는 주되, 누락 가능성을 반드시 알린다 (조용한 유실 금지).
      if (okResults.length < chunks.length) {
        analysisError = `${chunks.length}개 구간 중 ${chunks.length - okResults.length}개 분석 실패 — 일부 내용이 빠졌을 수 있습니다`;
      }
      console.log(`[voice] chunked analysis chunks=${chunks.length} ok=${okResults.length} transcript=${transcript.length}자`);
    } else {
      const p = await analyze(
        `발화: ${transcript}\n\n[시스템]: ${sysLine}\n\n[코드 인덱스] (총 ${graph?.nodes?.length || 0}개):\n${index.slice(0, 20000)}`,
        16000,
      );
      out = {
        kind: p.kind === "query" ? "query" : "meeting",
        answer: norm(p.answer),
        status: ["implemented", "partial", "not_found"].includes(String(p.status)) ? String(p.status) : "not_found",
        evidence: asStrArr(p.evidence).slice(0, 12),
        suggestions: asObjArr(p.suggestions).slice(0, 5).map((s) => ({ title: norm(s?.title), description: norm(s?.description) })),
        summary: norm(p.summary),
        decisions: toDecisions(p.decisions).slice(0, 15),
        tasks: toTasks(p.tasks).slice(0, 30),
        open_questions: asStrArr(p.open_questions).slice(0, 12),
        risks: asStrArr(p.risks).slice(0, 12),
      };
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (!analysisError) {
      // JSON.parse 실패 등 예상 밖 경로 — 원문 일부를 로그에 남겨 추적 가능하게 한다.
      analysisError = `분석 결과 해석 실패 (${msg.slice(0, 120)})`;
      console.error(`[voice] ANALYSIS PARSE FAILED: ${msg}`);
    }
    out.summary = `(분석 실패 — ${analysisError})`;
  }
  console.log(`[voice] analysis kind=${out.kind} summary=${out.summary.length}자 decisions=${out.decisions.length} tasks=${out.tasks.length} err=${analysisError ?? "none"} elapsed=${Date.now() - t0}ms`);

  // 4) meeting이면 영구 저장 + 녹음자(로그인 사용자)에게 Slack 요약 DM
  //    (현재: 테스트로 본인에게. 추후 팀 채널 전송으로 바꾸려면 resolveRouteByEmail 대신 채널 webhook 사용)
  let meetingId: string | null = null;
  let slackSent: { ok: boolean; error?: string } | null = null;
  if (out.kind === "meeting") {
    try {
      const db = await getDb();
      const res = await db.collection("meeting_transcripts").insertOne({
        transcript, summary: out.summary, tasks: out.tasks,
        decisions: out.decisions, open_questions: out.open_questions, risks: out.risks,
        created_by_email: (session.user.email || "").toLowerCase(),
        created_at: new Date().toISOString(),
      });
      meetingId = String(res.insertedId);
    } catch (e) {
      // 저장 실패해도 결과는 반환하되, 이유는 반드시 남긴다 (이전엔 완전 무시라 추적 불가).
      console.error(`[voice] MONGO INSERT FAILED: ${e instanceof Error ? `${e.name}: ${e.message}` : String(e)}`);
    }

    try {
      slackSent = await sendDmToEmail(
        session.user.email || "",
        buildMeetingSummaryPayload(out),
      );
    } catch (e) {
      slackSent = { ok: false, error: e instanceof Error ? e.message : "send failed" };
    }
  }

  console.log(`[voice] done meetingId=${meetingId} slack=${slackSent?.ok ?? "n/a"} total=${Date.now() - t0}ms`);
  // analysisError를 클라이언트로 전달 → 화면에 정확한 사유 표시 (요약이 빈 이유를 알 수 있게)
  return NextResponse.json({ transcript, meetingId, slackSent, analysisError, ...out });
}
