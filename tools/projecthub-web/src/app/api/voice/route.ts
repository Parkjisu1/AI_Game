import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { getDb } from "@/lib/mongodb";
import { sendDmToEmail, buildMeetingSummaryPayload } from "@/lib/slack";
import fs from "fs";
import path from "path";

// 통합 음성 처리 — STT 후 AI가 스스로 분류:
//   kind="query"   → 코드/기능 상태 질문: DNA graph.json(실제코드) 근거로만 답 (거짓없음)
//   kind="meeting" → 회의/업무 지시: 요약 + task 분해 + meeting_transcripts 영구저장
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";

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

3) kind="meeting"이면:
   - summary: 핵심 3~6줄
   - tasks: 실행 가능한 업무 [{title, description, team:"dev"|"art"|"design"|"chat"}]

반드시 JSON만: {"kind":"query|meeting","answer":"","status":"","evidence":[],"suggestions":[],"summary":"","tasks":[]}`;

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!OPENAI_API_KEY) return NextResponse.json({ error: "서버에 OPENAI_API_KEY 미설정" }, { status: 500 });

  let audio: File | null = null;
  try {
    const form = await req.formData();
    audio = form.get("audio") as File | null;
  } catch {
    return NextResponse.json({ error: "form 파싱 실패" }, { status: 400 });
  }
  if (!audio) return NextResponse.json({ error: "오디오 없음" }, { status: 400 });

  // 1) STT
  const sttForm = new FormData();
  sttForm.append("file", audio, (audio as File).name || "audio.webm");
  sttForm.append("model", "gpt-4o-mini-transcribe");
  sttForm.append("language", "ko");
  const sttRes = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST", headers: { Authorization: `Bearer ${OPENAI_API_KEY}` }, body: sttForm,
  });
  if (!sttRes.ok) return NextResponse.json({ error: "STT 실패", detail: (await sttRes.text()).slice(0, 300) }, { status: 502 });
  const transcript: string = ((await sttRes.json()).text || "").trim();
  if (!transcript) return NextResponse.json({ kind: "meeting", transcript: "", summary: "(전사 결과 없음)", tasks: [] });

  // 2) 코드 인덱스 (query 근거용 — 항상 제공해 자동분류 + 답변)
  const graph = loadGraph();
  const index = graph?.nodes
    ? graph.nodes.slice().sort((a, b) => (b.refsIn || 0) - (a.refsIn || 0)).map((n) => `${n.cls} [${n.system}] in=${n.refsIn} out=${n.refsOut}`).join("\n")
    : "(코드 인덱스 없음)";
  const sysLine = (graph?.systems || []).map((s) => `${s.name}(${s.count})`).join(", ");

  // 3) 분류 + 처리 (단일 호출)
  let out = { kind: "meeting", answer: "", status: "not_found", evidence: [] as string[], suggestions: [] as { title: string; description: string }[], summary: "", tasks: [] as { title: string; description: string; team?: string }[] };
  try {
    const aRes = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: SYS },
          { role: "user", content: `발화: ${transcript}\n\n[시스템]: ${sysLine}\n\n[코드 인덱스] (총 ${graph?.nodes?.length || 0}개):\n${index.slice(0, 20000)}` },
        ],
        temperature: 0.1,
        response_format: { type: "json_object" },
      }),
    });
    const p = JSON.parse((await aRes.json()).choices?.[0]?.message?.content || "{}");
    out = {
      kind: p.kind === "query" ? "query" : "meeting",
      answer: String(p.answer || ""),
      status: ["implemented", "partial", "not_found"].includes(p.status) ? p.status : "not_found",
      evidence: Array.isArray(p.evidence) ? p.evidence.slice(0, 12).map(String) : [],
      suggestions: Array.isArray(p.suggestions) ? p.suggestions.slice(0, 5) : [],
      summary: String(p.summary || ""),
      tasks: Array.isArray(p.tasks) ? p.tasks.slice(0, 20) : [],
    };
  } catch {
    out.summary = "(분석 실패 — 전사만 반환)";
  }

  // 4) meeting이면 영구 저장 + 녹음자(로그인 사용자)에게 Slack 요약 DM
  //    (현재: 테스트로 본인에게. 추후 팀 채널 전송으로 바꾸려면 resolveRouteByEmail 대신 채널 webhook 사용)
  let meetingId: string | null = null;
  let slackSent: { ok: boolean; error?: string } | null = null;
  if (out.kind === "meeting") {
    try {
      const db = await getDb();
      const res = await db.collection("meeting_transcripts").insertOne({
        transcript, summary: out.summary, tasks: out.tasks,
        created_by_email: (session.user.email || "").toLowerCase(),
        created_at: new Date().toISOString(),
      });
      meetingId = String(res.insertedId);
    } catch { /* 저장 실패해도 결과 반환 */ }

    try {
      slackSent = await sendDmToEmail(
        session.user.email || "",
        buildMeetingSummaryPayload(out.summary, out.tasks),
      );
    } catch (e) {
      slackSent = { ok: false, error: e instanceof Error ? e.message : "send failed" };
    }
  }

  return NextResponse.json({ transcript, meetingId, slackSent, ...out });
}
