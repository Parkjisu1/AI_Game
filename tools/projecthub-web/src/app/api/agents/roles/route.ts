import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, isAdminEmail } from "@/auth";

/**
 * AI 에이전트 역할 목록.
 *
 * 우선순위:
 *   1. MongoDB `hermes_agent_roles` 컬렉션 (있으면 사용 — Session 4-C에서 UI로 편집)
 *   2. DEFAULT_ROLES 폴백 (현재 agent_team.py의 하드코딩과 일치)
 *
 * Session 4-C가 완성되면 agent_team.py도 매 호출마다 DB 조회로 전환.
 */

interface AgentRole {
  role: string;
  tool: string;
  model: string;
  description: string;
  display_order?: number;
  team?: "dev" | "design" | "art";
  /**
   * 같은 team 안의 세부 분과 (Phase 1: 데이터/표시만, Phase 2: 파이프라인 분기 키).
   * "general"은 sub_team 미지정/공용. 비워두면 'general' 취급.
   */
  sub_team?: string;
  /**
   * Phase 4: 직무 기술서 (Job Description / Persona).
   * 호출 시 프롬프트 최상단에 주입되어 LLM이 그 직무의 전문가처럼 행동하게 함.
   * 외부 채용공고를 그대로 붙여넣어도 OK. 비워두면 미주입.
   */
  persona?: string;
}

/**
 * sub_team 기본 카탈로그 — UI 드롭다운/필터에서 사용.
 * 추가 sub_team은 /api/agents/roles POST 시 자유롭게 새 값을 보낼 수 있음 (확장).
 */
export const SUB_TEAMS: Record<"dev" | "design" | "art", string[]> = {
  dev:    ["ui", "server", "ingame", "outgame", "general"],
  art:    ["ui", "background", "illustration", "general"],
  design: ["content", "level", "general"],
};

// 팀별 기본 역할 (agent_team.py와 UI 양쪽 미러)
// sub_team: 같은 team 안의 분과. "general"은 공용 풀(미분화).
// PM 에이전트는 Translator 다음에 호출되어 어느 sub_team이 처리할지 판정 (Phase 2 활성).
const DEFAULT_ROLES: AgentRole[] = [
  // Translator는 팀 공용 — 모든 입력이 거치는 라우터
  {
    role: "translator",
    tool: "litellm",
    model: "sub-coder-agent",
    description: "자연어 태스크 해석 · 정보 부족 시 질문 생성 · 팀 라우팅",
    team: "dev",
    sub_team: "general",
    display_order: 0,
  },

  // === 개발팀 (dev) ====================================================
  // PM — sub_team 배당 결정 (Phase 2부터 Translator 다음에 호출)
  {
    role: "dev_pm",
    tool: "litellm",
    model: "sub-coder-agent",
    description: "[PM] 개발 태스크를 ui/server/ingame/outgame 중 어디에 배당할지 결정",
    team: "dev",
    sub_team: "general",
    display_order: 5,
  },
  // 공용(general) — 분화 안 된 일반 작업
  {
    role: "lead",
    tool: "claude",
    model: "claude-opus-4-7",
    description: "[Lead] 태스크 분해, 영향 분석, 작업 계획 수립",
    team: "dev",
    sub_team: "general",
    display_order: 10,
  },
  {
    role: "main_coder",
    tool: "claude",
    model: "claude-opus-4-7",
    description: "[Coder] 핵심 아키텍처/복잡 로직 구현",
    team: "dev",
    sub_team: "general",
    display_order: 20,
  },
  {
    role: "sub_coder",
    tool: "litellm",
    model: "sub-coder-agent",
    description: "[Coder] 병렬 구현 — OpenAI 백엔드로 부하 분산",
    team: "dev",
    sub_team: "general",
    display_order: 30,
  },
  {
    role: "validator",
    tool: "litellm",
    model: "validator-agent",
    description: "[Reviewer] 계약 교차 검증",
    team: "dev",
    sub_team: "general",
    display_order: 40,
  },
  {
    role: "optimizer",
    tool: "claude",
    model: "claude-opus-4-7",
    description: "[Coder] 성능 최적화 — #optimize 태그일 때만 호출",
    team: "dev",
    sub_team: "general",
    display_order: 50,
  },
  {
    role: "optimization_reviewer",
    tool: "litellm",
    model: "validator-agent",
    description: "[Reviewer] 최적화 정확성·실효성 검증",
    team: "dev",
    sub_team: "general",
    display_order: 60,
  },
  {
    role: "reviewer",
    tool: "claude",
    model: "claude-opus-4-7",
    description: "[Reviewer] 최종 품질 게이트 — Claude Max",
    team: "dev",
    sub_team: "general",
    display_order: 70,
  },

  // dev/ui — Unity UI(UGUI/UI Toolkit), Canvas, 메뉴/HUD
  { role: "dev_ui_lead",     tool: "claude",  model: "claude-opus-4-7", description: "[Lead] UI 작업 계획 — Canvas/UI Toolkit/Prefab 영향 분석", team: "dev", sub_team: "ui", display_order: 80 },
  { role: "dev_ui_coder",    tool: "claude",  model: "claude-opus-4-7", description: "[Coder] UI 구현 — UGUI/UI Toolkit/USS",                team: "dev", sub_team: "ui", display_order: 81 },
  { role: "dev_ui_reviewer", tool: "litellm", model: "validator-agent", description: "[Reviewer] UI 일관성·접근성 검수",                       team: "dev", sub_team: "ui", display_order: 82 },

  // dev/server — 서버 로직(같은 레포 내 server 폴더 또는 백엔드 API)
  { role: "dev_server_lead",     tool: "claude",  model: "claude-opus-4-7", description: "[Lead] 서버 작업 계획 — API/DB 스키마",        team: "dev", sub_team: "server", display_order: 90 },
  { role: "dev_server_coder",    tool: "claude",  model: "claude-opus-4-7", description: "[Coder] 서버 구현 — 엔드포인트/비즈니스 로직",  team: "dev", sub_team: "server", display_order: 91 },
  { role: "dev_server_reviewer", tool: "litellm", model: "validator-agent", description: "[Reviewer] API 계약·보안 검수",                  team: "dev", sub_team: "server", display_order: 92 },

  // dev/ingame — 인게임 시스템(게임플레이, 적/장애물, 점수, 물리)
  { role: "dev_ingame_lead",     tool: "claude",  model: "claude-opus-4-7", description: "[Lead] 인게임 작업 계획 — 게임플레이 영향 분석", team: "dev", sub_team: "ingame", display_order: 100 },
  { role: "dev_ingame_coder",    tool: "claude",  model: "claude-opus-4-7", description: "[Coder] 인게임 구현 — Manager/Spawner/Physics", team: "dev", sub_team: "ingame", display_order: 101 },
  { role: "dev_ingame_reviewer", tool: "litellm", model: "validator-agent", description: "[Reviewer] 인게임 밸런스·버그 검수",              team: "dev", sub_team: "ingame", display_order: 102 },

  // dev/outgame — 메타게임(상점, 인벤토리, 진행도, 로비)
  { role: "dev_outgame_lead",     tool: "claude",  model: "claude-opus-4-7", description: "[Lead] 아웃게임 작업 계획 — 메타 시스템 영향",  team: "dev", sub_team: "outgame", display_order: 110 },
  { role: "dev_outgame_coder",    tool: "claude",  model: "claude-opus-4-7", description: "[Coder] 아웃게임 구현 — 상점/인벤토리/진행도",   team: "dev", sub_team: "outgame", display_order: 111 },
  { role: "dev_outgame_reviewer", tool: "litellm", model: "validator-agent", description: "[Reviewer] 메타 시스템 일관성 검수",              team: "dev", sub_team: "outgame", display_order: 112 },

  // === 아트팀 (art) =================================================
  {
    role: "art_pm",
    tool: "litellm",
    model: "sub-coder-agent",
    description: "[PM] 아트 태스크를 ui/background/illustration 중 어디에 배당할지 결정",
    team: "art",
    sub_team: "general",
    display_order: 200,
  },
  // 기존 art 파이프라인 — 기본(general)
  {
    role: "art_prompter",
    tool: "litellm",
    model: "sub-coder-agent",
    description: "[Lead] 아트 요청을 GPT Image 2 프롬프트로 변환",
    team: "art",
    sub_team: "general",
    display_order: 210,
  },
  {
    role: "image_generator",
    tool: "litellm",
    model: "gpt-image-2",
    description: "[Coder] GPT Image 2로 실제 이미지 생성",
    team: "art",
    sub_team: "general",
    display_order: 220,
  },
  {
    role: "art_reviewer",
    tool: "claude",
    model: "claude-opus-4-7",
    description: "[Reviewer] 생성 이미지 품질 검수 — 프롬프트 의도 반영 여부",
    team: "art",
    sub_team: "general",
    display_order: 230,
  },

  // art/ui — UI 아이콘, 버튼, 메뉴 그래픽
  { role: "art_ui_prompter", tool: "litellm", model: "sub-coder-agent", description: "[Lead] UI 아트 프롬프트 — 아이콘/버튼/HUD 명세",       team: "art", sub_team: "ui", display_order: 240 },
  { role: "art_ui_reviewer", tool: "claude",  model: "claude-opus-4-7", description: "[Reviewer] UI 아트 검수 — 가독성·일관성·픽셀 정렬",     team: "art", sub_team: "ui", display_order: 241 },

  // art/background — 배경, 환경 컨셉, 스테이지 비주얼
  { role: "art_bg_prompter", tool: "litellm", model: "sub-coder-agent", description: "[Lead] 배경 아트 프롬프트 — 환경/무드/구도",           team: "art", sub_team: "background", display_order: 250 },
  { role: "art_bg_reviewer", tool: "claude",  model: "claude-opus-4-7", description: "[Reviewer] 배경 검수 — 게임 톤·앤·매너 일치 여부",     team: "art", sub_team: "background", display_order: 251 },

  // art/illustration — 캐릭터/원화/일러스트
  { role: "art_illust_prompter", tool: "litellm", model: "sub-coder-agent", description: "[Lead] 원화 프롬프트 — 캐릭터/장면 묘사",        team: "art", sub_team: "illustration", display_order: 260 },
  { role: "art_illust_reviewer", tool: "claude",  model: "claude-opus-4-7", description: "[Reviewer] 원화 검수 — 캐릭터 일관성·디테일",     team: "art", sub_team: "illustration", display_order: 261 },

  // === 기획팀 (design) =================================================
  {
    role: "design_pm",
    tool: "litellm",
    model: "sub-coder-agent",
    description: "[PM] 기획 태스크를 content/level 중 어디에 배당할지 결정",
    team: "design",
    sub_team: "general",
    display_order: 300,
    persona: `You are a senior Game Design PM at the aimed-puzzle (Balloonflow) studio with 5+ years experience routing design tasks. Your only job is classification:

- "level": grid 패턴, 만화경, 스테이지 레이아웃, 25x25 셀 디자인, 색상 배치, 대칭, 난이도 분배 등 격자 데이터에 가까운 작업
- "content": 시나리오, 보상 시스템, 메타 progression, UI 카피, 튜토리얼 텍스트, 이벤트 기획 등 문서·시스템에 가까운 작업

확신이 안 서면 description의 동사를 본다. "그려"/"배치해"/"패턴" → level, "써줘"/"기획해"/"문서" → content.`,
  },
  // design/content — 컨텐츠 기획(시나리오, 시스템, 보상)
  { role: "design_content_lead",     tool: "claude",  model: "claude-opus-4-7", description: "[Lead/미연결] 컨텐츠 기획 — 시나리오/보상/시스템", team: "design", sub_team: "content", display_order: 310 },
  { role: "design_content_writer",   tool: "claude",  model: "claude-opus-4-7", description: "[Coder/미연결] 컨텐츠 문서 작성",                  team: "design", sub_team: "content", display_order: 311 },
  { role: "design_content_reviewer", tool: "litellm", model: "validator-agent", description: "[Reviewer/미연결] 컨텐츠 일관성 검수",              team: "design", sub_team: "content", display_order: 312 },

  // design/level — 격자 레벨 디자인 (활성화됨)
  {
    role: "design_level_designer",
    tool: "claude",
    model: "claude-opus-4-7",
    description: "[Designer] 격자 레벨 spec(symmetry/palette/per_color_count) 생성 — 그리지 않고 spec만",
    team: "design",
    sub_team: "level",
    display_order: 320,
    persona: `You are a senior Level Designer (10+ years) specializing in casual puzzle games like Block Blast, BlockuDoku, Balloonflow. Your domain expertise: **grid-based level layouts** — tilemap puzzles, kaleidoscope patterns, symmetry-heavy compositions.

🚨 **CRITICAL: You do NOT draw the grid. You produce a JSON spec.** A deterministic Python module (\`level_grid_generator.py\`) takes your spec and draws the actual cells with pixel-perfect symmetry. Your job is to think *like a designer*: which colors? what symmetry? how dense? what feel? — and return spec only.

## Output JSON shape (strict)
\`\`\`json
{
  "name": "K-25-rose-quartz",
  "width": 25,
  "height": 25,
  "symmetry": "4-fold-rot",
  "palette": [0, 2, 17, 13, 4],
  "per_color_count": {"0": 40, "2": 40, "17": 60, "13": 20, "4": 20},
  "seed": 42,
  "rationale": "1-2 sentences why these choices fit user request"
}
\`\`\`

## Rules you MUST follow
- **palette**: BalloonFlow color indices (0..23) only. Pick 2-11 colors. Reference (0=HotPink, 1=Cyan, 2=Purple, 3=Yellow, 4=Green, 5=Orange, 6=White, 7=DarkGray, 8=SkyBlue, 9=Forest, 10=Red, 11=Blue, 12=Teal, 13=Lavender, 14=Periwinkle, 15=Brown, 16=Cream, 17=Pink, 18=Wine, 19=Mint, 20=Indigo, 21=Rose, 22=Silver, 23=Gray).
- **per_color_count keys are color indices as strings** ("0", "10"). Values are total cell counts.
- **Each per_color_count value must be a multiple of 10.** AND if symmetry is "4-fold" or "4-fold-rot", multiple of **20** (because every fundamental cell expands to 4).
- Sum of per_color_count must fit grid capacity:
  - 25x25 with 2-fold-h: max ≈ 624 (axis row excluded)
  - 25x25 with 4-fold or 4-fold-rot: max ≈ 576 (axis row+col excluded)
- **symmetry**: choose from "none", "2-fold-h", "2-fold-v", "4-fold", "diagonal", "4-fold-rot".
- **width/height**: default 25x25 unless user specifies. Diagonal/4-fold-rot require square.
- **seed**: pick a small int (1-1000). Different seeds → different layouts with same spec.

## Aesthetic guidance
- Casual puzzle game tone: avoid muddy/dark-only palettes. Mix saturated + pastel.
- Color theory: complementary (e.g. 0+11 pink+blue), triadic (0+4+11), analogous (10+11+12 red→blue→teal).
- Density: 20-40% filled is comfortable for visibility; >50% feels crowded; <15% feels sparse.
- Kaleidoscope feel: prefer 4-fold-rot with 3-5 colors, density 25-35%.

## When the user request is vague
Default to: 25x25, 4-fold-rot, 4 colors picked for the requested theme/mood, total filled cells ≈ 200 (multiple of 20).

Return JSON ONLY in a \`\`\`json\`\`\` code block. No prose outside the block.`,
  },
  {
    role: "design_level_reviewer",
    tool: "claude",
    model: "claude-opus-4-7",
    description: "[Reviewer] 격자 레벨 검수 — PNG 시각 + validation report 데이터 둘 다 확인",
    team: "design",
    sub_team: "level",
    display_order: 322,
    persona: `You are a senior Game Designer (12+ years) reviewing a generated puzzle level for the aimed-puzzle (Balloonflow) team.

## You receive
1. The original task description (what user wanted)
2. A PNG preview at a known path (use **Read tool** to view it)
3. A validation report — already-verified facts: symmetry held, color counts %10, palette in BalloonFlow range
4. The spec (symmetry, palette, per_color_count, seed)

## You evaluate (in this order)
1. **Visual reading** (Read the PNG): does it *look* like a kaleidoscope/pattern that delivers what the user asked? Is the palette pleasing or muddy? Are dense regions vs empty regions distributed nicely?
2. **Density & balance**: is one color dominating awkwardly? Are some colors so rare they feel like noise?
3. **Spec → request fit**: does symmetry/palette match the user's hint (e.g. user said "warm tones" — are the picked colors actually warm)?
4. **Re-roll suggestion**: if the layout is fine but feels random, suggest a different seed.

## You do NOT re-check
- Symmetry (validator already confirmed)
- 10-multiple counts (validator already confirmed)
- Out-of-palette colors (validator already blocked)
Don't waste tokens re-validating these.

## Output JSON
\`\`\`json
{
  "verdict": "ok" | "revise" | "regenerate" | "cannot_review",
  "quality_score": 0-100,
  "visual_observations": ["read the PNG and describe 3-5 facts"],
  "issues_found": ["문제 0-N개"],
  "notes": "검수 의견 2-3줄",
  "suggested_spec_adjustments": "verdict=revise/regenerate일 때만 — 다음 시도용 권고"
}
\`\`\`

Score guide:
- 90-100: 의도 정확 반영, 색감·밀도 우수
- 75-89:  좋음, 사소한 색 보정 권장
- 60-74:  허용 가능, 한 색 too dominant 또는 한 색 too sparse
- 40-59:  뚜렷한 약점 (palette 부조화, 너무 빈 patches), revise 권장
- 0-39:   regenerate 권장`,
  },
];

export async function GET() {
  try {
    const db = await getDb();
    const docs = await db
      .collection<AgentRole>("hermes_agent_roles")
      .find({})
      .sort({ display_order: 1 })
      .toArray();

    if (docs.length > 0) {
      return NextResponse.json({
        roles: docs.map((d) => ({
          role: d.role,
          tool: d.tool,
          model: d.model,
          description: d.description,
          display_order: d.display_order ?? 99,
          team: d.team || "dev",
          sub_team: d.sub_team || "general",
          persona: d.persona || "",
        })),
        sub_teams: SUB_TEAMS,
        source: "db",
      });
    }
  } catch {
    /* fall through to defaults */
  }

  return NextResponse.json({ roles: DEFAULT_ROLES, sub_teams: SUB_TEAMS, source: "default" });
}

async function requireAdmin() {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!isAdminEmail(email)) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  return null;
}

const ALLOWED_TOOLS = new Set(["claude", "litellm", "openai", "anthropic"]);
const ALLOWED_TEAMS = new Set(["dev", "design", "art"]);

function validateRolePayload(body: Record<string, unknown>): { ok: true; role: AgentRole } | { ok: false; error: string } {
  const role = typeof body.role === "string" ? body.role.trim() : "";
  const tool = typeof body.tool === "string" ? body.tool.trim().toLowerCase() : "";
  const model = typeof body.model === "string" ? body.model.trim() : "";
  const description = typeof body.description === "string" ? body.description.trim() : "";
  const display_order = typeof body.display_order === "number" ? body.display_order : 99;
  const teamRaw = typeof body.team === "string" ? body.team.trim().toLowerCase() : "dev";
  const team = (ALLOWED_TEAMS.has(teamRaw) ? teamRaw : "dev") as "dev" | "design" | "art";
  // sub_team — 자유 입력 허용 (Phase 3에서 신규 sub_team 추가 가능). 형식만 검증.
  const subRaw = typeof body.sub_team === "string" ? body.sub_team.trim().toLowerCase() : "general";
  const sub_team = subRaw && /^[a-z][a-z0-9_]*$/.test(subRaw) ? subRaw : "general";
  // persona — 직무 기술서. 4000자 cap (토큰 비용 폭주 방지)
  const persona = typeof body.persona === "string" ? body.persona.slice(0, 4000) : "";

  if (!role || !/^[a-z][a-z0-9_]*$/.test(role)) {
    return { ok: false, error: "role은 소문자+숫자+언더스코어로 (예: main_coder)" };
  }
  if (!ALLOWED_TOOLS.has(tool)) {
    return { ok: false, error: `tool은 ${Array.from(ALLOWED_TOOLS).join("/")} 중 하나` };
  }
  if (!model) return { ok: false, error: "model 필수" };

  return { ok: true, role: { role, tool, model, description, display_order, team, sub_team, persona } };
}

export async function POST(req: NextRequest) {
  const blocked = await requireAdmin();
  if (blocked) return blocked;

  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }
  const v = validateRolePayload(body as Record<string, unknown>);
  if (!v.ok) return NextResponse.json({ error: v.error }, { status: 400 });

  const db = await getDb();
  const coll = db.collection<AgentRole>("hermes_agent_roles");

  // upsert by role (unique)
  await coll.updateOne(
    { role: v.role.role },
    { $set: { ...v.role, updated_at: new Date().toISOString() } as unknown as AgentRole },
    { upsert: true }
  );
  return NextResponse.json({ ok: true, role: v.role });
}

export async function DELETE(req: NextRequest) {
  const blocked = await requireAdmin();
  if (blocked) return blocked;

  const url = new URL(req.url);
  const role = (url.searchParams.get("role") || "").trim();
  if (!role) return NextResponse.json({ error: "role query required" }, { status: 400 });

  const db = await getDb();
  await db.collection("hermes_agent_roles").deleteOne({ role });
  return NextResponse.json({ ok: true, role });
}

/**
 * DEFAULT를 DB에 시드 — 이미 있는 역할은 team/description이 비었을 때만 보정,
 * 없는 역할은 신규 insert. 사용자가 수동 편집한 tool/model/display_order는 보존.
 */
export async function PUT() {
  const blocked = await requireAdmin();
  if (blocked) return blocked;

  const db = await getDb();
  const coll = db.collection<AgentRole>("hermes_agent_roles");
  const existing = await coll.find({}).toArray();
  const existingByRole = new Map(existing.map((e) => [e.role, e]));
  const now = new Date().toISOString();
  let inserted = 0, patched = 0;

  for (const d of DEFAULT_ROLES) {
    const cur = existingByRole.get(d.role);
    if (!cur) {
      await coll.insertOne({ ...d, updated_at: now } as unknown as AgentRole);
      inserted++;
    } else {
      // 누락된 필드만 보강 — 사용자가 UI에서 손댄 값은 보존, 빈 자리만 default로 채움
      const patch: Record<string, unknown> = {};
      if (!cur.team && d.team) patch.team = d.team;
      if (!cur.sub_team && d.sub_team) patch.sub_team = d.sub_team;
      if (cur.display_order === undefined && d.display_order !== undefined) patch.display_order = d.display_order;
      // 페르소나가 비어있으면 default seed 페르소나로 채움 (UI에서 편집한 값은 그대로)
      const dPersona = (d as { persona?: string }).persona;
      if (!cur.persona && dPersona) patch.persona = dPersona;
      if (Object.keys(patch).length > 0) {
        await coll.updateOne({ role: d.role }, { $set: { ...patch, updated_at: now } });
        patched++;
      }
    }
  }
  return NextResponse.json({ ok: true, inserted, patched, total_defaults: DEFAULT_ROLES.length });
}
