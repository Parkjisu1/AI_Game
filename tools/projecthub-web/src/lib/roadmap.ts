// Sort Puzzle Roadmap CSV 파서 + 차트 데이터 가공

export interface RoadmapTask {
  role: string;       // "기획" | "개발" | "아트" | "★" | "ALL"
  title: string;
  period: string;
  weekStart: number;  // 1~12, 0 = 미정
  weekEnd: number;
  sprintId: number;
}

export interface RoadmapSprint {
  id: number;
  label: string;
  weekStart: number;
  weekEnd: number;
}

export interface RoadmapData {
  uploadedAt: string;
  startDate: string;  // W1 시작일 (YYYY-MM-DD), 미상이면 빈 문자열
  sprints: RoadmapSprint[];
  tasks: RoadmapTask[];
}

const ROLE_KEYS = new Set(["기획", "개발", "아트", "★", "ALL"]);
export const ROLE_COLORS: Record<string, string> = {
  "기획": "#3b82f6",  // blue
  "개발": "#10b981",  // green
  "아트": "#f59e0b",  // amber
  "★":   "#ef4444",   // red (마일스톤)
  "ALL":  "#6b7280",  // gray
};

// CSV 한 줄 파서 (RFC4180 lite)
function splitCSVLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQ) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') inQ = false;
      else cur += ch;
    } else {
      if (ch === '"') inQ = true;
      else if (ch === ",") { out.push(cur); cur = ""; }
      else cur += ch;
    }
  }
  out.push(cur);
  return out;
}

// "W1", "W1~W2", "W11-W12", "W3" 등 → [start, end]
function parsePeriod(s: string): [number, number] {
  if (!s) return [0, 0];
  const m = s.match(/W(\d+)(?:\s*[~\-]\s*W?(\d+))?/);
  if (m) return [parseInt(m[1]), parseInt(m[2] || m[1])];
  return [0, 0];
}

export function parseRoadmapCSV(text: string): RoadmapData {
  // BOM 제거 + 줄바꿈 통일
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const raw = text.replace(/\r\n/g, "\n");

  // CSV는 따옴표 안에 \n이 있을 수 있으므로 전체를 한 번에 파싱하지 말고
  // 라인 단위로 따옴표 짝을 추적하면서 합쳐야 함
  const lines: string[] = [];
  let buf = "";
  let inQ = false;
  for (const ch of raw) {
    if (ch === '"') inQ = !inQ;
    if (ch === "\n" && !inQ) {
      lines.push(buf);
      buf = "";
    } else {
      buf += ch;
    }
  }
  if (buf) lines.push(buf);

  const sprints: RoadmapSprint[] = [];
  const tasks: RoadmapTask[] = [];
  let currentSprint = -1;
  let startDate = "";

  for (const line of lines) {
    const cols = splitCSVLine(line);
    const first = (cols[0] || "").trim();
    const second = (cols[1] || "").trim();

    // 시작일 추출 (헤더 행에 있는 경우 — W1 컬럼명에서)
    if (!startDate) {
      for (const c of cols) {
        const m = c.match(/W1[^\d]*(\d{1,2})[\/\-](\d{1,2})/);
        if (m) {
          // 연도는 알 수 없으므로 현재 연도 사용
          const yr = new Date().getFullYear();
          startDate = `${yr}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}`;
          break;
        }
      }
    }

    // Sprint 헤더 (예: "SPRINT 0: 프리프로덕션 (W1~W3)")
    const sprintMatch = first.match(/^SPRINT\s+(\d+)\s*:/i);
    if (sprintMatch) {
      currentSprint = parseInt(sprintMatch[1]);
      const weekRange = first.match(/W(\d+)\s*~\s*W(\d+)/);
      sprints.push({
        id: currentSprint,
        label: first,
        weekStart: weekRange ? parseInt(weekRange[1]) : 0,
        weekEnd: weekRange ? parseInt(weekRange[2]) : 0,
      });
      continue;
    }

    // Task 행
    if (!ROLE_KEYS.has(first)) continue;
    if (!second) continue;

    const period = (cols[2] || "").trim();
    const [ws, we] = parsePeriod(period);
    tasks.push({
      role: first,
      title: second,
      period,
      weekStart: ws,
      weekEnd: we,
      sprintId: currentSprint,
    });
  }

  return {
    uploadedAt: new Date().toISOString(),
    startDate,
    sprints,
    tasks,
  };
}

// 주별 역할별 task 카운트 매트릭스
export function buildWeeklyMatrix(data: RoadmapData): {
  weeks: number[];
  roles: string[];
  matrix: Record<string, Record<number, number>>; // role → week → count
  weekTotals: Record<number, number>;
  maxTotal: number;
} {
  const maxWeek = Math.max(
    ...data.tasks.map((t) => t.weekEnd || 0),
    ...data.sprints.map((s) => s.weekEnd || 0),
    12
  );
  const weeks = Array.from({ length: maxWeek }, (_, i) => i + 1);
  const rolesSet = new Set<string>();
  const matrix: Record<string, Record<number, number>> = {};
  const weekTotals: Record<number, number> = {};

  for (const t of data.tasks) {
    rolesSet.add(t.role);
    if (!matrix[t.role]) matrix[t.role] = {};
    if (t.weekStart === 0 || t.weekEnd === 0) continue;
    for (let w = t.weekStart; w <= t.weekEnd; w++) {
      matrix[t.role][w] = (matrix[t.role][w] || 0) + 1;
      weekTotals[w] = (weekTotals[w] || 0) + 1;
    }
  }

  const roles = Array.from(rolesSet);
  const maxTotal = Math.max(0, ...Object.values(weekTotals));
  return { weeks, roles, matrix, weekTotals, maxTotal };
}

// 오늘 날짜 기준 현재 주 번호 (1~12, 범위 밖이면 0)
export function currentWeek(startDate: string): number {
  if (!startDate) return 0;
  const start = new Date(startDate);
  const today = new Date();
  const diffDays = Math.floor((today.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return 0;
  return Math.floor(diffDays / 7) + 1;
}
