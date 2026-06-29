import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

/**
 * 허용된 담당자 목록 반환.
 *
 * 소스:
 *  1. projecthub_settings.slack_assignee_webhooks (실제 팀원 DM 매핑)
 *  2. Hermes 에이전트 (자동 추가)
 *  3. 폴백: 기존 태스크의 assignee 필드 (레거시 대비)
 *
 * Phase 2에 유저 인증 붙으면 이 API가 로그인 기반 화이트리스트 반환.
 */
export interface AssigneeOption {
  name: string;
  label?: string;  // 표시용 (예: "🤖 Hermes")
  isBot?: boolean;
  slack_user_id?: string;
}

export async function GET() {
  try {
    const db = await getDb();
    const doc = await db
      .collection("projecthub_settings")
      .findOne({ key: "current" });

    const settings = (doc?.settings || {}) as {
      slack_assignee_webhooks?: Array<{
        assignee: string;
        slack_user_id?: string;
        webhook_url?: string;
      }>;
    };

    const options: AssigneeOption[] = [];
    const seen = new Set<string>();

    // 1. Hermes 최상단 고정
    options.push({
      name: "hermes",
      label: "🤖 Hermes (AI)",
      isBot: true,
    });
    seen.add("hermes");

    // 2. settings.slack_assignee_webhooks의 사용자들
    for (const mapping of settings.slack_assignee_webhooks || []) {
      const name = (mapping.assignee || "").trim();
      if (!name) continue;
      const low = name.toLowerCase();
      // hermes/헤르메스/hermes-bot 변형은 위의 "hermes"로 통합 → 중복 스킵
      if (low === "hermes" || low === "hermes-bot" || low === "헤르메스") continue;
      if (seen.has(name)) continue;
      options.push({
        name,
        label: name,
        slack_user_id: mapping.slack_user_id,
      });
      seen.add(name);
    }

    // 3. 폴백: 기존 태스크에서 쓰인 이름도 포함 (레거시 데이터 대비)
    //    — 단, seen에 없는 것만 추가해서 중복 방지
    const existingAssignees = await db
      .collection("pixelforge_tasks")
      .distinct("assignee");
    for (const name of existingAssignees) {
      if (typeof name !== "string") continue;
      const trimmed = name.trim();
      if (!trimmed) continue;
      const low = trimmed.toLowerCase();
      if (seen.has(trimmed) || low === "hermes-bot" || low === "헤르메스") continue;
      options.push({ name: trimmed, label: trimmed });
      seen.add(trimmed);
    }

    return NextResponse.json(options);
  } catch (e) {
    console.error("[/api/assignees] error:", e);
    // DB 에러 시 최소한 hermes는 반환
    return NextResponse.json([
      { name: "hermes", label: "🤖 Hermes (AI)", isBot: true },
    ]);
  }
}
