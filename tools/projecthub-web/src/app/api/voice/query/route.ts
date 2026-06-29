import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import fs from "fs";
import path from "path";

// 음성 상태 질의 — "X 기능 돼/됐어?" → STT → 실제 코드(DNA graph.json) 근거로만 답.
// 거짓 없음: graph에 있는 클래스만 근거로, 없으면 "미구현/확인불가". 런타임 동작은 정적분석 불가 명시.
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";

interface GNode { id: string; cls: string; classes?: string[]; file: string; system: string; refsIn: number; refsOut: number; }
interface Graph { generatedFrom?: string; nodes: GNode[]; systems?: { name: string; count: number }[]; }

function loadGraph(): Graph | null {
  try {
    const p = path.join(process.cwd(), "public", "balloonflow-graph.json");
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch { return null; }
}

const SYS = `당신은 BalloonFlow 코드베이스 분석가다. 아래 [코드 인덱스]는 실제 코드에서 추출한 클래스 목록(DNA graph, 거짓 없음)이다.
사용자 질문에 대해 **이 인덱스에 근거해서만** 답하라. 규칙(엄수):
- 질문이 가리키는 기능/클래스가 인덱스에 있으면 status="implemented"(또는 일부만 있으면 "partial"), 근거 클래스명을 evidence에 넣어라.
- 인덱스에 없으면 status="not_found" + "코드에서 찾지 못함 (미구현이거나 명칭 불일치)"라고 정직히 답하라. **절대 인덱스에 없는 클래스/기능을 지어내지 마라.**
- 정적 구조(클래스 존재·참조)만 본다 → "런타임에 실제로 정상 동작하는지는 정적 분석으로 확인 불가(빌드/플레이 필요)"임을 answer에 1줄 명시.
- suggestions: 사용자가 원할 법한 후속 작업(고치기/새로 만들기)을 0~3개 task 초안으로(없으면 빈 배열).
반드시 JSON만: {"answer":"한국어 답변","status":"implemented|partial|not_found","evidence":["ClassName (system)", ...],"suggestions":[{"title":"간결한 제목","description":"무엇을 왜"}]}`;

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!OPENAI_API_KEY) return NextResponse.json({ error: "서버에 OPENAI_API_KEY 미설정" }, { status: 500 });

  const graph = loadGraph();
  if (!graph || !Array.isArray(graph.nodes)) return NextResponse.json({ error: "코드 그래프(DNA) 로드 실패 — graph.json 없음" }, { status: 500 });

  let audio: File | null = null;
  let textQ = "";
  try {
    const form = await req.formData();
    audio = form.get("audio") as File | null;
    textQ = String(form.get("text") || "");
  } catch {
    return NextResponse.json({ error: "form 파싱 실패" }, { status: 400 });
  }

  // 1) STT (오디오가 있으면) 또는 텍스트 질의
  let transcript = textQ.trim();
  if (audio) {
    const sttForm = new FormData();
    sttForm.append("file", audio, (audio as File).name || "q.webm");
    sttForm.append("model", "gpt-4o-mini-transcribe");
    sttForm.append("language", "ko");
    const sttRes = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST", headers: { Authorization: `Bearer ${OPENAI_API_KEY}` }, body: sttForm,
    });
    if (!sttRes.ok) return NextResponse.json({ error: "STT 실패", detail: (await sttRes.text()).slice(0, 300) }, { status: 502 });
    transcript = ((await sttRes.json()).text || "").trim();
  }
  if (!transcript) return NextResponse.json({ transcript: "", answer: "(질문 인식 실패)", status: "not_found", evidence: [], suggestions: [] });

  // 2) 코드 인덱스 — 실제 클래스 목록(근거). 토큰 절약: cls·system·참조수.
  const index = graph.nodes
    .slice()
    .sort((a, b) => (b.refsIn || 0) - (a.refsIn || 0))
    .map((n) => `${n.cls} [${n.system}] in=${n.refsIn} out=${n.refsOut}`)
    .join("\n");
  const sysLine = (graph.systems || []).map((s) => `${s.name}(${s.count})`).join(", ");

  // 3) 증거 기반 답 생성
  let out = { answer: "", status: "not_found", evidence: [] as string[], suggestions: [] as { title: string; description: string }[] };
  try {
    const aRes = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: SYS },
          { role: "user", content: `질문: ${transcript}\n\n[시스템]: ${sysLine}\n\n[코드 인덱스] (총 ${graph.nodes.length}개 클래스):\n${index.slice(0, 20000)}` },
        ],
        temperature: 0.1,
        response_format: { type: "json_object" },
      }),
    });
    const parsed = JSON.parse((await aRes.json()).choices?.[0]?.message?.content || "{}");
    out = {
      answer: String(parsed.answer || ""),
      status: ["implemented", "partial", "not_found"].includes(parsed.status) ? parsed.status : "not_found",
      evidence: Array.isArray(parsed.evidence) ? parsed.evidence.slice(0, 12).map(String) : [],
      suggestions: Array.isArray(parsed.suggestions) ? parsed.suggestions.slice(0, 5) : [],
    };
  } catch {
    out.answer = "(분석 실패)";
  }

  return NextResponse.json({ transcript, generatedFrom: graph.generatedFrom || "", ...out });
}
