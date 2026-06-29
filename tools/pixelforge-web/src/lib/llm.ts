// Gemma 4 (또는 Gemini) 호출 — Google AI Studio API
// 픽셀 컬러 ID 매트릭스 생성 — Track A(모티프) / Track B(패턴) 워크플로우 적용

const API_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

// 28색 팔레트 (HEX + 한글명) — LLM이 색을 시각적으로 이해하도록
const PALETTE_FULL: Record<number, { hex: string; ko: string; family: string }> = {
  1:  { hex: "#FC6AAF", ko: "핫핑크",   family: "Pink/Red" },
  2:  { hex: "#50E8F6", ko: "시안",     family: "Blue" },
  3:  { hex: "#8950F8", ko: "바이올렛", family: "Purple" },
  4:  { hex: "#FED555", ko: "노랑",     family: "Yellow" },
  5:  { hex: "#73FE66", ko: "라임",     family: "Green" },
  6:  { hex: "#FDA14C", ko: "주황",     family: "Orange" },
  7:  { hex: "#FFFFFF", ko: "흰색",     family: "Neutral" },
  8:  { hex: "#414141", ko: "다크그레이", family: "Neutral" },
  9:  { hex: "#6EA8FA", ko: "스카이블루", family: "Blue" },
  10: { hex: "#39AE2E", ko: "다크그린", family: "Green" },
  11: { hex: "#FC5E5E", ko: "코랄레드", family: "Pink/Red" },
  12: { hex: "#326BF8", ko: "블루",     family: "Blue" },
  13: { hex: "#3AA58B", ko: "틸",       family: "Green/Teal" },
  14: { hex: "#E7A7FA", ko: "라벤더",   family: "Purple" },
  15: { hex: "#B7C7FB", ko: "페리윙클", family: "Blue" },
  16: { hex: "#6A4A30", ko: "갈색",     family: "Neutral" },
  17: { hex: "#FEE3A9", ko: "크림",     family: "Yellow" },
  18: { hex: "#FDB7C1", ko: "라이트핑크", family: "Pink/Red" },
  19: { hex: "#9E3D5E", ko: "다크로즈", family: "Pink/Red" },
  20: { hex: "#A7DD94", ko: "라이트그린", family: "Green" },
  21: { hex: "#592E7E", ko: "다크퍼플", family: "Purple" },
  22: { hex: "#DC7881", ko: "로즈",     family: "Pink/Red" },
  23: { hex: "#D9D9E7", ko: "라이트그레이", family: "Neutral" },
  24: { hex: "#6F727F", ko: "미디엄그레이", family: "Neutral" },
  25: { hex: "#FC38A5", ko: "마젠타",   family: "Pink/Red" },
  26: { hex: "#FDB458", ko: "앰버",     family: "Orange" },
  27: { hex: "#890A08", ko: "다크레드", family: "Pink/Red" },
  28: { hex: "#6FAFB1", ko: "세이지틸", family: "Green/Teal" },
};

// 키워드로 Track 자동 분류
function detectTrack(prompt: string): "motif" | "pattern" {
  const lower = prompt.toLowerCase();
  const patternKeywords = [
    "kaleidoscope", "만화경", "stripe", "스트라이프", "줄무늬", "checkerboard", "체커",
    "체크", "격자", "grid pattern", "geometric", "기하학", "기하", "tile", "타일",
    "symmetry", "대칭", "4분할", "쿼드런트", "quadrant", "mirror", "spiral", "소용돌이",
    "honeycomb", "벌집", "mandala", "만다라", "diamond pattern", "마름모", "concentric",
    "동심원", "dot pattern", "점", "lattice", "weave", "직조", "tessellation",
  ];
  if (patternKeywords.some((k) => lower.includes(k))) return "pattern";
  return "motif";
}

// 모티프 복잡도에 따른 권장 그리드 크기
function complexityHint(cols: number, rows: number): string {
  const max = Math.max(cols, rows);
  if (max <= 24) return "단순 아이콘 (실루엣 + 1~2 디테일)";
  if (max <= 32) return "중간 오브젝트 (메인 형태 + 음영 + 작은 디테일)";
  return "복잡한 대상 (전체 형태 + 다중 부위 + 세밀한 음영/하이라이트)";
}
// 기본: Gemini 2.5 Flash — 빠르고(5~10s) 무료 티어 충분, 매트릭스 출력 정확
const DEFAULT_MODEL = "gemini-2.5-flash";

// 모델별 fallback 체인 — 첫 번째 모델 실패 시 자동으로 다음 시도
// Pro 모델은 무료 티어 quota가 빡빡하므로 Flash로 폴백
const FALLBACK_CHAIN: Record<string, string[]> = {
  "gemini-2.5-flash": [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
  ],
  "gemini-2.5-pro": [
    "gemini-2.5-pro",
    "gemini-2.5-flash",  // Pro 429 시 Flash로 폴백
    "gemini-2.0-flash",
  ],
  "gemma-4-e4b-it": [
    "gemma-4-e4b-it",
    "gemma-3-4b-it",
    "gemma-2-2b-it",
    "gemini-2.5-flash",  // Gemma 안 되면 Flash
  ],
  "gemma-4-31b-it": [
    "gemma-4-31b-it",
    "gemma-3-27b-it",
    "gemma-2-27b-it",
    "gemini-2.5-flash",
  ],
};

// 지원 모델 (Nav settings dropdown)
export const SUPPORTED_MODELS = [
  { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash (빠름·고품질·추천)" },
  { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro (느림·최고품질)" },
  { id: "gemma-4-e4b-it", label: "Gemma 4 E4B (오픈소스·빠름)" },
  { id: "gemma-4-31b-it", label: "Gemma 4 31B (오픈소스·느림·고품질)" },
] as const;

// 28 game palette names — LLM에게 전달할 색 설명
const PALETTE_NAMES_KO: Record<number, string> = {
  1: "핑크", 2: "시안", 3: "보라", 4: "노랑", 5: "라임",
  6: "주황", 7: "흰색", 8: "검정", 9: "하늘", 10: "초록",
  11: "빨강", 12: "파랑", 13: "청록", 14: "연보라", 15: "연파랑",
  16: "갈색", 17: "살구", 18: "연분홍", 19: "와인", 20: "연초록",
  21: "진보라", 22: "코랄", 23: "연회색", 24: "회색", 25: "마젠타",
  26: "연주황", 27: "진빨강", 28: "민트",
};

export interface MatrixResult {
  matrix: number[][]; // [rows][cols], 0 = empty cell, 1~28 = color id
  rawText?: string;   // 디버깅용 원문 (LLM 응답 그대로)
  parseStats?: {
    usedModel?: string;
    rawLength: number;
    parsedRowCount: number;
    expectedRows: number;
    expectedCols: number;
    rowLengths: number[];  // 파싱된 각 행의 길이
    track?: "motif" | "pattern";
  };
}

interface GenerateMatrixOptions {
  apiKey: string;
  model?: string;
  prompt: string;       // designer_note 또는 의미 설명
  cols: number;
  rows: number;
  paletteIds?: number[]; // 사용 가능한 색상 ID (제한 없으면 1~28 전체)
  emptyAllowed?: boolean; // 빈 셀(0) 허용 여부
}

async function callOneModel(
  model: string,
  apiKey: string,
  systemInstruction: string,
  userPrompt: string,
  cols: number,
  rows: number
): Promise<{ rawText: string; status: number; errBody: string }> {
  const url = `${API_BASE}/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey)}`;
  const body = {
    contents: [
      { role: "user", parts: [{ text: `${systemInstruction}\n\n${userPrompt}` }] },
    ],
    generationConfig: {
      temperature: 0.4,
      maxOutputTokens: Math.min(8192, cols * rows * 4 + 200),
    },
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errBody = await res.text();
    return { rawText: "", status: res.status, errBody };
  }
  const data = await res.json();
  const rawText: string = data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
  return { rawText, status: 200, errBody: "" };
}

export async function generatePixelMatrix(opts: GenerateMatrixOptions): Promise<MatrixResult> {
  const { apiKey, prompt, cols, rows, paletteIds, emptyAllowed = false } = opts;
  const requestedModel = opts.model || DEFAULT_MODEL;

  // 사용 가능 색상 목록 (id, hex, 한글명, family 모두 LLM에 전달)
  const allowedIds = paletteIds && paletteIds.length > 0 ? paletteIds : Array.from({ length: 28 }, (_, i) => i + 1);
  const paletteDesc = allowedIds
    .map((id) => {
      const p = PALETTE_FULL[id];
      return p ? `c${id}=${p.hex}(${p.ko},${p.family})` : `c${id}`;
    })
    .join(", ");

  const track = detectTrack(prompt);
  const trackInstruction = track === "pattern"
    ? `### Track B — Pattern Workflow (기하학·반복·대칭)
This subject is a GEOMETRIC PATTERN. Use mathematical/algorithmic placement:
- **Symmetry**: Pick one — 8-way (kaleidoscope), 4-way (quadrant), horizontal mirror, vertical mirror, point symmetry, or rotational
- **Repetition unit**: Define a small motif (3×3 or 5×5) and tile it across the grid with EXACT alignment
- **Color balance**: If a specific count of colors is given, distribute them roughly evenly
- **Pixel-perfect alignment**: Every cell of every repetition unit MUST be in identical relative position. ZERO drift, ZERO antialiasing, ZERO partial cells
- **Examples**:
  - Honeycomb: hex tile pattern, alternating rows offset by half cell
  - Checkerboard: alternating cells, rigid 2-color or N-color rotation
  - Mandala: 8-way radial symmetry from center
  - Stripes: solid horizontal/vertical/diagonal bands of fixed width`
    : `### Track A — Motif Workflow (구체적 형상)
This subject is a CONCRETE MOTIF (object, character, food, building, animal, etc).
Complexity for ${cols}×${rows}: ${complexityHint(cols, rows)}

**Color role assignment** — Before drawing, assign each allowed color to a role:
- **outline**: Darkest color (often c8 darkgray or c27 darkred or c16 brown). Forms the silhouette edge
- **main_base**: Primary fill color of the main subject
- **main_highlight**: Lighter tone of main_base (light source, top-left)
- **main_shadow**: Darker tone of main_base (opposite light source)
- **secondary**: Sub-element color (e.g. leaf for a flower, sword for a knight)
- **point**: Accent color (eyes, gems, small details)
- **background** (if no transparency): Single uniform color filling empty cells
- **3-tone rule**: Same color family in light/mid/dark forms gives depth (e.g., c20 light-green / c5 lime / c10 darkgreen)

**Drawing rules**:
1. Start with the outer silhouette using the OUTLINE color — single-cell-wide line forming the shape
2. Fill the interior with main_base
3. Add highlight cells where light hits (typically top-left)
4. Add shadow cells opposite the highlight
5. Place secondary/point cells last for detail
6. NO floating disconnected cells unless intentional (sparkles, eyes)
7. The shape must be visually recognizable as the subject when viewed at this resolution`;

  const systemInstruction = `You are a pixel art generation engine. Output ONLY a 2D integer matrix of color IDs.

### Hard Rules
- Output EXACTLY ${rows} lines, each with EXACTLY ${cols} space-separated integers
- Each cell = ONE color ID (single integer). No mixing, no decimals
- Use ONLY these color IDs: ${paletteDesc}
- ${emptyAllowed ? "Use 0 for empty/transparent cells (background)" : "All cells MUST be filled with allowed color IDs (no 0)"}
- NO markdown fences, NO prose, NO color names — only the matrix
- Each cell becomes a solid colored block of pixels (no antialiasing). Plan accordingly.

${trackInstruction}

### Output Format
Return exactly ${rows} lines. Each line has ${cols} integers separated by single spaces. First line = top row, last line = bottom row. Example for 3×3 with c1, c5, c12:
1 5 1
5 12 5
1 5 1`;

  const userPrompt = `Subject: ${prompt}
Grid: ${cols} columns × ${rows} rows
Apply the appropriate Track workflow above and output the matrix now.`;

  // Fallback 체인 시도
  const chain = FALLBACK_CHAIN[requestedModel] || [requestedModel];
  const errors: string[] = [];
  let rawText = "";
  let usedModel = "";
  let hadQuotaError = false;
  for (const model of chain) {
    const result = await callOneModel(model, apiKey, systemInstruction, userPrompt, cols, rows);
    if (result.status === 200 && result.rawText) {
      rawText = result.rawText;
      usedModel = model;
      break;
    }
    if (result.status === 429) hadQuotaError = true;
    // 429는 짧게, 404는 더 짧게 (모델 부재 — 노이즈)
    const snippet = result.errBody.substring(0, 100).replace(/\s+/g, " ");
    errors.push(`${model}[${result.status}] ${snippet}`);
  }
  if (!rawText) {
    if (hadQuotaError) {
      throw new Error(
        `Quota 초과 (429) — 무료 티어 한도. 잠시 후 재시도하거나, 우상단 ⚙️에서 모델을 'Gemini 2.5 Flash'로 변경하세요. ${errors[0]}`
      );
    }
    throw new Error(`All models failed: ${errors.join(" | ")}`);
  }

  const { matrix, rowLengths } = parseMatrix(rawText, cols, rows, new Set(allowedIds), emptyAllowed);

  // 품질 검증: 유효한 행이 기대치의 50% 미만이면 실패로 판단
  const parsedRowCount = rowLengths.length;
  if (parsedRowCount < Math.ceil(rows * 0.5)) {
    const preview = rawText.substring(0, 300).replace(/\n/g, " | ");
    throw new Error(
      `LLM 출력이 불완전합니다 — ${parsedRowCount}/${rows} 행만 파싱됨. 모델(${usedModel})이 매트릭스 형식을 지키지 않았습니다. ` +
      `원문 일부: "${preview}". 모델을 다른 것으로 바꾸거나(Gemini Pro) 프롬프트를 더 구체적으로 적어보세요.`
    );
  }

  return {
    matrix,
    rawText,
    parseStats: {
      usedModel,
      rawLength: rawText.length,
      parsedRowCount,
      expectedRows: rows,
      expectedCols: cols,
      rowLengths,
      track,
    },
  };
}

// 단일 행에서 "Row 1:", "|", ",", "[...]" 같은 접두사/장식 제거
function extractNumsFromLine(line: string): number[] {
  // "Row N:" "Line N:" 같은 접두사 제거
  let cleaned = line.replace(/^(row|line|r)\s*\d+\s*[:\-\.]?\s*/i, "");
  // JSON/array 장식 제거
  cleaned = cleaned.replace(/[\[\],|]/g, " ");
  // 1~28 범위 또는 0인 정수만 추출 (음수 거부, 2~3자리 숫자만)
  const matches = cleaned.match(/\b\d{1,2}\b/g);
  if (!matches) return [];
  return matches.map(Number).filter((n) => n >= 0 && n <= 99);
}

// LLM 응답에서 정수 매트릭스 추출 — 더 관대한 파싱
export function parseMatrix(
  text: string,
  cols: number,
  rows: number,
  allowedIds: Set<number>,
  emptyAllowed: boolean
): { matrix: number[][]; rowLengths: number[] } {
  // 코드 펜스 제거
  let cleaned = text.replace(/```[a-z]*\n?/gi, "").replace(/```/g, "");
  // "c1" → "1" 형태 처리 (LLM이 c 접두사를 붙이면)
  cleaned = cleaned.replace(/\bc(\d{1,2})\b/gi, "$1");
  // 라인 단위
  const lines = cleaned.split("\n").map((l) => l.trim()).filter(Boolean);
  const parsed: number[][] = [];
  for (const line of lines) {
    const nums = extractNumsFromLine(line);
    if (nums.length < Math.max(3, cols / 3)) continue; // 너무 짧은 라인은 스킵 (잡음)
    parsed.push(nums);
  }

  const rowLengths = parsed.map((r) => r.length);

  // 행 수가 부족하면 마지막 행 반복하여 보강
  while (parsed.length < rows) {
    if (parsed.length === 0) {
      parsed.push(new Array(cols).fill(emptyAllowed ? 0 : Array.from(allowedIds)[0] || 1));
    } else {
      parsed.push([...parsed[parsed.length - 1]]);
    }
  }
  if (parsed.length > rows) parsed.length = rows;

  // 각 행 cols 길이로 정규화 + 색 ID 검증
  const out: number[][] = [];
  for (let r = 0; r < rows; r++) {
    const row: number[] = [];
    const src = parsed[r];
    for (let c = 0; c < cols; c++) {
      let v = src[c] ?? src[src.length - 1] ?? 0;
      if (v === 0 && !emptyAllowed) {
        v = Array.from(allowedIds)[0] || 1;
      }
      if (v !== 0 && !allowedIds.has(v)) {
        v = Array.from(allowedIds)[0] || 1;
      }
      row.push(v);
    }
    out.push(row);
  }
  return { matrix: out, rowLengths };
}
