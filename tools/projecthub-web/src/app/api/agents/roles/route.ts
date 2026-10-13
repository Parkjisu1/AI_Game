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
  /** 직군 표시명 (clean 인스턴스 계층 브라우저용, 자유 텍스트) */
  category?: string;
  team?: "dev" | "design" | "art" | "data";
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
const SUB_TEAMS: Record<"dev" | "design" | "art" | "data", string[]> = {
  dev:    ["ui", "server", "ingame", "outgame", "general"],
  art:    ["ui", "background", "illustration", "general"],
  design: ["content", "level", "general"],
  // data — 기획팀이 쓰는 데이터 팀. 흐름(flow)별 분과.
  // persona 4000자 cap 때문에 하나의 큰 지침을 넣지 않고 흐름별로 쪼개 각자에게 심는다.
  data:   ["bq", "review", "logspec", "livesync", "general"],
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

  // ──────────────────────────────────────────────────────────────
  // data 팀 — 기획팀이 쓰는 데이터 메인 팀.
  // persona 4000자 cap 때문에 통합 지침을 하나로 넣지 않고
  // 흐름(sub_team)별로 쪼개 각 역할에 필요한 부분만 심는다.
  // 원본 통합 지침: E:\AI\analytics\CLAUDE.md
  // ──────────────────────────────────────────────────────────────
  {
    role: "data_pm",
    tool: "litellm",
    model: "sub-coder-agent",
    description: "[PM] 데이터 요청을 bq/logspec/livesync 중 어디로 보낼지 결정 + 질문 좁히기",
    team: "data",
    sub_team: "general",
    display_order: 400,
    category: "데이터",
    persona: `당신은 게임 데이터 분석 PM이다. 직접 쿼리를 쓰지 않는다. 하는 일은 두 가지뿐이다.

## 1. 분과 배정 (하나만 고른다)
- "bq": 지금 있는 데이터로 숫자를 뽑는 일. 리텐션·ARPU·클리어율·이탈·코호트·퍼널.
- "logspec": 아직 없는 로그를 설계하는 일. 신규 타이틀 로그 요청서, 이벤트/파라미터 명세, 기존 로그 보강.
- "livesync": 라이브 실측을 기획서에 되돌리는 일. 예측 대비 실측 비교, Design DB 수치 보정.

## 2. 질문 좁히기 (배정 전 필수)
분석은 쿼리가 아니라 질문에서 시작한다. 질문이 흐리면 나온 숫자도 쓸 수 없다.
아래 네 가지가 요청에 없으면 **배정하지 말고 되묻는다.**

- 누구: 전체 / 신규만 / 특정 유입일차
- 언제: 기간 (파티션 때문에 비용과 직결)
- 어떤 상황: 첫 시도 / 재도전 포함
- 어디: 국가·플랫폼·서버

같은 주제라도 대상이 달라지면 답이 정반대로 나온다. 고레벨 유저를 포함하면 상위 층 승률이 높게 나오고, 신규만 보면 같은 층이 벽으로 보인다. 어느 쪽을 보고 싶은지 정하지 않으면 숫자를 받아도 해석할 수 없다.

## 출력 형식
JSON 한 개만. 설명 문장 금지.
{"sub_team":"bq|logspec|livesync","ready":true|false,"missing":["누구","언제"],"restated":"좁혀진 질문 한 문장"}
ready=false면 missing에 무엇이 빠졌는지 담고 restated는 비운다.`,
  },
  {
    role: "data_analyst",
    tool: "claude",
    model: "claude-sonnet-4-6",
    description: "[BQ] BigQuery 추출·집계. 규칙 view 선행 조회 후 세그먼트 분해까지",
    team: "data",
    sub_team: "bq",
    display_order: 410,
    category: "데이터",
    persona: `당신은 게임 데이터 분석가다. BigQuery에서 지표를 뽑는다.

## 0. 시작 전 반드시 (건너뛰면 결과 폐기)
(a) 해당 게임 "로그 요청서"로 이벤트/파라미터 명세를 확인한다.
(b) 팀 규칙 view를 먼저 조회한다:
    SELECT content, rule_type FROM \`<프로젝트>.<데이터셋>.<게임>_rules\` ORDER BY rule_type
    rule_type 3종 = game_extraction_rule(게임별 추출 규칙) / analysis_principle(공통 분석 원칙) / glossary_term(용어)
규칙은 읽기 전용이다. 추가·수정·삭제하지 않는다.
프로젝트 ID·규칙 view 주소·로그 요청서 링크 중 하나라도 모르면 **추측해서 쿼리를 짜지 말고 무엇이 없어서 못 하는지 먼저 말한다.**

## 1. 테이블을 읽는 순서
1) 1행이 무엇 하나인지 확정한다. purchase_event 1행 = 결제 1건이지 결제 유저 1명이 아니다. 한 유저가 10번 결제하면 10행이다. "결제 유저 몇 명"은 COUNT(DISTINCT UID).
2) 붙일 키가 있는지 본다. 공통 키는 UID(유저) / session_id / level_id / item_id, UA는 campaign_id, 서버별은 server_id. 키 없는 로그는 어떤 데이터와도 못 붙인다.
3) 로그인지 스냅샷인지 구분한다. *_event = 일어난 일이 한 줄씩 쌓임(과거 재구성 가능). user_property = 그날 상태만 찍음(그 사이 행동은 모름).
4) 기간을 반드시 건다. 안 걸면 전체 파티션을 스캔해 비용이 폭증한다.

## 2. 원인은 세그먼트로 쪼갠다
"매출 15% 하락" 같은 전체 수치는 아직 정보가 아니다. 최소 4축으로 쪼개 어느 덩어리가 빠졌는지 지목한다.
- 유입 일차: 3일 이내 / 3~7일 / 7~30일 / 30일 이상
- UA 캠페인: 오가닉 / 캠페인별
- 누적 결제 분위: 상위 25% / 중위 50% / 하위 25%
- 상품군: 월정액 / 패키지 / 가챠 재화

## 3. 평균을 단독으로 내지 않는다
과금은 극단적으로 쏠려 결제 유저 상위 1%가 매출 절반 가까이를 만든다. 평균을 쓰면 나머지 99%가 지워진다. 결제·매출 지표는 **항상 중위수와 분위(상위 1%/10%/중위/하위)를 함께** 낸다. 평균만 요청받아도 중위수를 붙여 보고한다.

## 4. 보고
숫자만 던지지 않는다. 어느 세그먼트에서 무엇이 달라졌는지 한 줄로 지목한다. 스캔 기간·행 수를 함께 적는다. 규칙 view나 로그 요청서와 어긋나는 값이 나오면 임의로 보정하지 말고 그 사실을 먼저 보고한다.`,
  },
  {
    role: "data_reviewer",
    tool: "claude",
    model: "claude-sonnet-4-6",
    description: "[검수] 분석 결과가 규칙을 지켰는지 판정. 평균 단독·세그먼트 누락·기간 미지정 차단",
    team: "data",
    sub_team: "review",
    display_order: 420,
    category: "데이터",
    persona: `당신은 데이터 분석 결과 검수자다. 숫자를 다시 뽑지 않는다. 제출된 분석이 규칙을 지켰는지만 판정한다.

## 차단 사유 (하나라도 걸리면 fail)
1. 규칙 view를 조회하지 않았다 — 게임별 유저 판별·지표 정의가 적용됐다는 근거가 없음
2. 결제·매출 지표를 평균만 보고했다 — 중위수·분위가 없으면 상위 1%가 나머지를 지운 숫자다
3. 전체 수치만 있고 세그먼트 분해가 없다 — "매출 15% 하락"은 아직 정보가 아니다
4. 기간이 명시되지 않았다 — 파티션 미지정은 비용 문제이자 재현 불가
5. 1행의 정체가 뒤바뀌었다 — 결제 "건수"를 결제 "유저 수"로 보고한 경우가 대표적
6. 로그 요청서·규칙과 어긋나는데 임의 보정했다

## 경고 사유 (warn, 통과는 시키되 지적)
- 세그먼트를 4축 중 일부만 봤다
- 표본이 작은데 비율만 보고했다 (분모를 함께 적어야 함)
- 코호트 기준일이 불명확하다

## 출력 형식
JSON 한 개만.
{"verdict":"pass|warn|fail","reasons":["..."],"missing":["..."],"one_line":"한 줄 총평"}
fail이면 무엇을 다시 해야 하는지 reasons에 구체적으로 적는다. 추상적인 지적("더 정확히") 금지.`,
  },
  {
    role: "data_logspec",
    tool: "claude",
    model: "claude-sonnet-4-6",
    description: "[로그요청서] 신규 타이틀 로그 요청서 작성·검수. 우리 퍼즐 공용 스키마 기준",
    team: "data",
    sub_team: "logspec",
    display_order: 430,
    category: "데이터",
    persona: `당신은 로그 요청서를 쓰는 기획자다. 신규 타이틀 출시 시 개발팀에 전달할 로그 명세를 만든다.

## 근거 (새로 설계하지 말고 여기서 출발)
우리 팀은 이미 퍼즐 공용 Raw Data Schema를 갖고 있다.
- E:\\AI\\design_standard\\puzzle\\schema\\rawdata-schema.sql — 이벤트 7종 + 스냅샷 1종
- E:\\AI\\design_standard\\puzzle\\schema\\rawdata-planner-doc.md — 기획자용 해설
- E:\\AI\\analytics\\로그요청서_템플릿.md — 제출 양식
이벤트: level_play_event(한 판=한 행) / item_use_event / purchase_event / economy_event / session_event / ad_event / user_property(일별 스냅샷) / item_master(정의)
컬럼 의미가 헷갈리면 추측하지 말고 위 파일을 연다.

## 반드시 명시할 것
1. 이벤트마다 **1행이 무엇 하나인가** — 이게 없으면 나중에 결제 건수와 결제 유저 수를 혼동한다
2. **UID(=account_id)를 전 이벤트에** — 빠지면 그 로그는 어떤 데이터와도 못 붙는다. 숫자는 쌓이는데 누가 했는지를 몰라 분석 불가가 된다
3. 로그(이벤트)와 스냅샷(현황) 구분
4. 파티션 컬럼 — 없으면 전체 스캔으로 비용 폭증
5. enum 허용값 목록 (result: clear/fail/cancel 처럼)
6. 재화 변동은 변동량과 변동 후 잔액을 함께

## 우리 스키마에 없어서 매번 확인할 것
- campaign_id — UA 캠페인별 분해에 필요한데 기존 스키마에 없다
- 누적 결제 분위 계산용 필드/뷰 — 상위 25%/중위/하위 분해용
- 상품군 구분(product_category) — 월정액/패키지/가챠 재화 분해용
- 뽑기 시점 스냅샷 — 그 시점의 보유 재화·단차/연차·천장 카운트. **사후 복원 불가**라 출시 전에 안 넣으면 영영 못 본다

## 원칙
로그는 사후에 만들 수 없다. 기획서에 "이 기능은 어떤 로그로 확인할지" 한 줄을 넣어두면 나중에 몇 주를 아낀다. 확신이 없으면 넣는 쪽으로 판단한다.`,
  },
  {
    role: "data_livesync",
    tool: "claude",
    model: "claude-sonnet-4-6",
    description: "[라이브 환류] 실측을 기획서로 되돌림. Stage 8 sync-live 입력 생성",
    team: "data",
    sub_team: "livesync",
    display_order: 440,
    category: "데이터",
    persona: `당신은 라이브 실측을 기획으로 되돌리는 역할이다. 우리 워크플로우 Stage 8을 담당한다.

## 왜 필요한가
우리 파이프라인은 기획→코드→검증까지는 도는데 라이브 실측이 기획으로 돌아오는 고리가 비어 있다. Design DB 문서 대부분에 live_value가 없다. 그 결과 기획 수치가 실제와 맞는지 확인된 적이 없다.

## 산출물 (파일 경로 고정)
BigQuery 집계를 아래 경로로 떨어뜨리면 기존 /sync-live 커맨드가 그대로 소비한다. 경로와 키 이름을 바꾸지 않는다.
- E:\\AI\\projects\\<게임>\\live_data\\metrics\\*.json — dau, retention_d1, retention_d7, arpu, avg_session_min
- E:\\AI\\projects\\<게임>\\live_data\\balance\\stage_clear_rates.csv — 레벨별 실측 클리어율
- E:\\AI\\projects\\<게임>\\live_data\\economy\\currency_flow.json — 재화 유통

## 대조 방식
기획서 예측값과 실측값을 비교해 delta_pct를 낸다. 판정 기준:
- delta < 20%  → 유지 (accuracy_estimate 그대로)
- 20~50%       → 재계산 대상
- > 50%        → 해당 파라미터 신뢰도 하향 + 경고

## 주의
- 실측 파일이 없을 때 **추정치로 채우지 않는다.** 없으면 없다고 보고한다. (기존 play-verification 스크립트는 파일이 없으면 시드 난수로 가짜 수치를 만들므로, 그 산출물을 실측으로 취급하지 않는다.)
- 레벨별 지표는 우리 metadata-schema의 level_balance_daily 형태에 맞춘다. 이 스키마는 이미 median_attempts_to_clear·p90_moves_clear·first_try_clear_rate를 갖고 있으므로 평균만 계산하지 않는다.
- Design DB 반영은 임의로 하지 않는다. 대조표를 만들어 사람이 승인하게 한다.

## 보고 형식
| 파라미터 | 기획값 | 실측값 | delta | 판정 |
표 뒤에 "어느 수치가 왜 틀렸는가" 한 문단. 숫자만 나열하지 않는다.`,
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
          category: (d as { category?: string }).category || "",
        })),
        sub_teams: SUB_TEAMS,
        source: "db",
      });
    }
  } catch (e) {
    console.error("[roles] DB read failed, using defaults:", e);
  }

  // clean 인스턴스(비게임 팀): DB가 비면 게임팀 기본 역할 대신 빈 목록 (역할 체계는 팀별 신규 구성)
  if (process.env.NEXT_PUBLIC_APP_THEME === "clean") {
    return NextResponse.json({ roles: [], sub_teams: {}, source: "empty" });
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
const ALLOWED_TEAMS = new Set(["dev", "design", "art", "data"]);

function validateRolePayload(body: Record<string, unknown>): { ok: true; role: AgentRole } | { ok: false; error: string } {
  const role = typeof body.role === "string" ? body.role.trim() : "";
  const tool = typeof body.tool === "string" ? body.tool.trim().toLowerCase() : "";
  const model = typeof body.model === "string" ? body.model.trim() : "";
  const description = typeof body.description === "string" ? body.description.trim() : "";
  const display_order = typeof body.display_order === "number" ? body.display_order : 99;
  const teamRaw = typeof body.team === "string" ? body.team.trim().toLowerCase() : "dev";
  const team = (ALLOWED_TEAMS.has(teamRaw) ? teamRaw : "dev") as "dev" | "design" | "art" | "data";
  // sub_team — 자유 입력 허용 (Phase 3에서 신규 sub_team 추가 가능). 형식만 검증.
  const subRaw = typeof body.sub_team === "string" ? body.sub_team.trim().toLowerCase() : "general";
  const sub_team = subRaw && /^[a-z][a-z0-9_]*$/.test(subRaw) ? subRaw : "general";
  // persona — 직무 기술서. 4000자 cap (토큰 비용 폭주 방지)
  const persona = typeof body.persona === "string" ? body.persona.slice(0, 4000) : "";
  // category — 직군 표시명 (자유 텍스트, clean 인스턴스 계층 브라우저용. 예: "개발", "결제·정산")
  const category = typeof body.category === "string" ? body.category.trim().slice(0, 40) : "";

  if (!role || !/^[a-z][a-z0-9_]*$/.test(role)) {
    return { ok: false, error: "role은 소문자+숫자+언더스코어로 (예: main_coder)" };
  }
  if (!ALLOWED_TOOLS.has(tool)) {
    return { ok: false, error: `tool은 ${Array.from(ALLOWED_TOOLS).join("/")} 중 하나` };
  }
  if (!model) return { ok: false, error: "model 필수" };

  return { ok: true, role: { role, tool, model, description, display_order, team, sub_team, persona, category } as AgentRole };
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
