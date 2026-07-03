import { NextResponse } from "next/server";
import { auth } from "@/auth";

// OpenAI Realtime 세션용 단기 client secret 발급 (서버 키는 절대 클라이언트로 안 나감).
// 클라이언트는 이 secret으로 WebRTC를 직접 OpenAI에 연결한다 (10분 만료).

const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const REALTIME_MODEL = process.env.OPENAI_REALTIME_MODEL || "gpt-realtime";

const INSTRUCTIONS = `당신은 BalloonFlow 팀의 AI 비서 JARVIS다. 한국어로 짧고 명료하게 대화한다.

역할:
- 팀의 작업 현황 질문 → get_status 툴을 호출해 실제 데이터로만 답한다 (추측 금지).
- 업무 지시 → 제목/내용을 요약해 사용자에게 구두로 확인받은 뒤에만 create_task를 호출한다.
- 작업 유형이 명확하면 제목 앞에 태그를 붙인다: [unity] 코드수정, [art], [기획], [level], [sim], [goal] (큰 목표 → 자동 분해).
- 모르는 것은 모른다고 답한다. 숫자·상태는 반드시 툴 결과에 근거한다.
말투: 간결한 비서 톤. 불필요한 사족 없이 핵심만.`;

export async function POST() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!OPENAI_API_KEY) return NextResponse.json({ error: "서버에 OPENAI_API_KEY 미설정" }, { status: 500 });

  const body = {
    expires_after: { anchor: "created_at", seconds: 600 },
    session: {
      type: "realtime",
      model: REALTIME_MODEL,
      instructions: INSTRUCTIONS,
      audio: {
        input: { transcription: { model: "gpt-4o-mini-transcribe", language: "ko" } },
        output: { voice: "marin" },
      },
      tools: [
        {
          type: "function",
          name: "get_status",
          description: "Hermes 작업 보드 현황 조회 — todo/진행중/리뷰/24h 완료 수, 진행중 작업 목록, 워커 상태",
          parameters: { type: "object", properties: {}, required: [] },
        },
        {
          type: "function",
          name: "create_task",
          description: "새 Hermes 작업 생성. 반드시 사용자에게 제목을 구두로 확인받은 뒤 호출.",
          parameters: {
            type: "object",
            properties: {
              title: { type: "string", description: "작업 제목 (유형 태그 포함, 예: '[unity] 팝업 사운드 타이밍 수정')" },
              description: { type: "string", description: "실행자가 바로 착수 가능한 구체적 지시" },
            },
            required: ["title"],
          },
        },
      ],
      tool_choice: "auto",
    },
  };

  const r = await fetch("https://api.openai.com/v1/realtime/client_secrets", {
    method: "POST",
    headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.value) {
    return NextResponse.json(
      { error: "realtime 세션 생성 실패", detail: JSON.stringify(j).slice(0, 400) },
      { status: 502 },
    );
  }
  return NextResponse.json({ value: j.value, expires_at: j.expires_at, model: REALTIME_MODEL });
}
