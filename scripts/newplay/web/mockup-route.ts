import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, authDisabled, isAdminEmail } from "@/auth";

/**
 * 목업 요청 — 설계 문서(산출물)를 화면으로 볼 수 있게 만든다.
 *
 * 왜 필요한가:
 *   design 산출물은 문서라 미리보기에 나올 게 없다. 그런데 "게임키 판매 화면" 같은 건
 *   글로 읽는 것보다 화면으로 보는 편이 판단이 빠르다.
 *   그래서 설계 문서를 근거로 **정적 목업 화면**을 만드는 dev 태스크를 만들어준다.
 *   그 태스크가 끝나면 패치가 나오고, 그 패치는 기존 미리보기 경로를 그대로 탄다.
 *
 * 만드는 것은 태스크 하나뿐이다. 레포·운영·QA 에는 아무것도 쓰지 않는다.
 *
 * 주의: 확인 항목이 아직 "아니오" 로 남아 있으면 설계가 확정되지 않은 것이다.
 *       그 상태로 목업을 만들면 틀린 화면을 만들게 되므로 경고를 함께 돌려준다.
 */
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let email = "";
  if (!authDisabled) {
    const s = await auth();
    email = String(s?.user?.email || "");
    if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    if (!isAdminEmail(email)) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const body = await req.json().catch(() => null);
  const id = String(body?.id || "");
  if (!/^[a-f0-9]{24}$/i.test(id)) return NextResponse.json({ error: "invalid id" }, { status: 400 });

  const { ObjectId } = await import("mongodb");
  const db = await getDb();
  const col = db.collection("pixelforge_tasks");
  const src = await col.findOne(
    { _id: new ObjectId(id) },
    { projection: { title: 1, deliverable: 1, acceptance_criteria: 1, project: 1 } },
  );
  if (!src?.deliverable) return NextResponse.json({ error: "산출물이 없는 태스크입니다" }, { status: 404 });

  const crits: { text: string; state: string }[] = Array.isArray(src.acceptance_criteria) ? src.acceptance_criteria : [];
  const ng = crits.filter((c) => c.state === "ng");
  const pending = crits.filter((c) => c.state !== "ok" && c.state !== "ng");
  const confirmed = crits.filter((c) => c.state === "ok");

  // 이미 같은 원본으로 만든 목업 태스크가 있으면 중복 생성하지 않는다.
  const dup = await col.findOne({ mockup_of: String(src._id) }, { projection: { _id: 1, status: 1 } });
  if (dup) {
    return NextResponse.json({
      ok: true, reused: true, taskId: String(dup._id), status: dup.status,
      warning: "이미 이 설계로 만든 목업 태스크가 있습니다.",
    });
  }

  const lines = [
    `아래 설계 문서를 근거로 **정적 목업 화면**을 만들어줘. 기능 동작은 필요 없고, 화면만 보이면 된다.`,
    ``,
    `## 만드는 방법`,
    `- 기존 스토어 화면의 톤앤매너·컴포넌트·SCSS 규칙을 그대로 따른다. 새 디자인 언어를 만들지 마라.`,
    `- 라우트를 새로 추가해 접근 가능하게 한다(예: /mockup/<이름>). 기존 라우트를 건드리지 마라.`,
    `- API 호출은 넣지 마라. 화면에 보일 값은 파일 안의 상수로 둔다.`,
    `- 문구는 i18n 을 거치지 않고 한국어 상수로 둬도 된다 — 목업이라는 것을 주석에 명시할 것.`,
    `- **미리보기로 확인할 것이므로 front-end/ 안에서만 변경한다.** 백엔드는 건드리지 마라.`,
    ``,
    `## 확정된 전제 (사람이 "예" 로 판정함)`,
    confirmed.length ? confirmed.map((c) => `- ${c.text}`).join("\n") : "- (아직 확정된 항목이 없음)",
  ];
  if (ng.length) {
    lines.push(``, `## ⛔ 사람이 "아니오" 로 판정한 항목 — 이 전제는 쓰지 마라`, ng.map((c) => `- ${c.text}`).join("\n"));
  }
  if (pending.length) {
    lines.push(``, `## 미판정 항목 — 쓰되 화면에 가정임을 표시하라`, pending.map((c) => `- ${c.text}`).join("\n"));
  }
  lines.push(``, `---`, ``, `## 원본 설계 문서`, ``, String(src.deliverable).slice(0, 30000));

  const now = new Date().toISOString();
  const doc = {
    title: `[목업] ${src.title}`,
    description: lines.join("\n"),
    status: "todo",
    assignee: "hermes",
    project: src.project || "webstore",
    team: "dev",
    team_override: true,
    sub_team: "frontend",
    sub_team_override: true,
    mockup_of: String(src._id),
    created_by_email: email,
    created_at: now,
    updated_at: now,
    comments: [],
    has_image: false,
  };
  const r = await col.insertOne(doc);
  await col.updateOne({ _id: src._id }, { $set: { mockup_task_id: String(r.insertedId) } });

  return NextResponse.json({
    ok: true,
    taskId: String(r.insertedId),
    warning: ng.length
      ? `"아니오" 로 판정된 항목 ${ng.length}개는 제외했습니다.`
      : pending.length
      ? `미판정 항목이 ${pending.length}개 있습니다 — 확정 후 만드는 편이 정확합니다.`
      : "",
  });
}
