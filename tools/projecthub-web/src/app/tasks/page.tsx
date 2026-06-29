"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";

interface Comment {
  text: string;
  author: string;
  created_at: string;
}

interface Attachment {
  id: string;
  kind: "md" | "json" | "text";
  name: string;
  mime: string;
  size: number;
  content: string;  // UTF-8 평문 (base64 아님) — LLM이 직접 읽을 수 있게
}

type Team = "dev" | "art" | "design" | "chat" | "auto";

interface Task {
  _id?: string;
  title: string;
  description: string;
  assignee: string;
  priority: "urgent" | "high" | "medium" | "low";
  status: "todo" | "in_progress" | "review" | "done";
  related_levels: string;
  /** 목록 응답에는 포함되지 않음 — 상세 GET /api/tasks/[id]에서만 fetch (lazy) */
  image_base64?: string;
  /** 목록 응답에서만 채워짐. 카드의 📎 아이콘 표시용 */
  has_image?: boolean;
  /** 목록 응답에는 제외 — 상세 GET에서 fetch */
  attachments?: Attachment[];
  /** 목록 응답에서는 마지막 5개만 (검색 보조). 상세 GET에서 전체 */
  comments?: Comment[];
  created_at?: string;
  updated_at?: string;
  team?: Team;                  // Translator 판정 or 사용자 수동 재배정
  team_override?: boolean;      // true면 Translator가 덮어쓰지 않음
  /** team 안의 분과 (예: dev→ui/server/ingame/outgame, art→ui/background/illustration). "general"은 미분화 */
  sub_team?: string;
  /** PM 자동 배당을 덮어쓰지 않게 잠금 (사용자 수동 sub_team 지정 시) */
  sub_team_override?: boolean;
  generated_design_ids?: string[];
  generated_level_ids?: string[];
  created_by_email?: string;
  /** true면 watcher가 이 task를 일절 처리하지 않음 (⛔ 중단). ▶️ 재개 시 false. */
  hermes_stopped?: boolean;
}

const TEAM_META: Record<Team, { label: string; emoji: string; color: string; bg: string }> = {
  dev:    { label: "개발", emoji: "💻", color: "text-cyan-700",    bg: "bg-cyan-50 border-cyan-300" },
  art:    { label: "아트", emoji: "🎨", color: "text-pink-700",    bg: "bg-pink-50 border-pink-300" },
  design: { label: "기획", emoji: "📐", color: "text-amber-700",   bg: "bg-amber-50 border-amber-300" },
  chat:   { label: "대화", emoji: "💬", color: "text-gray-600",    bg: "bg-gray-50 border-gray-300" },
  auto:   { label: "자동", emoji: "🤖", color: "text-slate-500",   bg: "bg-slate-50 border-slate-300" },
};

/** team별 sub_team 카탈로그 — /api/agents/roles의 SUB_TEAMS와 동기화 */
const SUB_TEAMS: Record<Team, string[]> = {
  dev:    ["general", "ui", "server", "ingame", "outgame"],
  art:    ["general", "ui", "background", "illustration"],
  design: ["general", "content", "level"],
  chat:   ["general"],
  auto:   ["general"],
};

const SUB_TEAM_LABELS: Record<string, string> = {
  general:      "공용",
  ui:           "UI",
  server:       "서버",
  ingame:       "인게임",
  outgame:      "아웃게임",
  background:   "배경",
  illustration: "원화",
  content:      "컨텐츠",
  level:        "레벨",
};

function subTeamLabel(s?: string): string {
  if (!s) return "공용";
  return SUB_TEAM_LABELS[s] || s;
}

// 태그/키워드 기반 자동 팀 추론 (Translator 결과 없을 때 폴백)
function inferTeam(task: Task): Team {
  if (task.team && task.team !== "auto") return task.team;
  const text = `${task.title} ${task.description}`.toLowerCase();
  if (/\[(art|아트|image|sprite|illustration)\]|이미지 생성|디자인 참조|일러스트/.test(text)) return "art";
  if (/\[(design|기획|balance|spec|plan)\]|밸런스|난이도|레벨 기획|기획서/.test(text)) return "design";
  if (/\[(unity|code|patch|fix|sync|optimize)\]|\.cs|prefab|수정|manager/.test(text)) return "dev";
  return "chat";
}

/** task 텍스트로부터 sub_team 추정 (PM이 결정 안 했을 때 폴백) */
function inferSubTeam(task: Task, team: Team): string {
  if (task.sub_team) return task.sub_team;
  const text = `${task.title} ${task.description}`.toLowerCase();
  if (team === "dev") {
    if (/\[(ui)\]|canvas|ugui|ui\s?toolkit|hud|button|menu|메뉴|버튼/.test(text)) return "ui";
    if (/\[(server|backend|api)\]|api|endpoint|server|백엔드|서버/.test(text)) return "server";
    if (/\[(ingame|인게임)\]|spawner|gameplay|physics|풍선|벌룬|장애물|인게임/.test(text)) return "ingame";
    if (/\[(outgame|아웃게임)\]|상점|인벤토리|로비|진행도|outgame/.test(text)) return "outgame";
  }
  if (team === "art") {
    if (/\[(ui)\]|아이콘|버튼|hud|메뉴/.test(text)) return "ui";
    if (/\[(bg|background)\]|배경|환경|스테이지/.test(text)) return "background";
    if (/\[(illust|illustration|원화|character)\]|캐릭터|일러스트|원화/.test(text)) return "illustration";
  }
  if (team === "design") {
    if (/\[(level)\]|레벨|난이도|밸런싱/.test(text)) return "level";
    if (/\[(content)\]|컨텐츠|시나리오|보상/.test(text)) return "content";
  }
  return "general";
}

const TEXT_ATTACH_MAX_BYTES = 256 * 1024;      // 파일 하나당
const TOTAL_ATTACH_MAX_BYTES = 5 * 1024 * 1024; // 전체 합계
const ATTACH_ACCEPT = ".md,.markdown,.json,.txt,.log,.yml,.yaml,.cs,.py,.ts,.tsx,.js";

interface AssigneeOption {
  name: string;
  label?: string;
  isBot?: boolean;
  slack_user_id?: string;
}

const COLUMNS: { id: Task["status"]; label: string; color: string; accent: string }[] = [
  { id: "todo",        label: "할 일",   color: "bg-gray-100", accent: "#94a3b8" },
  { id: "in_progress", label: "진행 중", color: "bg-blue-50",   accent: "#3b82f6" },
  { id: "review",      label: "리뷰",    color: "bg-yellow-50", accent: "#f59e0b" },
  { id: "done",        label: "완료",    color: "bg-green-50",  accent: "#10b981" },
];
const TEAM_ICON: Record<string, string> = { dev: "code", art: "palette", design: "ruler", chat: "chat", auto: "bot" };

const PRIORITY_STYLES: Record<Task["priority"], { badge: string; dot: string }> = {
  urgent: { badge: "bg-red-100 text-red-700",    dot: "bg-red-500" },
  high:   { badge: "bg-orange-100 text-orange-700", dot: "bg-orange-400" },
  medium: { badge: "bg-blue-100 text-blue-700",  dot: "bg-blue-400" },
  low:    { badge: "bg-gray-100 text-gray-500",  dot: "bg-gray-300" },
};

/** priority 필드가 누락된 doc도 깨지지 않도록 medium 폴백 */
function priStyle(p: Task["priority"] | undefined | null): { badge: string; dot: string } {
  return (p && PRIORITY_STYLES[p]) || PRIORITY_STYLES.medium;
}

const EMPTY_TASK: Omit<Task, "_id" | "created_at" | "updated_at"> = {
  title: "",
  description: "",
  assignee: "",
  priority: "medium",
  status: "todo",
  related_levels: "",
  image_base64: "",
  attachments: [],
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_TASK });
  const [saving, setSaving] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<Task["status"] | null>(null);
  const [detailTask, setDetailTask] = useState<Task | null>(null);
  const [filterAssignee, setFilterAssignee] = useState<string>("all");
  const [filterPriority, setFilterPriority] = useState<string>("all");
  const [filterTeam, setFilterTeam] = useState<string>("all");
  const [filterSubTeam, setFilterSubTeam] = useState<string>("all");
  const [allowedAssignees, setAllowedAssignees] = useState<AssigneeOption[]>([]);
  const titleRef = useRef<HTMLInputElement>(null);

  // Session 12: 검색 + 내 태스크 + 태그 필터 + 전역 팔레트 + URL 공유
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [showOnlyMine, setShowOnlyMine] = useState<boolean>(false);
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set());
  const [currentUserEmail, setCurrentUserEmail] = useState<string>("");
  const [showPalette, setShowPalette] = useState<boolean>(false);
  const [paletteQuery, setPaletteQuery] = useState<string>("");

  // 허용된 담당자 목록 (API에서 가져옴 — Hermes + 팀원들)
  useEffect(() => {
    fetch("/api/assignees")
      .then((r) => r.json())
      .then((data: AssigneeOption[]) => {
        if (Array.isArray(data)) setAllowedAssignees(data);
      })
      .catch(() => {
        // 폴백: hermes만
        setAllowedAssignees([{ name: "hermes", label: "🤖 Hermes (AI)", isBot: true }]);
      });
    // 현재 로그인 사용자 이메일 (내 태스크 필터용)
    fetch("/api/auth/session")
      .then((r) => r.json())
      .then((j) => {
        const e = (j?.user?.email || "").toLowerCase();
        if (e) setCurrentUserEmail(e);
      })
      .catch(() => {});
  }, []);

  // 전역 단축키 — Cmd/Ctrl+K 로 검색 팔레트 열기
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setShowPalette((v) => !v);
      } else if (e.key === "Escape") {
        setShowPalette(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // 필터 드롭다운용 (허용된 목록 + 기존 태스크의 담당자 합집합)
  const assigneeList = useMemo(() => {
    const set = new Set<string>();
    allowedAssignees.forEach((a) => set.add(a.name));
    tasks.forEach((t) => { if (t.assignee?.trim()) set.add(t.assignee.trim()); });
    return Array.from(set).sort();
  }, [tasks, allowedAssignees]);

  // 태스크 제목에서 [tag] 패턴 추출 (필터용 facet)
  const tagFacets = useMemo(() => {
    const counts = new Map<string, number>();
    const re = /\[([^\]]+)\]/g;
    for (const t of tasks) {
      const text = `${t.title} ${t.description}`;
      let m: RegExpExecArray | null;
      const seen = new Set<string>();
      while ((m = re.exec(text)) !== null) {
        const tag = m[1].trim().toLowerCase();
        if (!tag || tag.length > 30 || seen.has(tag)) continue;
        seen.add(tag);
        counts.set(tag, (counts.get(tag) || 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20);
  }, [tasks]);

  function toggleTag(tag: string) {
    setActiveTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag); else next.add(tag);
      return next;
    });
  }

  // 필터 적용된 task 목록 (Session 12 확장)
  const filteredTasks = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const tagArr = Array.from(activeTags);
    return tasks.filter((t) => {
      if (filterAssignee !== "all" && (t.assignee || "") !== filterAssignee) return false;
      if (filterPriority !== "all" && t.priority !== filterPriority) return false;
      if (filterTeam !== "all" && inferTeam(t) !== filterTeam) return false;
      if (filterSubTeam !== "all" && inferSubTeam(t, inferTeam(t)) !== filterSubTeam) return false;
      // 내 태스크 — 내가 만들었거나, 내가 담당(이메일이 assignee 매핑에 있으면)이거나, 내가 코멘트를 남긴 태스크
      if (showOnlyMine) {
        if (!currentUserEmail) return false;
        const createdByMe = (t as { created_by_email?: string }).created_by_email === currentUserEmail;
        const commentedByMe = (t.comments || []).some((c) => {
          const author = (c.author || "").toLowerCase();
          return author === currentUserEmail || (currentUserEmail.startsWith(author + "@") && author.length > 0);
        });
        if (!createdByMe && !commentedByMe) return false;
      }
      // 태그 필터 (AND)
      if (tagArr.length > 0) {
        const text = `${t.title} ${t.description}`.toLowerCase();
        if (!tagArr.every((tag) => text.includes(`[${tag}]`))) return false;
      }
      // 텍스트 검색 — 제목 + 설명 + 최근 코멘트 일부
      if (q) {
        const hay =
          `${t.title} ${t.description} ${t.assignee || ""} ` +
          (t.comments || []).slice(-5).map((c) => c.text || "").join(" ");
        if (!hay.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [tasks, filterAssignee, filterPriority, filterTeam, filterSubTeam, searchQuery, showOnlyMine, activeTags, currentUserEmail]);

  // 텍스트 계열 파일 첨부 (md/json/txt...) — UTF-8 평문으로 저장
  async function handleFileAttach(file: File) {
    if (file.size > TEXT_ATTACH_MAX_BYTES) {
      alert(`파일은 ${Math.round(TEXT_ATTACH_MAX_BYTES / 1024)}KB 이하만 지원됩니다. (${file.name}: ${Math.round(file.size / 1024)}KB)`);
      return;
    }
    const lowName = file.name.toLowerCase();
    let kind: Attachment["kind"] = "text";
    if (lowName.endsWith(".md") || lowName.endsWith(".markdown")) kind = "md";
    else if (lowName.endsWith(".json")) kind = "json";

    const current = form.attachments || [];
    const totalSize = current.reduce((s, a) => s + a.size, 0) + file.size;
    if (totalSize > TOTAL_ATTACH_MAX_BYTES) {
      alert(`첨부 합계가 ${Math.round(TOTAL_ATTACH_MAX_BYTES / 1024 / 1024)}MB를 초과할 수 없습니다.`);
      return;
    }
    try {
      const content = await file.text();
      const att: Attachment = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        kind,
        name: file.name,
        mime: file.type || "text/plain",
        size: file.size,
        content,
      };
      setForm((prev) => ({ ...prev, attachments: [...(prev.attachments || []), att] }));
    } catch {
      alert("파일을 읽을 수 없습니다 (인코딩 문제일 수 있음).");
    }
  }

  function removeAttachment(id: string) {
    setForm((prev) => ({
      ...prev,
      attachments: (prev.attachments || []).filter((a) => a.id !== id),
    }));
  }

  // 이미지 첨부 핸들러 (FileReader → base64 data URL)
  function handleImageAttach(file: File) {
    if (file.size > 2 * 1024 * 1024) {
      alert("이미지 크기는 2MB 이하만 지원됩니다.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = String(e.target?.result || "");
      setForm((prev) => ({ ...prev, image_base64: dataUrl }));
    };
    reader.readAsDataURL(file);
  }

  useEffect(() => {
    fetchTasks();
  }, []);

  // detailTask가 열릴 때 — 목록 응답엔 image_base64/attachments/full comments가 없으므로 lazy fetch.
  // 한 번만 fetch (이미 image_base64 있으면 skip).
  useEffect(() => {
    if (!detailTask?._id) return;
    if (detailTask.image_base64 !== undefined) return;  // 이미 채워짐 (또는 명시적 빈 string)
    let cancelled = false;
    fetch(`/api/tasks/${detailTask._id}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((full: Task | null) => {
        if (cancelled || !full) return;
        // detailTask가 아직 같은 _id면 머지
        setDetailTask((cur) => (cur && String(cur._id) === String(detailTask._id) ? { ...cur, ...full } : cur));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [detailTask?._id, detailTask?.image_base64]);

  // URL hash로 태스크 공유 — #task=<id> 있으면 로드 후 해당 모달 자동 오픈
  useEffect(() => {
    function openFromHash() {
      const h = window.location.hash;
      const m = /#task=([a-f0-9]{24})/.exec(h);
      if (!m) return;
      const id = m[1];
      const t = tasks.find((x) => String(x._id) === id);
      if (t) setDetailTask(t);
    }
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, [tasks]);

  useEffect(() => {
    if (showModal && titleRef.current) titleRef.current.focus();
  }, [showModal]);

  // SSE — 다른 클라이언트나 Hermes watcher가 task를 바꾸면 자동 반영
  useEffect(() => {
    const es = new EventSource("/api/tasks/stream");

    const applyUpsert = (raw: unknown) => {
      const incoming = raw as Task | undefined;
      if (!incoming || !incoming._id) return;
      const id = String(incoming._id);
      setTasks((prev) => {
        const idx = prev.findIndex((t) => String(t._id) === id);
        if (idx === -1) return [...prev, { ...incoming, _id: id }];
        const next = prev.slice();
        next[idx] = { ...incoming, _id: id };
        return next;
      });
      setDetailTask((cur) =>
        cur && String(cur._id) === id ? { ...incoming, _id: id } : cur
      );
    };

    es.addEventListener("insert", (e: MessageEvent) => {
      try { applyUpsert(JSON.parse(e.data)?.task); } catch { /* ignore */ }
    });
    es.addEventListener("update", (e: MessageEvent) => {
      try { applyUpsert(JSON.parse(e.data)?.task); } catch { /* ignore */ }
    });
    es.addEventListener("delete", (e: MessageEvent) => {
      try {
        const id = String(JSON.parse(e.data)?._id || "");
        if (!id) return;
        setTasks((prev) => prev.filter((t) => String(t._id) !== id));
        setDetailTask((cur) => (cur && String(cur._id) === id ? null : cur));
      } catch { /* ignore */ }
    });
    // 서버 에러/change stream 끊김 — EventSource가 자동 재연결

    return () => es.close();
  }, []);

  async function fetchTasks() {
    try {
      const data = await fetch("/api/tasks").then((r) => r.json());
      if (Array.isArray(data)) setTasks(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  async function createTask() {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (data.ok) {
        setTasks((prev) => [...prev, { ...form, _id: String(data.id) }]);
        setForm({ ...EMPTY_TASK });
        setShowModal(false);
      }
    } catch { /* ignore */ }
    finally { setSaving(false); }
  }

  async function moveTask(task: Task, newStatus: Task["status"]) {
    if (task.status === newStatus) return;
    const updated = { ...task, status: newStatus };
    setTasks((prev) => prev.map((t) => (t._id === task._id ? updated : t)));
    try {
      await fetch("/api/tasks", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ _id: task._id, status: newStatus }),
      });
    } catch { /* ignore */ }
  }

  // Drag and Drop
  function onDragStart(taskId: string) {
    setDragging(taskId);
  }

  function onDragEnd() {
    setDragging(null);
    setDragOver(null);
  }

  function onDragOver(e: React.DragEvent, colId: Task["status"]) {
    e.preventDefault();
    setDragOver(colId);
  }

  function onDrop(e: React.DragEvent, colId: Task["status"]) {
    e.preventDefault();
    if (!dragging) return;
    const task = tasks.find((t) => t._id === dragging);
    if (task) moveTask(task, colId);
    setDragging(null);
    setDragOver(null);
  }

  const tasksByStatus = (status: Task["status"]) =>
    filteredTasks.filter((t) => t.status === status);

  function formatDate(iso?: string) {
    if (!iso) return "";
    return new Date(iso).toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  }

  const nextStatus: Record<Task["status"], Task["status"]> = {
    todo: "in_progress",
    in_progress: "review",
    review: "done",
    done: "todo",
  };

  const hasAnyFilter =
    filterAssignee !== "all" || filterPriority !== "all" || filterTeam !== "all" || filterSubTeam !== "all" ||
    searchQuery.trim() !== "" || showOnlyMine || activeTags.size > 0;

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2"><Icon name="tasks" size={24} /> 작업 보드</h1>
          <p className="text-sm text-gray-500 mt-1 leading-relaxed">
            총 {tasks.length}개 작업
            {filteredTasks.length !== tasks.length ? ` · 표시 ${filteredTasks.length}개` : ""}
            <span className="hidden sm:inline ml-2 text-xs text-gray-300">
              (⌘/Ctrl+K 전체 검색)
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setShowPalette(true)}
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50"
          >
            <Icon name="search" size={14} /> 검색 <kbd className="ml-1 text-[10px] bg-gray-100 px-1 rounded">⌘K</kbd>
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            + 새 작업
          </button>
        </div>
      </div>

      {/* 필터 행 */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="제목·설명·코멘트 검색..."
          className="flex-1 min-w-[180px] px-3 py-1.5 border border-gray-200 rounded-lg text-sm"
          style={{ color: "#e6e9ef" }}
        />
        <label
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs border rounded-lg cursor-pointer ${
            showOnlyMine ? "bg-blue-50 border-blue-300 text-blue-700" : "border-gray-200 text-gray-600 hover:bg-gray-50"
          }`}
        >
          <input
            type="checkbox"
            checked={showOnlyMine}
            onChange={(e) => setShowOnlyMine(e.target.checked)}
            disabled={!currentUserEmail}
            className="sr-only"
          />
          <Icon name="target" size={14} /> 내 태스크
        </label>
        <select
          value={filterAssignee}
          onChange={(e) => setFilterAssignee(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white"
          style={{ color: "#e6e9ef" }}
        >
          <option value="all">모든 담당자</option>
          {assigneeList.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={filterPriority}
          onChange={(e) => setFilterPriority(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white"
          style={{ color: "#e6e9ef" }}
        >
          <option value="all">모든 우선순위</option>
          <option value="urgent">Urgent</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select
          value={filterTeam}
          onChange={(e) => { setFilterTeam(e.target.value); setFilterSubTeam("all"); }}
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white"
          style={{ color: "#e6e9ef" }}
        >
          <option value="all">모든 팀</option>
          <option value="dev">💻 개발</option>
          <option value="art">🎨 아트</option>
          <option value="design">📐 기획</option>
          <option value="chat">💬 대화</option>
        </select>
        {filterTeam !== "all" && SUB_TEAMS[filterTeam as Team] && SUB_TEAMS[filterTeam as Team].length > 1 && (
          <select
            value={filterSubTeam}
            onChange={(e) => setFilterSubTeam(e.target.value)}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white"
            style={{ color: "#e6e9ef" }}
          >
            <option value="all">모든 분과</option>
            {SUB_TEAMS[filterTeam as Team].map((s) => (
              <option key={s} value={s}>{subTeamLabel(s)}</option>
            ))}
          </select>
        )}
        {hasAnyFilter && (
          <button
            onClick={() => {
              setFilterAssignee("all");
              setFilterPriority("all");
              setFilterTeam("all");
              setFilterSubTeam("all");
              setSearchQuery("");
              setShowOnlyMine(false);
              setActiveTags(new Set());
            }}
            className="text-xs text-blue-600 hover:underline"
          >
            전체 초기화
          </button>
        )}
      </div>

      {/* 태그 facet */}
      {tagFacets.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-gray-400 mr-1">태그</span>
          {tagFacets.map(([tag, count]) => {
            const on = activeTags.has(tag);
            return (
              <button
                key={tag}
                onClick={() => toggleTag(tag)}
                className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                  on
                    ? "bg-black text-white border-black"
                    : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
                }`}
              >
                [{tag}] <span className="opacity-60 tabular-nums">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-48 text-gray-400 text-sm">로딩 중...</div>
      )}

      {!loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {COLUMNS.map((col) => {
            const colTasks = tasksByStatus(col.id);
            const isOver = dragOver === col.id;
            return (
              <div
                key={col.id}
                className={`rounded-xl border-2 transition-colors ${
                  isOver ? "border-blue-300 bg-blue-50" : "border-transparent bg-gray-100"
                }`}
                onDragOver={(e) => onDragOver(e, col.id)}
                onDrop={(e) => onDrop(e, col.id)}
              >
                {/* Column header */}
                <div className={`${col.color} rounded-t-xl px-3 py-2.5 flex items-center justify-between border-b border-gray-200`} style={{ borderTop: `2px solid ${col.accent}` }}>
                  <span className="text-sm font-semibold text-gray-700 flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: col.accent }} /> {col.label}</span>
                  <span className="text-xs rounded-full px-2 py-0.5 font-semibold" style={{ background: col.accent + "22", color: col.accent }}>
                    {colTasks.length}
                  </span>
                </div>

                {/* Cards */}
                <div className="p-2 space-y-2 min-h-[200px]">
                  {colTasks.map((task) => {
                    const team = inferTeam(task);
                    const teamMeta = TEAM_META[team];
                    const isOverride = !!task.team_override;
                    const subTeam = inferSubTeam(task, team);
                    const subOverride = !!task.sub_team_override;
                    const showSub = subTeam && subTeam !== "general";
                    const designCount = (task.generated_design_ids || []).length;
                    return (
                    <div
                      key={task._id}
                      draggable
                      onDragStart={() => onDragStart(task._id!)}
                      onDragEnd={onDragEnd}
                      className={`bg-white rounded-lg border border-gray-200 p-3 shadow-sm cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow ${
                        dragging === task._id ? "opacity-50" : ""
                      }`}
                      onClick={() => setDetailTask(task)}
                    >
                      {/* Team badge + priority dot + title */}
                      <div className="flex items-start gap-2 mb-2">
                        <span
                          className={`mt-0.5 shrink-0 inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-medium ${teamMeta.bg} ${teamMeta.color}`}
                          title={`팀: ${teamMeta.label}${isOverride ? " (수동)" : " (자동 분류)"}${showSub ? " · 분과: " + subTeamLabel(subTeam) : ""}`}
                        >
                          <Icon name={TEAM_ICON[team] || "bot"} size={11} /> {teamMeta.label}
                          {showSub && (
                            <span className="ml-1 opacity-80">· {subTeamLabel(subTeam)}{subOverride && "·수동"}</span>
                          )}
                          {isOverride && !showSub && <span className="ml-0.5 opacity-60">·수동</span>}
                        </span>
                        <span
                          className={`mt-1.5 shrink-0 w-2 h-2 rounded-full ${priStyle(task.priority).dot}`}
                        />
                        <p className="text-sm font-medium leading-snug line-clamp-2 flex-1">{task.title}</p>
                        {task.has_image && (
                          <span className="shrink-0 text-gray-400" title="이미지 첨부됨 — 카드 클릭으로 상세 보기"><Icon name="paperclip" size={13} /></span>
                        )}
                        {designCount > 0 && (
                          <span className="shrink-0 inline-flex items-center gap-0.5 text-[10px] text-pink-700 bg-pink-50 border border-pink-200 rounded px-1.5 py-0.5" title={`생성된 이미지 ${designCount}개`}>
                            <Icon name="image" size={11} /> {designCount}
                          </span>
                        )}
                      </div>
                      {/* 카드 thumbnail 제거 — 6.4MB 페이로드 → 100KB로 축소 (2026-04-30). 이미지는 모달에서만. */}

                      {/* Description preview */}
                      {task.description && (
                        <p className="text-xs text-gray-400 line-clamp-2 mb-2 pl-4">{task.description}</p>
                      )}

                      {/* Footer */}
                      <div className="flex items-center justify-between pl-4">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${priStyle(task.priority).badge}`}
                          >
                            {task.priority}
                          </span>
                          {task.related_levels && (
                            <span className="text-xs text-gray-400 bg-gray-50 border border-gray-100 px-1.5 py-0.5 rounded-full">
                              Lv {task.related_levels}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {task.assignee && (
                            <span className="text-xs text-gray-400">{task.assignee}</span>
                          )}
                          {task.created_at && (
                            <span className="text-xs text-gray-300">{formatDate(task.created_at)}</span>
                          )}
                        </div>
                      </div>

                      {/* Quick move + delete */}
                      <div className="mt-2 ml-4 flex items-center gap-3">
                        {col.id !== "done" && (
                          <button
                            className="text-xs text-gray-400 hover:text-gray-700 transition-colors"
                            onClick={(e) => {
                              e.stopPropagation();
                              moveTask(task, nextStatus[col.id]);
                            }}
                          >
                            → {COLUMNS.find((c) => c.id === nextStatus[col.id])?.label}
                          </button>
                        )}
                        <button
                          className="text-xs hover:underline"
                          style={{color:"#dc2626"}}
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (!confirm(`"${task.title}" 삭제?`)) return;
                            await fetch(`/api/tasks/${task._id}`, { method: "DELETE" });
                            setTasks((prev) => prev.filter((t) => t._id !== task._id));
                          }}
                        >
                          삭제
                        </button>
                        {/* U2: Hermes 작업 ⛔중단/▶️재개 — 카드에서 바로 (모달 안 열고). assignee가 hermes 계열일 때만 */}
                        {/hermes|헤르메스/i.test(task.assignee || "") && (
                          task.hermes_stopped ? (
                            <button
                              className="text-xs hover:underline"
                              style={{ color: "#16a34a" }}
                              title="Hermes 작업 재개 (status를 '할 일'로 되돌려 이어서 진행)"
                              onClick={async (e) => {
                                e.stopPropagation();
                                const updated = { ...task, hermes_stopped: false, status: "todo" as Task["status"] };
                                setTasks((prev) => prev.map((t) => (t._id === task._id ? updated : t)));
                                await fetch("/api/tasks", {
                                  method: "PATCH",
                                  headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ _id: task._id, hermes_stopped: false, status: "todo" }),
                                }).catch(() => {});
                              }}
                            >
                              ▶️ 재개
                            </button>
                          ) : (
                            <button
                              className="text-xs hover:underline"
                              style={{ color: "#dc2626" }}
                              title="Hermes 처리 즉시 중단 (진행 중 단계는 끝나지만 다음 단계·재작업·질문 루프 차단)"
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!confirm(`"${task.title}" 의 Hermes 처리를 즉시 중단할까요?`)) return;
                                const updated = { ...task, hermes_stopped: true };
                                setTasks((prev) => prev.map((t) => (t._id === task._id ? updated : t)));
                                await fetch("/api/tasks", {
                                  method: "PATCH",
                                  headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ _id: task._id, hermes_stopped: true }),
                                }).catch(() => {});
                              }}
                            >
                              <span className="inline-flex items-center gap-1"><Icon name="ban" size={13} /> 중단</span>
                            </button>
                          )
                        )}
                        {/* 설명 요청: 생성자에게 DM — 자기 자신(내가 만든 태스크)에는 비활성 */}
                        {(() => {
                          const owner = (task.created_by_email || "").toLowerCase();
                          const me = currentUserEmail.toLowerCase();
                          const canAsk = !!owner && !!me && owner !== me;
                          if (!canAsk) return null;
                          return (
                            <button
                              className="text-xs text-amber-600 hover:underline"
                              title={`${owner}에게 설명 요청 DM 발송`}
                              onClick={async (e) => {
                                e.stopPropagation();
                                const extra = prompt(
                                  `이 태스크에 대해 생성자(${owner})에게 설명 요청 DM을 보냅니다.\n추가 메시지가 있으면 입력 (선택):`,
                                  ""
                                );
                                if (extra === null) return; // cancelled
                                const r = await fetch(`/api/tasks/${task._id}/ask-owner`, {
                                  method: "POST",
                                  headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ message: extra }),
                                });
                                const j = await r.json().catch(() => ({}));
                                if (!r.ok) {
                                  alert(j.error || "요청 실패");
                                  return;
                                }
                                const slackOk = j?.slack?.ok;
                                alert(
                                  slackOk
                                    ? `${owner} 에게 Slack DM을 보냈습니다 ✓\n코멘트도 기록되었습니다.`
                                    : `코멘트는 기록했지만 Slack DM은 실패했습니다 (${j?.slack?.error || "no route"}).\n생성자가 태스크 코멘트를 봐야 합니다.`
                                );
                              }}
                            >
                              <span className="inline-flex items-center gap-1"><Icon name="help" size={13} /> 설명 요청</span>
                            </button>
                          );
                        })()}
                      </div>
                    </div>
                    );
                  })}

                  {colTasks.length === 0 && (
                    <div className="flex items-center justify-center h-20 text-gray-300 text-xs">
                      비어 있음
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Task Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-3 overflow-y-auto">
          <div className="bg-white rounded-2xl p-6 w-full max-w-[480px] shadow-xl my-4">
            <h2 className="text-lg font-bold mb-4">새 작업 만들기</h2>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">제목 *</label>
                <input
                  ref={titleRef}
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) createTask(); }}
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                  placeholder="작업 제목"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">설명</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none"
                  rows={3}
                  placeholder="작업 설명 (선택)"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">담당자</label>
                  <select
                    value={form.assignee}
                    onChange={(e) => setForm({ ...form, assignee: e.target.value })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 bg-white"
                    style={{color:"#e6e9ef"}}
                  >
                    <option value="">담당자 선택</option>
                    {allowedAssignees.map((a) => (
                      <option key={a.name} value={a.name}>
                        {a.label || a.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">우선순위</label>
                  <select
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: e.target.value as Task["priority"] })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 bg-white"
                  >
                    <option value="urgent">Urgent</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">상태</label>
                  <select
                    value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value as Task["status"] })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 bg-white"
                  >
                    {COLUMNS.map((c) => (
                      <option key={c.id} value={c.id}>{c.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">관련 레벨</label>
                  <input
                    value={form.related_levels}
                    onChange={(e) => setForm({ ...form, related_levels: e.target.value })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                    placeholder="예: 1-5, 10"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">이미지 첨부 (선택, 최대 2MB)</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleImageAttach(f);
                  }}
                  className="mt-1 w-full text-xs text-gray-600 file:mr-2 file:px-3 file:py-1.5 file:rounded-lg file:border file:border-gray-200 file:bg-gray-50 file:text-gray-700 file:cursor-pointer hover:file:bg-gray-100"
                />
                {form.image_base64 && (
                  <div className="mt-2 relative inline-block">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={form.image_base64}
                      alt="첨부 미리보기"
                      className="max-h-32 rounded-lg border border-gray-200"
                    />
                    <button
                      type="button"
                      onClick={() => setForm({ ...form, image_base64: "" })}
                      className="absolute -top-2 -right-2 bg-white border border-gray-300 rounded-full w-5 h-5 text-xs flex items-center justify-center hover:bg-gray-50"
                    >
                      ×
                    </button>
                  </div>
                )}
              </div>

              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  파일 첨부 (.md, .json, .txt 등 — 파일당 256KB / 합계 5MB)
                </label>
                <input
                  type="file"
                  accept={ATTACH_ACCEPT}
                  multiple
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    files.forEach((f) => handleFileAttach(f));
                    e.target.value = "";
                  }}
                  className="mt-1 w-full text-xs text-gray-600 file:mr-2 file:px-3 file:py-1.5 file:rounded-lg file:border file:border-gray-200 file:bg-gray-50 file:text-gray-700 file:cursor-pointer hover:file:bg-gray-100"
                />
                {(form.attachments || []).length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {(form.attachments || []).map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center gap-2 text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1"
                      >
                        <span className="font-mono text-gray-500 uppercase text-[10px] px-1.5 py-0.5 bg-white border border-gray-200 rounded">
                          {a.kind}
                        </span>
                        <span className="text-gray-700 truncate flex-1" title={a.name}>{a.name}</span>
                        <span className="text-gray-400 tabular-nums">{(a.size / 1024).toFixed(1)}KB</span>
                        <button
                          type="button"
                          onClick={() => removeAttachment(a.id)}
                          className="text-gray-400 hover:text-red-500"
                          title="제거"
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-5">
              <button
                onClick={() => { setShowModal(false); setForm({ ...EMPTY_TASK }); }}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                취소
              </button>
              <button
                onClick={createTask}
                disabled={saving || !form.title.trim()}
                className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40"
              >
                {saving ? "저장 중..." : "만들기"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cmd+K 전역 검색 팔레트 */}
      {showPalette && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-start justify-center pt-[12vh] p-4"
             onClick={() => setShowPalette(false)}>
          <div className="bg-white rounded-xl w-full max-w-xl shadow-2xl overflow-hidden"
               onClick={(e) => e.stopPropagation()}>
            <div className="p-3 border-b border-gray-100 flex items-center gap-2">
              <span className="text-gray-400"><Icon name="search" size={16} /></span>
              <input
                autoFocus
                value={paletteQuery}
                onChange={(e) => setPaletteQuery(e.target.value)}
                placeholder="태스크 검색 (제목·설명·담당자·코멘트)..."
                className="flex-1 text-sm outline-none bg-transparent"
                style={{ color: "#e6e9ef" }}
              />
              <kbd className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded text-gray-500">ESC</kbd>
            </div>
            <div className="max-h-[60vh] overflow-y-auto">
              {(() => {
                const q = paletteQuery.trim().toLowerCase();
                const hits = q
                  ? tasks.filter((t) => {
                      const hay =
                        `${t.title} ${t.description} ${t.assignee || ""} ` +
                        (t.comments || []).slice(-3).map((c) => c.text || "").join(" ");
                      return hay.toLowerCase().includes(q);
                    }).slice(0, 25)
                  : tasks.slice(0, 15);
                if (hits.length === 0) {
                  return <div className="p-6 text-center text-sm text-gray-400">일치 태스크 없음</div>;
                }
                return hits.map((t) => {
                  const col = COLUMNS.find((c) => c.id === t.status);
                  return (
                    <button
                      key={t._id}
                      onClick={() => {
                        setDetailTask(t);
                        setShowPalette(false);
                        setPaletteQuery("");
                        if (typeof window !== "undefined" && t._id) {
                          history.replaceState(null, "", `#task=${t._id}`);
                        }
                      }}
                      className="w-full text-left px-4 py-2.5 hover:bg-gray-50 border-b border-gray-50 flex items-center gap-2"
                    >
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded font-medium flex-shrink-0 text-gray-700"
                        style={{ backgroundColor: "rgba(0,0,0,0.05)" }}
                      >
                        {col?.label || t.status}
                      </span>
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${priStyle(t.priority).dot}`} />
                      <span className="text-sm text-gray-800 truncate flex-1">{t.title}</span>
                      <span className="text-xs text-gray-400 flex-shrink-0">{t.assignee}</span>
                    </button>
                  );
                });
              })()}
            </div>
            <div className="p-2 border-t border-gray-100 text-[11px] text-gray-400 flex items-center justify-between">
              <span>클릭하면 상세 열림 + URL에 #task=... 복사됨</span>
              <span>{paletteQuery ? `"${paletteQuery}"` : `최근 ${Math.min(15, tasks.length)}개`}</span>
            </div>
          </div>
        </div>
      )}

      {/* Detail / Edit / Comment Modal */}
      {detailTask && (
        <DetailModal
          task={detailTask}
          columns={COLUMNS}
          priorityStyles={PRIORITY_STYLES}
          allowedAssignees={allowedAssignees}
          onClose={() => setDetailTask(null)}
          onUpdate={async (patch) => {
            await fetch("/api/tasks", {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ _id: detailTask._id, ...patch }),
            });
            const updated = { ...detailTask, ...patch };
            setTasks((prev) => prev.map((t) => (t._id === detailTask._id ? updated : t)));
            setDetailTask(updated);
          }}
          onStatusChange={(newStatus) => {
            moveTask(detailTask, newStatus);
            setDetailTask({ ...detailTask, status: newStatus });
          }}
          onAddComment={async (text, author) => {
            await fetch("/api/tasks", {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ _id: detailTask._id, add_comment: { text, author } }),
            });
            const newComment: Comment = { text, author, created_at: new Date().toISOString() };
            const updated = { ...detailTask, comments: [...(detailTask.comments || []), newComment] };
            setTasks((prev) => prev.map((t) => (t._id === detailTask._id ? updated : t)));
            setDetailTask(updated);
          }}
          onDeleteComment={async (index) => {
            if (!confirm("댓글 삭제?")) return;
            await fetch("/api/tasks", {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ _id: detailTask._id, delete_comment_index: index }),
            });
            const updated = {
              ...detailTask,
              comments: (detailTask.comments || []).filter((_, i) => i !== index),
            };
            setTasks((prev) => prev.map((t) => (t._id === detailTask._id ? updated : t)));
            setDetailTask(updated);
          }}
        />
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Detail / Edit / Comment Modal — 별도 컴포넌트
// ───────────────────────────────────────────────────────────────
function DetailModal({
  task,
  columns,
  priorityStyles,
  allowedAssignees,
  onClose,
  onUpdate,
  onStatusChange,
  onAddComment,
  onDeleteComment,
}: {
  task: Task;
  columns: Array<{ id: Task["status"]; label: string }>;
  priorityStyles: Record<Task["priority"], { badge: string; dot: string }>;
  allowedAssignees: AssigneeOption[];
  onClose: () => void;
  onUpdate: (patch: Partial<Task>) => Promise<void>;
  onStatusChange: (status: Task["status"]) => void;
  onAddComment: (text: string, author: string) => Promise<void>;
  onDeleteComment: (index: number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    title: task.title,
    description: task.description,
    assignee: task.assignee,
    priority: task.priority,
    related_levels: task.related_levels,
  });
  const [saving, setSaving] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [commentAuthor, setCommentAuthor] = useState("");
  const [addingComment, setAddingComment] = useState(false);

  // task 변경 시 editForm 동기화
  useEffect(() => {
    setEditForm({
      title: task.title,
      description: task.description,
      assignee: task.assignee,
      priority: task.priority,
      related_levels: task.related_levels,
    });
  }, [task]);

  async function saveEdit() {
    setSaving(true);
    try {
      await onUpdate(editForm);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleAddComment() {
    if (!commentText.trim()) return;
    setAddingComment(true);
    try {
      await onAddComment(commentText.trim(), commentAuthor.trim() || "익명");
      setCommentText("");
    } finally {
      setAddingComment(false);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-3 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl w-full max-w-[560px] shadow-xl my-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white z-10 px-6 py-4 border-b border-gray-100">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${(priorityStyles[task.priority] || priorityStyles.medium).dot}`} />
              {editing ? (
                <input
                  value={editForm.title}
                  onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                  className="text-lg font-bold w-full border-b border-blue-300 focus:outline-none"
                  style={{ color: "#e6e9ef" }}
                />
              ) : (
                <h2 className="text-lg font-bold leading-snug truncate">{task.title}</h2>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0 ml-2">
              <button
                onClick={() => setEditing(!editing)}
                className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                  editing ? "bg-blue-50 border-blue-300 text-blue-600" : "border-gray-200 hover:bg-gray-50"
                }`}
                style={{ color: editing ? undefined : "#e6e9ef" }}
              >
                {editing ? "취소" : <span className="inline-flex items-center gap-1"><Icon name="edit" size={13} /> 편집</span>}
              </button>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
            </div>
          </div>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Edit fields */}
          {editing ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase">담당자</label>
                  <select
                    value={editForm.assignee}
                    onChange={(e) => setEditForm({ ...editForm, assignee: e.target.value })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    style={{ color: "#e6e9ef" }}
                  >
                    <option value="">담당자 선택</option>
                    {allowedAssignees.map((a) => (
                      <option key={a.name} value={a.name}>
                        {a.label || a.name}
                      </option>
                    ))}
                    {/* 기존 assignee 값이 목록에 없으면 보존 (레거시) */}
                    {editForm.assignee &&
                      !allowedAssignees.some((a) => a.name === editForm.assignee) && (
                        <option value={editForm.assignee}>
                          {editForm.assignee} (레거시)
                        </option>
                      )}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase">우선순위</label>
                  <select
                    value={editForm.priority}
                    onChange={(e) => setEditForm({ ...editForm, priority: e.target.value as Task["priority"] })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    style={{ color: "#e6e9ef" }}
                  >
                    <option value="urgent">Urgent</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase">설명</label>
                <textarea
                  value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none"
                  rows={4}
                  style={{ color: "#e6e9ef" }}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase">관련 레벨</label>
                <input
                  value={editForm.related_levels}
                  onChange={(e) => setEditForm({ ...editForm, related_levels: e.target.value })}
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                  style={{ color: "#e6e9ef" }}
                />
              </div>
              <button
                onClick={saveEdit}
                disabled={saving || !editForm.title.trim()}
                className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40"
              >
                {saving ? "저장 중..." : "저장"}
              </button>
            </div>
          ) : (
            <>
              {/* View mode */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${(priorityStyles[task.priority] || priorityStyles.medium).badge}`}>
                  {task.priority}
                </span>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                  {columns.find((c) => c.id === task.status)?.label}
                </span>
                {(() => {
                  const team = inferTeam(task);
                  const meta = TEAM_META[team];
                  return (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium border ${meta.bg} ${meta.color}`}
                      title={task.team_override ? "수동 재배정됨" : "자동 분류"}
                    >
                      {meta.emoji} {meta.label}
                      {task.team_override && <span className="ml-1 opacity-60">·수동</span>}
                    </span>
                  );
                })()}
                {task.assignee && <span className="text-xs text-gray-500">{task.assignee}</span>}
                {task.hermes_stopped && (
                  <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-700 border border-red-200">
                    ⛔ 중단됨
                  </span>
                )}
              </div>

              {/* Hermes 작업 중단 / 재개 — assignee가 hermes 계열일 때만 노출 */}
              {/hermes|헤르메스/i.test(task.assignee || "") && (
                <div className="flex items-center gap-2">
                  {!task.hermes_stopped ? (
                    <button
                      onClick={async () => {
                        if (!confirm("이 작업에 대한 Hermes 처리를 즉시 중단할까요?\n진행 중인 단계는 끝나지만, 다음 단계·재작업·질문 루프는 차단됩니다.")) return;
                        await onUpdate({ hermes_stopped: true });
                        await onAddComment("⛔ 사용자가 작업을 중단했습니다. (Hermes 처리 일시 정지 — ▶️ 재개 전까지 어떤 이벤트에도 반응하지 않음)", "hermes");
                      }}
                      className="px-3 py-1.5 text-xs font-medium bg-red-600 text-white rounded-lg hover:bg-red-700"
                    >
                      ⛔ 작업 중단
                    </button>
                  ) : (
                    <button
                      onClick={async () => {
                        if (!confirm("작업을 재개할까요? (status가 '할 일'로 돌아가 Hermes가 이어서 진행합니다)")) return;
                        // 단일 PATCH로 플래그 해제 + status 변경 → 단일 change event (재개 시 이중 트리거 방지).
                        // 별도 코멘트는 추가하지 않음 — watcher가 '📋 처리 시작합니다'를 곧바로 남김.
                        await onUpdate({ hermes_stopped: false, status: "todo" });
                      }}
                      className="px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700"
                    >
                      ▶️ 작업 재개
                    </button>
                  )}
                  <span className="text-[10px] text-gray-400">폭주/무한루프 시 즉시 정지</span>
                </div>
              )}

              {/* 팀 재배정 */}
              <div className="flex items-center gap-2 text-xs flex-wrap">
                <span className="text-gray-500">팀 재배정:</span>
                <select
                  value={task.team || "auto"}
                  onChange={async (e) => {
                    const newTeam = e.target.value as Team;
                    const isAuto = newTeam === "auto";
                    // 팀이 바뀌면 sub_team override는 해제 (새 팀의 기본 분과로 PM이 다시 결정)
                    await onUpdate({
                      team: isAuto ? undefined : newTeam,
                      team_override: !isAuto,
                      sub_team: undefined,
                      sub_team_override: false,
                    });
                  }}
                  className="px-2 py-1 text-xs border border-gray-200 rounded-lg bg-white"
                  style={{ color: "#e6e9ef" }}
                >
                  <option value="auto">🤖 자동 (Translator)</option>
                  <option value="dev">💻 개발</option>
                  <option value="art">🎨 아트</option>
                  <option value="design">📐 기획</option>
                  <option value="chat">💬 대화</option>
                </select>
                {task.team_override && (
                  <span className="text-[10px] text-amber-600">Translator 덮어쓰기 방지 ON</span>
                )}
              </div>

              {/* 분과(sub_team) 재배정 — team이 결정된 경우만 노출 */}
              {(() => {
                const t = inferTeam(task);
                const opts = SUB_TEAMS[t] || ["general"];
                if (opts.length <= 1) return null;
                return (
                  <div className="flex items-center gap-2 text-xs flex-wrap">
                    <span className="text-gray-500">분과 재배정:</span>
                    <select
                      value={task.sub_team || "auto"}
                      onChange={async (e) => {
                        const v = e.target.value;
                        const isAuto = v === "auto";
                        await onUpdate({
                          sub_team: isAuto ? undefined : v,
                          sub_team_override: !isAuto,
                        });
                      }}
                      className="px-2 py-1 text-xs border border-gray-200 rounded-lg bg-white"
                      style={{ color: "#e6e9ef" }}
                    >
                      <option value="auto">🤖 자동 (PM)</option>
                      {opts.map((s) => (
                        <option key={s} value={s}>{subTeamLabel(s)}</option>
                      ))}
                    </select>
                    {task.sub_team_override && (
                      <span className="text-[10px] text-amber-600">PM 덮어쓰기 방지 ON</span>
                    )}
                  </div>
                );
              })()}

              {task.description && (
                <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{task.description}</p>
              )}

              {task.image_base64 && (
                <div className="rounded-lg overflow-hidden border border-gray-200">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={task.image_base64} alt="" className="w-full max-h-72 object-contain bg-gray-50" />
                </div>
              )}

              {(task.attachments || []).length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">첨부 파일</p>
                  {(task.attachments || []).map((a) => (
                    <details key={a.id} className="border border-gray-200 rounded-lg bg-gray-50">
                      <summary className="cursor-pointer px-3 py-2 text-xs flex items-center gap-2 hover:bg-gray-100">
                        <span className="font-mono uppercase text-[10px] px-1.5 py-0.5 bg-white border border-gray-200 rounded">{a.kind}</span>
                        <span className="text-gray-700 truncate flex-1" title={a.name}>{a.name}</span>
                        <span className="text-gray-400 tabular-nums">{(a.size / 1024).toFixed(1)}KB</span>
                      </summary>
                      <pre className="px-3 py-2 text-xs text-gray-800 whitespace-pre-wrap break-words max-h-72 overflow-auto border-t border-gray-200 bg-white font-mono">
                        {a.kind === "json"
                          ? (() => { try { return JSON.stringify(JSON.parse(a.content), null, 2); } catch { return a.content; } })()
                          : a.content}
                      </pre>
                    </details>
                  ))}
                </div>
              )}

              {task.related_levels && (
                <div className="text-sm text-gray-500">
                  <span className="font-medium text-gray-700">관련 레벨:</span> {task.related_levels}
                </div>
              )}

              {/* Task에서 생성된 이미지 — 양방향 연결 */}
              <GeneratedDesigns taskId={String(task._id || "")} ids={task.generated_design_ids || []} />

              {/* design/level 4팀 경쟁 결과 — task_id로 fetch */}
              <CompetitiveLevels taskId={String(task._id || "")} levelIds={task.generated_level_ids || []} />
            </>
          )}

          {/* Status buttons */}
          <div className="pt-3 border-t border-gray-100">
            <p className="text-xs text-gray-400 mb-2">상태 변경</p>
            <div className="flex flex-wrap gap-2">
              {columns.map((col) => (
                <button
                  key={col.id}
                  onClick={() => onStatusChange(col.id)}
                  className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                    task.status === col.id
                      ? "bg-black text-white border-black"
                      : "border-gray-200 hover:bg-gray-50"
                  }`}
                  style={{ color: task.status === col.id ? undefined : "#e6e9ef" }}
                >
                  {col.label}
                </button>
              ))}
            </div>
          </div>

          {/* Comments */}
          <div className="pt-3 border-t border-gray-100">
            <p className="text-xs text-gray-400 mb-3">
              댓글 {task.comments?.length ? `(${task.comments.length})` : ""}
            </p>

            {/* Comment list */}
            {task.comments && task.comments.length > 0 && (
              <div className="space-y-3 mb-4 max-h-60 overflow-y-auto">
                {task.comments.map((c, i) => (
                  <div key={i} className="bg-gray-50 rounded-lg p-3 group">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold" style={{ color: "#e6e9ef" }}>{c.author}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-400">
                          {new Date(c.created_at).toLocaleString("ko-KR", {
                            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                          })}
                        </span>
                        <button
                          onClick={() => onDeleteComment(i)}
                          className="text-xs text-red-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                          title="댓글 삭제"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{c.text}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Add comment */}
            <div className="flex flex-col gap-2">
              <div className="flex gap-2">
                <input
                  value={commentAuthor}
                  onChange={(e) => setCommentAuthor(e.target.value)}
                  placeholder="이름"
                  className="w-24 shrink-0 px-2.5 py-2 text-xs border border-gray-200 rounded-lg"
                  style={{ color: "#e6e9ef" }}
                />
                <input
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) handleAddComment(); }}
                  placeholder="댓글 작성... (Enter로 전송)"
                  className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg"
                  style={{ color: "#e6e9ef" }}
                />
                <button
                  onClick={handleAddComment}
                  disabled={addingComment || !commentText.trim()}
                  className="px-3 py-2 text-xs bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40 shrink-0"
                >
                  {addingComment ? "..." : "전송"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Task에서 생성된 이미지 썸네일 — 갤러리로 연결
// ───────────────────────────────────────────────────────────────
interface GalleryThumb {
  _id: string;
  prompt: string;
  images: Array<{ filename: string }>;
  created_at: string;
}

function GeneratedDesigns({ taskId, ids }: { taskId: string; ids: string[] }) {
  const [items, setItems] = useState<GalleryThumb[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    // /api/designs?task_id=... 로 이 task에서 생성된 이미지 조회 (양방향 중 Task→Gallery 방향)
    fetch(`/api/designs?task_id=${encodeURIComponent(taskId)}&limit=24`)
      .then((r) => r.json())
      .then((j) => {
        const arr = Array.isArray(j?.designs) ? j.designs : [];
        setItems(arr);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [taskId, ids.length]); // generated_design_ids 변경 시 재조회

  if (!taskId) return null;
  if (!loading && items.length === 0 && ids.length === 0) return null;

  return (
    <div className="pt-3 border-t border-gray-100">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          🖼 생성된 이미지 {items.length > 0 ? `(${items.length})` : ""}
        </p>
        <a
          href={`/gallery?task_id=${encodeURIComponent(taskId)}`}
          className="text-[11px] text-blue-600 hover:underline"
        >
          갤러리에서 보기 →
        </a>
      </div>
      {loading && <p className="text-xs text-gray-400">로딩 중...</p>}
      {!loading && items.length === 0 && ids.length > 0 && (
        <p className="text-xs text-gray-400">연결된 이미지({ids.length}개)가 있으나 조회되지 않음</p>
      )}
      {items.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {items.map((d) => {
            const first = d.images?.[0];
            if (!first) return null;
            return (
              <a
                key={d._id}
                href={`/gallery#design=${d._id}`}
                className="group relative block rounded-lg overflow-hidden border border-gray-200 hover:border-pink-400 bg-gray-50"
                title={d.prompt}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/designs/image/${first.filename}`}
                  alt={d.prompt.slice(0, 40)}
                  className="w-full aspect-square object-cover group-hover:opacity-80 transition-opacity"
                  loading="lazy"
                />
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <p className="text-[10px] text-white line-clamp-2 leading-tight">{d.prompt}</p>
                </div>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────
// CompetitiveLevels — 4팀 경쟁 레벨 비교 + 별점
// ─────────────────────────────────────────────────────────────────────
interface LevelItem {
  _id: string;
  name?: string;
  team_id?: string | null;
  pattern_chosen?: string | null;
  png_filename: string;
  width: number;
  height: number;
  user_score?: number | null;
}

const TEAM_META_LEVEL: Record<string, { label: string; icon: string; color: string }> = {
  hermes_native: { label: "Hermes Native",   icon: "🌀", color: "border-indigo-400 bg-indigo-50" },
  geometric:     { label: "Geometric",       icon: "🔷", color: "border-emerald-400 bg-emerald-50" },
  organic:       { label: "Organic",         icon: "🌊", color: "border-amber-400 bg-amber-50" },
  tile:          { label: "Tile / Pixel-Art", icon: "🧱", color: "border-pink-400 bg-pink-50" },
  balloonflow:   { label: "BalloonFlow",     icon: "🎯", color: "border-cyan-400 bg-cyan-50" },
};
const TEAM_ORDER = ["hermes_native", "geometric", "organic", "tile", "balloonflow"];

function CompetitiveLevels({ taskId, levelIds }: { taskId: string; levelIds: string[] }) {
  const [items, setItems] = useState<LevelItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingTeam, setSavingTeam] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/levels?task_id=${encodeURIComponent(taskId)}&limit=20`);
      const j = await r.json();
      const arr = Array.isArray(j?.levels) ? j.levels : [];
      // team_id 가진 항목만 (4팀 결과)
      setItems(arr.filter((x: LevelItem) => x.team_id));
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    refetch();
  }, [refetch, levelIds.length]);

  if (!taskId) return null;
  if (!loading && items.length === 0) return null;

  const setStar = async (item: LevelItem, score: number) => {
    setSavingTeam(item._id);
    try {
      const r = await fetch(`/api/levels/${item._id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_score: score }),
      });
      if (r.ok) await refetch();
    } finally {
      setSavingTeam(null);
    }
  };

  // 팀 순서대로 정렬 (TEAM_ORDER 기반)
  const ordered = TEAM_ORDER
    .map((tid) => items.find((x) => x.team_id === tid))
    .filter((x): x is LevelItem => Boolean(x));
  const stragglers = items.filter((x) => x.team_id && !TEAM_ORDER.includes(x.team_id));
  const all = [...ordered, ...stragglers];

  return (
    <div className="pt-3 border-t border-gray-100">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          🏁 {TEAM_ORDER.length}팀 경쟁 결과 ({items.length}/{TEAM_ORDER.length})
        </p>
        <a href={`/levels?task_id=${encodeURIComponent(taskId)}`} className="text-[11px] text-indigo-600 hover:underline">
          /levels 에서 보기 →
        </a>
      </div>
      <p className="text-[11px] text-gray-400 mb-2">
        같은 spec, 다른 알고리즘. 1~5 별점으로 평가하면 hermes_design_team_scores 누적 → 약팀 자동 개선.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {all.map((lv) => {
          const meta = (lv.team_id && TEAM_META_LEVEL[lv.team_id]) || {
            label: lv.team_id || "?", icon: "❓", color: "border-gray-300 bg-gray-50",
          };
          return (
            <div key={lv._id} className={`rounded-lg border-2 p-2 ${meta.color}`}>
              <a
                href={`/levels#level=${lv._id}`}
                className="block aspect-square overflow-hidden rounded border border-gray-200 bg-white"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/levels/image/${lv.png_filename}`}
                  alt={meta.label}
                  className="w-full h-full object-contain"
                  loading="lazy"
                />
              </a>
              <div className="mt-1.5 flex items-center justify-between gap-1">
                <span className="text-[11px] font-semibold truncate">
                  {meta.icon} {meta.label}
                </span>
                <span className="text-[9px] text-gray-500 font-mono shrink-0">
                  {lv.pattern_chosen || "?"}
                </span>
              </div>
              <div className="mt-1.5 flex items-center gap-0.5">
                {[1, 2, 3, 4, 5].map((n) => {
                  const filled = (lv.user_score || 0) >= n;
                  const isSaving = savingTeam === lv._id;
                  return (
                    <button
                      key={n}
                      disabled={isSaving}
                      onClick={() => setStar(lv, n)}
                      className={`text-lg leading-none transition-transform hover:scale-110 ${
                        filled ? "text-yellow-400" : "text-gray-300 hover:text-yellow-300"
                      } disabled:opacity-50`}
                      title={`${n}점`}
                    >
                      ★
                    </button>
                  );
                })}
                {lv.user_score ? (
                  <span className="ml-1 text-[10px] text-gray-500">{lv.user_score}/5</span>
                ) : (
                  <span className="ml-1 text-[10px] text-gray-400">미평가</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
