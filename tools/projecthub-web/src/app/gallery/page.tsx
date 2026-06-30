"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";

interface DesignImage {
  filename: string;
  width: number;
  height: number;
}

interface Design {
  _id: string;
  prompt: string;
  user_prompt?: string;
  tags: string[];
  model: string;
  size: string;
  n: number;
  images: DesignImage[];
  created_by_email: string;
  created_at: string;
  source?: "task" | "gallery";
  task_id?: string;
  task_title?: string;
  reference_filename?: string | null;
  has_ref?: boolean;
  mode_9slice?: boolean;
  border_px?: number;
  /** 정통 9-slice 메타 — 이미지 변형 X, Unity Sprite Border 입력값으로 사용 */
  nine_slice?: {
    top: number;
    right: number;
    bottom: number;
    left: number;
    image_width: number;
    image_height: number;
    set_at: string;
    set_by: string;
  } | null;
  /** Frame Cutout 변환 시 원본 디자인 역참조 */
  source_design_id?: string | null;
  /** 사용자별 즐겨찾기 (key는 email의 .@를 _로 치환) */
  stars?: Record<string, boolean>;
  /** 사용자별 별점 (0~5) */
  star_ratings?: Record<string, number>;
  /** 디자인 코멘트 스레드 */
  comments?: Array<{ id: string; text: string; author: string; author_email: string; created_at: string }>;
  /** 인페인팅 결과 디자인 표시 */
  inpaint?: boolean;
}

/** 사용자 이메일을 DB 키 형식으로 (. @ → _) */
function emailKey(email: string): string {
  return (email || "").replace(/[.@]/g, "_");
}

interface Facets {
  tags: Array<{ tag: string; count: number }>;
  authors: string[];
}

type SortKey = "newest" | "oldest" | "prompt";

const SIZES = [
  { value: "auto", label: "자동 (모델 결정)" },
  { value: "1024x1024", label: "1024×1024 (정방형)" },
  { value: "1024x1536", label: "1024×1536 (세로)" },
  { value: "1536x1024", label: "1536×1024 (가로)" },
  { value: "2048x2048", label: "2048×2048 (고해상도 정방형)" },
  { value: "512x512", label: "512×512 (저해상도)" },
];
const QUALITIES = [
  { value: "auto", label: "자동" },
  { value: "high", label: "high (고품질, 느림)" },
  { value: "medium", label: "medium (표준)" },
  { value: "low", label: "low (빠름, 저렴)" },
];
const COUNTS = [1, 2, 3, 4];

function imgUrl(filename: string): string {
  return `/api/designs/image/${filename}`;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

export default function GalleryPage() {
  const [designs, setDesigns] = useState<Design[]>([]);
  const [facets, setFacets] = useState<Facets>({ tags: [], authors: [] });
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // 필터
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [tagFilter, setTagFilter] = useState<string>("");
  const [authorFilter, setAuthorFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [taskIdFilter, setTaskIdFilter] = useState<string>("");

  // 생성 모달
  const [showCreate, setShowCreate] = useState(false);
  const [gPrompt, setGPrompt] = useState("");
  const [gN, setGN] = useState(1);
  const [gSize, setGSize] = useState("auto");
  const [gQuality, setGQuality] = useState("auto");
  const [gTags, setGTags] = useState("");
  const [gRefImage, setGRefImage] = useState<string>("");  // data URL
  const [gRefName, setGRefName] = useState<string>("");
  const [g9Slice, setG9Slice] = useState(false);
  const [gBorderPx, setGBorderPx] = useState(96);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  // 상세 모달
  const [detail, setDetail] = useState<Design | null>(null);
  const [zoomImage, setZoomImage] = useState<string | null>(null);
  // 9-slice 변환 모달
  const [slicing, setSlicing] = useState<Design | null>(null);
  const [sliceBorder, setSliceBorder] = useState<number>(96);
  const [slicing4Side, setSlicing4Side] = useState<boolean>(false);
  const [sliceTop, setSliceTop] = useState<number>(96);
  const [sliceBottom, setSliceBottom] = useState<number>(96);
  const [sliceLeft, setSliceLeft] = useState<number>(96);
  const [sliceRight, setSliceRight] = useState<number>(96);
  const [slicingBusy, setSlicingBusy] = useState<boolean>(false);
  // 즐겨찾기 필터
  const [showStarredOnly, setShowStarredOnly] = useState<boolean>(false);
  const [minRating, setMinRating] = useState<number>(0);
  const [me, setMe] = useState<string>("");
  // 인페인팅 모달
  const [inpaintTarget, setInpaintTarget] = useState<Design | null>(null);
  // 코멘트 입력
  const [commentText, setCommentText] = useState("");

  // 현재 로그인 사용자 이메일 (별·코멘트 본인 식별)
  useEffect(() => {
    fetch("/api/auth/session")
      .then((r) => r.json())
      .then((j) => setMe((j?.user?.email || "").toLowerCase()))
      .catch(() => {});
  }, []);

  // 별 토글
  async function toggleStar(d: Design) {
    if (!me) return;
    const key = emailKey(me);
    const cur = d.stars?.[key] || false;
    await fetch(`/api/designs/${d._id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ starred: !cur }),
    });
    fetchDesigns();
    if (detail && detail._id === d._id) {
      setDetail({ ...detail, stars: { ...(detail.stars || {}), [key]: !cur } });
    }
  }

  async function setRating(d: Design, r: number) {
    if (!me) return;
    const key = emailKey(me);
    await fetch(`/api/designs/${d._id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ star_rating: r }),
    });
    if (detail && detail._id === d._id) {
      setDetail({ ...detail, star_ratings: { ...(detail.star_ratings || {}), [key]: r } });
    }
    fetchDesigns();
  }

  async function postComment() {
    if (!detail || !commentText.trim()) return;
    try {
      const r = await fetch(`/api/designs/${detail._id}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: commentText.trim() }),
      });
      if (!r.ok) {
        console.error("[gallery] postComment failed:", r.status);
        alert("코멘트 등록에 실패했습니다.");
        return;
      }
      const j = await r.json();
      if (j.ok && j.comment) {
        setDetail({ ...detail, comments: [...(detail.comments || []), j.comment] });
        setCommentText("");
      } else {
        console.error("[gallery] postComment rejected:", j.error || j);
        alert("코멘트 등록에 실패했습니다.");
      }
    } catch (e) {
      console.error("[gallery] postComment error:", e);
      alert("코멘트 등록 중 오류가 발생했습니다.");
    }
  }

  async function deleteComment(cid: string) {
    if (!detail) return;
    if (!confirm("이 코멘트를 삭제할까요?")) return;
    await fetch(`/api/designs/${detail._id}/comments?cid=${cid}`, { method: "DELETE" });
    setDetail({ ...detail, comments: (detail.comments || []).filter((c) => c.id !== cid) });
  }

  const fetchDesigns = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      page: String(page),
      limit: "20",
      sort,
    });
    if (q.trim()) params.set("q", q.trim());
    if (tagFilter) params.set("tag", tagFilter);
    if (authorFilter) params.set("author", authorFilter);
    if (sourceFilter) params.set("source", sourceFilter);
    if (taskIdFilter) params.set("task_id", taskIdFilter);
    try {
      const r = await fetch(`/api/designs?${params}`);
      if (!r.ok) {
        setDesigns([]);
        return;
      }
      const j = await r.json();
      setDesigns(Array.isArray(j.designs) ? j.designs : []);
      setTotalPages(j.pages || 1);
      if (j.facets) setFacets(j.facets);
    } finally {
      setLoading(false);
    }
  }, [page, sort, q, tagFilter, authorFilter, sourceFilter, taskIdFilter]);

  useEffect(() => { fetchDesigns(); }, [fetchDesigns]);

  // 검색어 변경 시 1페이지로
  useEffect(() => { setPage(1); }, [q, sort, tagFilter, authorFilter, sourceFilter, taskIdFilter]);

  // URL query `?task_id=...` 로 진입 시 자동 필터
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sp = new URLSearchParams(window.location.search);
    const tid = sp.get("task_id");
    if (tid && /^[a-f0-9]{24}$/.test(tid)) setTaskIdFilter(tid);
  }, []);

  async function generate() {
    const prompt = gPrompt.trim();
    if (!prompt) return;
    setGenError("");
    setGenerating(true);
    try {
      const r = await fetch("/api/designs/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          n: gN,
          size: gSize,
          quality: gQuality,
          tags: gTags.split(",").map((t) => t.trim()).filter(Boolean),
          ref_image_base64: gRefImage || undefined,
          mode_9slice: g9Slice || undefined,
          border_px: g9Slice ? gBorderPx : undefined,
        }),
      });
      const j = await r.json();
      if (!r.ok) { setGenError(j.error || "생성 실패"); return; }
      setShowCreate(false);
      setGPrompt("");
      setGTags("");
      setGRefImage("");
      setGRefName("");
      setG9Slice(false);
      setPage(1);
      await fetchDesigns();
    } catch (e) {
      setGenError(e instanceof Error ? e.message : "생성 실패");
    } finally {
      setGenerating(false);
    }
  }

  function handleRefUpload(file: File) {
    if (file.size > 4 * 1024 * 1024) {
      setGenError("참조 이미지는 4MB 이하만 지원됩니다.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      setGRefImage(String(e.target?.result || ""));
      setGRefName(file.name);
    };
    reader.readAsDataURL(file);
  }

  async function deleteDesign(id: string) {
    if (!confirm("이 디자인을 삭제하시겠습니까?")) return;
    const r = await fetch(`/api/designs/${id}`, { method: "DELETE" });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      alert(j.error || "삭제 실패");
      return;
    }
    setDetail(null);
    await fetchDesigns();
  }

  const hasFilters = useMemo(() => Boolean(q || tagFilter || authorFilter || sourceFilter || taskIdFilter), [q, tagFilter, authorFilter, sourceFilter, taskIdFilter]);

  return (
    <div>
      <div className="mb-5 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2"><Icon name="palette" size={24} /> 디자인 갤러리</h1>
          <p className="text-sm text-gray-500 mt-1 leading-relaxed">GPT Image 2로 생성된 디자인 · 정렬 · 필터 · 검색 가능</p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="/levels"
            className="inline-flex items-center gap-1.5 px-3 py-2 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg text-sm font-medium hover:bg-indigo-100 transition-colors"
          >
            <Icon name="image" size={16} /> 레벨 갤러리 →
          </a>
          <button
            onClick={() => { setGenError(""); setShowCreate(true); }}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <Icon name="plus" size={16} /> 업로드
          </button>
        </div>
      </div>

      {/* 검색 + 정렬 + 필터 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
              <Icon name="search" size={16} />
            </span>
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="프롬프트 검색..."
              className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm"
              style={{ color: "#e6e9ef" }}
            />
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            style={{ color: "#e6e9ef" }}
          >
            <option value="newest">최신순</option>
            <option value="oldest">오래된순</option>
            <option value="prompt">프롬프트순</option>
          </select>
          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            style={{ color: "#e6e9ef" }}
          >
            <option value="">모든 태그</option>
            {facets.tags.map((t) => (
              <option key={t.tag} value={t.tag}>#{t.tag} ({t.count})</option>
            ))}
          </select>
          <select
            value={authorFilter}
            onChange={(e) => setAuthorFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            style={{ color: "#e6e9ef" }}
          >
            <option value="">모든 작성자</option>
            {facets.authors.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          {hasFilters && (
            <button
              onClick={() => {
                setQ(""); setTagFilter(""); setAuthorFilter(""); setSourceFilter(""); setTaskIdFilter("");
                if (typeof window !== "undefined") {
                  const u = new URL(window.location.href);
                  u.searchParams.delete("task_id");
                  history.replaceState(null, "", u.toString());
                }
              }}
              className="ml-auto text-xs text-blue-600 hover:underline"
            >
              초기화
            </button>
          )}
        </div>

        {/* 출처 필터 — pill chips */}
        <div className="flex flex-wrap items-center gap-2">
          {([
            { value: "", label: "전체" },
            { value: "gallery", label: "직접 생성" },
            { value: "task", label: "Task 생성" },
          ] as const).map((opt) => {
            const active = sourceFilter === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => setSourceFilter(opt.value)}
                className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  active
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Task 필터 배너 */}
      {taskIdFilter && (
        <div className="mb-4 flex items-center justify-between gap-2 bg-purple-50 border border-purple-200 rounded-lg px-3 py-2 text-sm">
          <div className="text-purple-800">
            🔗 Task에서 생성된 이미지만 표시 중
            <span className="ml-2 font-mono text-xs text-purple-500">#{taskIdFilter.slice(-8)}</span>
          </div>
          <div className="flex items-center gap-3">
            <a
              href={`/tasks#task=${taskIdFilter}`}
              className="text-xs text-purple-700 hover:underline"
            >
              원본 Task로 이동 →
            </a>
            <button
              onClick={() => {
                setTaskIdFilter("");
                if (typeof window !== "undefined") {
                  const u = new URL(window.location.href);
                  u.searchParams.delete("task_id");
                  history.replaceState(null, "", u.toString());
                }
              }}
              className="text-xs text-purple-600 hover:text-purple-800"
            >
              해제 ×
            </button>
          </div>
        </div>
      )}

      {/* 그리드 */}
      {/* 즐겨찾기 / 별점 필터 */}
      {me && (
        <div className="mb-3 flex items-center gap-3 text-xs text-gray-600">
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={showStarredOnly} onChange={(e) => setShowStarredOnly(e.target.checked)} />
            ⭐ 내 즐겨찾기만
          </label>
          <label className="flex items-center gap-1">
            최소 평점:
            <select
              value={minRating}
              onChange={(e) => setMinRating(parseInt(e.target.value, 10))}
              className="border border-gray-200 rounded px-2 py-0.5 text-xs"
              style={{ color: "#e6e9ef" }}
            >
              <option value={0}>전체</option>
              <option value={1}>★ 1+</option>
              <option value={2}>★★ 2+</option>
              <option value={3}>★★★ 3+</option>
              <option value={4}>★★★★ 4+</option>
              <option value={5}>★★★★★ 5</option>
            </select>
          </label>
        </div>
      )}

      {loading ? (
        <div className="text-sm text-gray-400 py-10 text-center">로딩 중...</div>
      ) : designs.length === 0 ? (
        <div className="text-sm text-gray-400 py-10 text-center">
          {hasFilters ? "검색 결과가 없습니다" : '아직 생성된 디자인이 없습니다. "+ 새 이미지 생성"으로 시작하세요.'}
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-2.5">
          {designs.filter((d) => {
            if (!me) return true;
            const k = emailKey(me);
            if (showStarredOnly && !d.stars?.[k]) return false;
            if (minRating > 0) {
              const r = d.star_ratings?.[k] ?? 0;
              if (r < minRating) return false;
            }
            return true;
          }).map((d) => {
            const thumb = d.images?.[0];
            if (!thumb) return null;
            const myKey = emailKey(me);
            const isStarred = !!(d.stars && d.stars[myKey]);
            const myRating = d.star_ratings?.[myKey] || 0;
            return (
              <button
                key={d._id}
                onClick={() => setDetail(d)}
                className="group relative aspect-square overflow-hidden rounded-lg border border-gray-200 bg-gray-100 cursor-pointer hover:ring-2 hover:ring-blue-500 transition-shadow text-left"
                title={d.prompt}
              >
                {/* 즐겨찾기 토글 — 좌상단 */}
                {me && (
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleStar(d); }}
                    className="absolute top-1.5 left-1.5 z-10 text-base hover:scale-110 transition-transform drop-shadow"
                    title={isStarred ? "즐겨찾기 해제" : "즐겨찾기"}
                  >
                    {isStarred ? "⭐" : "☆"}
                  </button>
                )}
                {/* 내 별점 (있으면 좌하단) */}
                {myRating > 0 && (
                  <span className="absolute bottom-1.5 left-1.5 z-10 text-[10px] bg-yellow-400/90 text-yellow-900 px-1.5 py-0.5 rounded-full font-bold">
                    ★ {myRating}
                  </span>
                )}
                {d.comments && d.comments.length > 0 && (
                  <span className="absolute bottom-1.5 right-1.5 z-10 inline-flex items-center gap-0.5 text-[10px] bg-blue-500/90 text-white px-1.5 py-0.5 rounded-full">
                    <Icon name="chat" size={10} /> {d.comments.length}
                  </span>
                )}
                {d.source === "task" && (
                  <span
                    className="absolute top-1.5 right-1.5 z-10 text-[10px] bg-purple-500 text-white px-1.5 py-0.5 rounded-full font-medium"
                    title={`Task: ${d.task_title || d.task_id}`}
                  >
                    Task
                  </span>
                )}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={imgUrl(thumb.filename)}
                  alt={d.prompt.slice(0, 50)}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              </button>
            );
          })}
        </div>
      )}

      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded disabled:opacity-40"
          >
            ← 이전
          </button>
          <span className="text-sm text-gray-500 tabular-nums">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded disabled:opacity-40"
          >
            다음 →
          </button>
        </div>
      )}

      {/* 생성 모달 */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4" onClick={() => !generating && setShowCreate(false)}>
          <div className="bg-white rounded-xl max-w-lg w-full p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-bold mb-3">새 이미지 생성</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">프롬프트 <span className="text-red-500">*</span></label>
                <textarea
                  value={gPrompt}
                  onChange={(e) => setGPrompt(e.target.value)}
                  rows={4}
                  placeholder="예: pastel pink balloon character with a smiley face, game UI asset, transparent background"
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                  style={{ color: "#e6e9ef" }}
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">매수</label>
                  <select
                    value={gN}
                    onChange={(e) => setGN(parseInt(e.target.value, 10))}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    style={{ color: "#e6e9ef" }}
                  >
                    {COUNTS.map((n) => <option key={n} value={n}>{n}장</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">크기</label>
                  <select
                    value={gSize}
                    onChange={(e) => setGSize(e.target.value)}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    style={{ color: "#e6e9ef" }}
                  >
                    {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">품질</label>
                  <select
                    value={gQuality}
                    onChange={(e) => setGQuality(e.target.value)}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    style={{ color: "#e6e9ef" }}
                  >
                    {QUALITIES.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
                  </select>
                </div>
              </div>

              {/* 참조 이미지 업로드 */}
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  참조 이미지 (선택, 최대 4MB)
                </label>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  업로드하면 <code className="bg-gray-100 px-1 rounded">images/edits</code> 엔드포인트 사용 — 업로드 이미지의 스타일/컴포지션을 프롬프트에 맞춰 변형
                </p>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleRefUpload(f);
                    e.target.value = "";
                  }}
                  className="mt-1 w-full text-xs text-gray-600 file:mr-2 file:px-3 file:py-1.5 file:rounded-lg file:border file:border-gray-200 file:bg-gray-50 file:text-gray-700 file:cursor-pointer hover:file:bg-gray-100"
                />
                {gRefImage && (
                  <div className="mt-2 flex items-center gap-2 p-2 border border-gray-200 rounded-lg bg-gray-50">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={gRefImage} alt="참조" className="w-16 h-16 object-cover rounded border border-gray-200" />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-gray-700 truncate" title={gRefName}>{gRefName}</div>
                      <div className="text-[10px] text-gray-400">엔드포인트 전환됨: edits</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => { setGRefImage(""); setGRefName(""); }}
                      className="text-xs text-red-600 hover:bg-red-50 px-2 py-1 rounded"
                    >
                      제거
                    </button>
                  </div>
                )}
              </div>

              {/* 9-Slice 모드 — Unity Sprite Border 용 UI 이미지 */}
              <div className="border border-amber-200 rounded-lg p-3 bg-amber-50/40">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={g9Slice}
                    onChange={(e) => setG9Slice(e.target.checked)}
                  />
                  <span className="text-sm font-semibold text-amber-800">🧩 9-Slice 모드</span>
                  <span className="text-[11px] text-amber-700/70">
                    Unity Sprite Border용 UI — flat fill 강제, 자글거림 방지
                  </span>
                </label>
                {g9Slice && (
                  <div className="mt-2 flex items-center gap-2 text-xs text-amber-900">
                    <label className="flex items-center gap-1">
                      Border:
                      <input
                        type="number"
                        min={8}
                        max={256}
                        step={8}
                        value={gBorderPx}
                        onChange={(e) => setGBorderPx(Math.max(8, Math.min(256, parseInt(e.target.value) || 96)))}
                        className="w-20 border border-amber-300 rounded px-2 py-1 text-xs"
                        style={{ color: "#e6e9ef" }}
                      />
                      px
                    </label>
                    <span className="text-[10px] text-amber-700">
                      → Unity Sprite import 시 4면 모두 이 값 적용 (size는 1024×1024로 자동)
                    </span>
                  </div>
                )}
                <p className="text-[10px] text-amber-700/80 mt-1">
                  체크 시 프롬프트에 "flat fill, no noise, uniform middle" 가이드 자동 prepend +
                  태그에 <code className="bg-amber-100 px-1 rounded">9slice, tileable, ui_panel</code> 추가
                </p>
              </div>

              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">태그 (쉼표 구분, 선택)</label>
                <input
                  type="text"
                  value={gTags}
                  onChange={(e) => setGTags(e.target.value)}
                  placeholder="예: balloon, character, pastel"
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                  style={{ color: "#e6e9ef" }}
                />
              </div>
              {genError && <p className="text-xs text-red-600">{genError}</p>}
              <p className="text-[11px] text-gray-400">
                GPT Image 2 (OpenAI via LiteLLM) · 매수×quality에 따라 30초~3분 · 비용은 high={'>'}medium{'>'}low
              </p>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setShowCreate(false)} disabled={generating} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">취소</button>
              <button onClick={generate} disabled={generating || !gPrompt.trim()} className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40">
                {generating ? "생성 중... (1~2분)" : "생성"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 상세 모달 */}
      {detail && (
        <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center p-4" onClick={() => setDetail(null)}>
          <div className="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="text-base font-bold">디자인 상세</h3>
                <p className="text-xs text-gray-400 mt-0.5">{formatTime(detail.created_at)} · {detail.created_by_email}</p>
              </div>
              <button onClick={() => setDetail(null)} className="text-gray-400 hover:text-gray-700 text-xl">×</button>
            </div>
            {/* 참조 이미지가 있으면 결과물 위에 별도 섹션으로 표시 */}
            {detail.reference_filename && (
              <div className="mb-3 p-3 rounded-lg bg-purple-50 border border-purple-200">
                <p className="text-xs font-medium text-purple-700 uppercase tracking-wide mb-2">
                  📎 참조 이미지 (원본 레퍼런스 — images/edits 엔드포인트 사용됨)
                </p>
                <div className="flex justify-center">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={imgUrl(detail.reference_filename)}
                    alt="참조 이미지"
                    onClick={() => detail.reference_filename && setZoomImage(imgUrl(detail.reference_filename))}
                    className="max-h-64 rounded border border-purple-200 bg-white cursor-zoom-in"
                  />
                </div>
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              {(detail.images ?? []).map((img) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={img.filename}
                  src={imgUrl(img.filename)}
                  alt={detail.prompt.slice(0, 50)}
                  onClick={() => setZoomImage(imgUrl(img.filename))}
                  className="w-full rounded-lg border border-gray-200 bg-gray-50 cursor-zoom-in"
                />
              ))}
            </div>
            <div className="space-y-2">
              {detail.nine_slice && (
                <div className="rounded-md p-3 bg-emerald-50 border border-emerald-200 text-xs">
                  <div className="font-bold text-emerald-800 mb-1">🧩 9-Slice Border (Unity import 가이드)</div>
                  <div className="font-mono text-emerald-900 mb-1">
                    Top:{detail.nine_slice.top}px · Right:{detail.nine_slice.right}px · Bottom:{detail.nine_slice.bottom}px · Left:{detail.nine_slice.left}px
                  </div>
                  <div className="text-[11px] text-emerald-700/80">
                    💡 이 PNG를 Unity Project로 import → Sprite Editor → Border 입력값에 위 4값 그대로 입력. 이미지 자체는 손대지 않은 원본입니다.
                  </div>
                </div>
              )}
              {detail.mode_9slice && (
                <div className="rounded-md p-2 bg-amber-50 border border-amber-200 text-xs">
                  <span className="font-bold text-amber-800">🪟 Frame Cutout 변환본</span>
                  {detail.border_px && (
                    <span className="ml-2 text-amber-700">border = {detail.border_px}px (중앙 알파 0)</span>
                  )}
                  {detail.source_design_id && (
                    <span className="ml-2 text-[11px] text-amber-700/70">
                      원본: <code className="font-mono">{detail.source_design_id.slice(-8)}</code>
                    </span>
                  )}
                </div>
              )}
              {detail.user_prompt && detail.user_prompt !== detail.prompt && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">사용자 입력 프롬프트</p>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{detail.user_prompt}</p>
                </div>
              )}
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  최종 프롬프트 {detail.mode_9slice && <span className="text-amber-600 normal-case">(9-slice 가이드 prepend됨)</span>}
                </p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{detail.prompt}</p>
              </div>
              <div className="flex flex-wrap gap-1">
                {(detail.tags ?? []).map((t) => (
                  <span key={t} className="text-[11px] bg-gray-100 text-gray-600 px-2 py-0.5 rounded">#{t}</span>
                ))}
              </div>
              <div className="text-xs text-gray-500">
                <span className="font-medium">모델:</span> {detail.model} · <span className="font-medium">크기:</span> {detail.size} · <span className="font-medium">매수:</span> {detail.n}
              </div>

              {/* 별점 — 1~5 클릭 */}
              {me && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-xs text-gray-500">내 평점:</span>
                  {[1,2,3,4,5].map((r) => {
                    const myR = detail.star_ratings?.[emailKey(me)] || 0;
                    const filled = r <= myR;
                    return (
                      <button
                        key={r}
                        onClick={() => setRating(detail, myR === r ? 0 : r)}
                        className={`text-lg transition-transform hover:scale-110 ${filled ? "text-yellow-500" : "text-gray-300 hover:text-yellow-300"}`}
                        title={`${r}점${myR === r ? " (해제)" : ""}`}
                      >
                        ★
                      </button>
                    );
                  })}
                  {detail.star_ratings && Object.keys(detail.star_ratings).length > 0 && (
                    <span className="text-[11px] text-gray-400 ml-2">
                      평균:{" "}
                      {(
                        Object.values(detail.star_ratings).filter((v) => v > 0)
                          .reduce((a, b) => a + b, 0) /
                        Math.max(1, Object.values(detail.star_ratings).filter((v) => v > 0).length)
                      ).toFixed(1)}
                      {" "}({Object.values(detail.star_ratings).filter((v) => v > 0).length}명)
                    </span>
                  )}
                </div>
              )}

              {/* 코멘트 스레드 */}
              <div className="border-t border-gray-100 pt-3">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2 inline-flex items-center gap-1">
                  <Icon name="chat" size={14} /> 코멘트 {detail.comments?.length ? `(${detail.comments.length})` : ""}
                </p>
                {(detail.comments || []).length > 0 && (
                  <div className="space-y-2 mb-3 max-h-48 overflow-y-auto">
                    {detail.comments!.map((c) => (
                      <div key={c.id} className="bg-gray-50 rounded p-2 group">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-xs font-semibold text-gray-700">{c.author}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-gray-400">
                              {new Date(c.created_at).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                            </span>
                            {(c.author_email === me) && (
                              <button
                                onClick={() => deleteComment(c.id)}
                                className="text-xs text-red-400 opacity-0 group-hover:opacity-100"
                              >
                                ✕
                              </button>
                            )}
                          </div>
                        </div>
                        <p className="text-xs text-gray-700 whitespace-pre-wrap">{c.text}</p>
                      </div>
                    ))}
                  </div>
                )}
                {me && (
                  <div className="flex gap-2">
                    <input
                      value={commentText}
                      onChange={(e) => setCommentText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) postComment(); }}
                      placeholder="피드백·코멘트 작성... (Enter)"
                      className="flex-1 px-3 py-1.5 text-xs border border-gray-200 rounded"
                      style={{ color: "#e6e9ef" }}
                    />
                    <button
                      onClick={postComment}
                      disabled={!commentText.trim()}
                      className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40"
                    >
                      등록
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-gray-100 flex-wrap">
              {detail.source === "task" && detail.task_id && (
                <a
                  href={`/tasks#task=${detail.task_id}`}
                  className="px-4 py-2 text-sm border border-purple-200 text-purple-700 rounded-lg hover:bg-purple-50"
                >
                  🔗 원본 Task로 이동
                </a>
              )}
              <button
                onClick={() => {
                  setGPrompt(detail.prompt);
                  setGSize(detail.size);
                  setGTags((detail.tags ?? []).filter((t) => !t.startsWith("task:")).join(", "));
                  setDetail(null);
                  setShowCreate(true);
                }}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                비슷하게 더 생성
              </button>
              {!detail.mode_9slice && (
                <button
                  onClick={() => {
                    const m = detail.nine_slice;
                    const def = 96;
                    setSliceBorder(m?.top || def);
                    setSliceTop(m?.top ?? def);
                    setSliceRight(m?.right ?? def);
                    setSliceBottom(m?.bottom ?? def);
                    setSliceLeft(m?.left ?? def);
                    setSlicing4Side(!!m && (m.top !== m.right || m.top !== m.bottom || m.top !== m.left));
                    setSlicing(detail);
                  }}
                  className="px-4 py-2 text-sm border border-amber-300 text-amber-800 rounded-lg hover:bg-amber-50"
                  title="9-Slice border 메타 설정 또는 Frame Cutout 변환"
                >
                  🧩 9-Slice / Frame
                </button>
              )}
              <button
                onClick={() => setInpaintTarget(detail)}
                className="px-4 py-2 text-sm border border-purple-300 text-purple-800 rounded-lg hover:bg-purple-50"
                title="브러시로 영역 칠하고 그 부분만 새 프롬프트로 재생성"
              >
                🪄 부분 재생성
              </button>
              <button
                onClick={() => deleteDesign(detail._id)}
                className="px-4 py-2 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50"
              >
                삭제
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 확대 이미지 */}
      {zoomImage && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 cursor-zoom-out" onClick={() => setZoomImage(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={zoomImage} alt="" className="max-w-full max-h-full object-contain" />
        </div>
      )}

      {/* 인페인팅 모달 — 브러시로 마스크 그리고 그 부분만 재생성 */}
      {inpaintTarget && <InpaintModal target={inpaintTarget} onClose={() => setInpaintTarget(null)} onDone={() => { setInpaintTarget(null); setDetail(null); fetchDesigns(); }} />}

      {/* 9-Slice 변환 모달 — 이미 생성된 이미지 중앙을 투명 처리 */}
      {slicing && (
        <div
          className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
          onClick={() => !slicingBusy && setSlicing(null)}
        >
          <div
            className="bg-white rounded-xl max-w-3xl w-full p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold">🧩 9-Slice 변환</h3>
              <button
                onClick={() => !slicingBusy && setSlicing(null)}
                className="text-gray-400 hover:text-gray-700 text-xl"
                disabled={slicingBusy}
              >
                ×
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 미리보기 — 보더 라인 오버레이 */}
              <div className="relative bg-gray-100 rounded-lg overflow-hidden" style={{ aspectRatio: "1 / 1" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={slicing.images[0] ? imgUrl(slicing.images[0].filename) : ""}
                  alt="원본"
                  className="absolute inset-0 w-full h-full object-contain"
                />
                {/* 보더 라인 오버레이 — 이미지 비율 기준 (1024 가정) */}
                {(() => {
                  const W = slicing.images[0]?.width || 1024;
                  const H = slicing.images[0]?.height || 1024;
                  const t = slicing4Side ? sliceTop : sliceBorder;
                  const b = slicing4Side ? sliceBottom : sliceBorder;
                  const l = slicing4Side ? sliceLeft : sliceBorder;
                  const r = slicing4Side ? sliceRight : sliceBorder;
                  return (
                    <>
                      {/* 4개 보더 라인을 % 위치에 그림 */}
                      <div className="absolute left-0 right-0 border-t-2 border-amber-500/80" style={{ top: `${(t / H) * 100}%` }} />
                      <div className="absolute left-0 right-0 border-t-2 border-amber-500/80" style={{ top: `${((H - b) / H) * 100}%` }} />
                      <div className="absolute top-0 bottom-0 border-l-2 border-amber-500/80" style={{ left: `${(l / W) * 100}%` }} />
                      <div className="absolute top-0 bottom-0 border-l-2 border-amber-500/80" style={{ left: `${((W - r) / W) * 100}%` }} />
                      {/* 중앙 (투명 될 영역) 표시 */}
                      <div
                        className="absolute bg-amber-500/15 border border-amber-500/50"
                        style={{
                          top: `${(t / H) * 100}%`,
                          bottom: `${(b / H) * 100}%`,
                          left: `${(l / W) * 100}%`,
                          right: `${(r / W) * 100}%`,
                        }}
                      >
                        <div className="text-[10px] text-amber-800 font-bold p-1 bg-white/70 inline-block rounded">
                          → 투명 처리
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>

              {/* 보더 입력 */}
              <div className="space-y-3 text-sm">
                <p className="text-xs text-gray-500">
                  주황 영역(중앙)이 알파 0(투명)으로 처리됩니다.
                  <br />Unity Sprite import 시 동일한 보더 값으로 9-slice 설정.
                </p>

                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={slicing4Side}
                    onChange={(e) => setSlicing4Side(e.target.checked)}
                    disabled={slicingBusy}
                  />
                  4면 개별 지정
                </label>

                {!slicing4Side ? (
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">보더 (4면 동일, px)</label>
                    <input
                      type="number"
                      min={8}
                      max={512}
                      step={8}
                      value={sliceBorder}
                      onChange={(e) => setSliceBorder(Math.max(8, Math.min(512, parseInt(e.target.value) || 96)))}
                      disabled={slicingBusy}
                      className="w-full border border-gray-200 rounded px-3 py-1.5"
                      style={{ color: "#e6e9ef" }}
                    />
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {([
                      ["Top", sliceTop, setSliceTop],
                      ["Right", sliceRight, setSliceRight],
                      ["Bottom", sliceBottom, setSliceBottom],
                      ["Left", sliceLeft, setSliceLeft],
                    ] as const).map(([label, val, setter]) => (
                      <div key={label}>
                        <label className="block text-gray-500 mb-0.5">{label} (px)</label>
                        <input
                          type="number" min={0} max={512} step={8} value={val}
                          onChange={(e) => setter(Math.max(0, Math.min(512, parseInt(e.target.value) || 0)))}
                          disabled={slicingBusy}
                          className="w-full border border-gray-200 rounded px-2 py-1"
                          style={{ color: "#e6e9ef" }}
                        />
                      </div>
                    ))}
                  </div>
                )}

                <div className="text-[11px] text-gray-400">
                  원본 사이즈: <span className="font-mono">{slicing.images[0]?.width} × {slicing.images[0]?.height}</span>
                </div>

                <div className="space-y-2 pt-3 border-t border-gray-100">
                  <p className="text-[11px] text-gray-500">
                    동일 보더값으로 두 가지 작업 가능 — 정통 9-slice는 이미지 보존, Frame Cutout은 중앙 투명 새 PNG.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <button
                      onClick={async () => {
                        if (!slicing) return;
                        setSlicingBusy(true);
                        try {
                          const body = slicing4Side
                            ? { border_top: sliceTop, border_bottom: sliceBottom, border_left: sliceLeft, border_right: sliceRight }
                            : { border_px: sliceBorder };
                          const r = await fetch(`/api/designs/${slicing._id}/9slice-meta`, {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(body),
                          });
                          const j = await r.json();
                          if (!r.ok) { alert(j.error || "메타 저장 실패"); return; }
                          setSlicing(null);
                          setDetail(null);
                          await fetchDesigns();
                          const m = j.nine_slice;
                          alert(`✅ 9-Slice 메타 저장됨\nT:${m.top} R:${m.right} B:${m.bottom} L:${m.left}\n→ Unity Sprite Editor Border에 그대로 입력`);
                        } catch (e) {
                          alert(`오류: ${e instanceof Error ? e.message : "unknown"}`);
                        } finally { setSlicingBusy(false); }
                      }}
                      disabled={slicingBusy}
                      className="flex-1 px-4 py-2 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-40"
                      title="이미지 그대로 두고 border 4값만 메타로 저장 (Unity 표준 9-slice)"
                    >
                      🧩 9-Slice 메타 저장 (이미지 보존)
                    </button>
                    <button
                      onClick={async () => {
                        if (!slicing) return;
                        if (!confirm("중앙을 투명 처리한 별도 PNG 파일을 새로 만듭니다. 원본은 그대로 보존됩니다.\n계속할까요?")) return;
                        setSlicingBusy(true);
                        try {
                          const body = slicing4Side
                            ? { border_top: sliceTop, border_bottom: sliceBottom, border_left: sliceLeft, border_right: sliceRight }
                            : { border_px: sliceBorder };
                          const r = await fetch(`/api/designs/${slicing._id}/to-9slice`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(body),
                          });
                          const j = await r.json();
                          if (!r.ok) { alert(j.error || "변환 실패"); return; }
                          setSlicing(null);
                          setDetail(null);
                          await fetchDesigns();
                          alert(`✅ Frame Cutout 변환 완료. 새 디자인 ID: ${String(j.new_id).slice(-8)} (${j.zeroed_pixels?.toLocaleString()} 픽셀 투명화)`);
                        } catch (e) {
                          alert(`오류: ${e instanceof Error ? e.message : "unknown"}`);
                        } finally { setSlicingBusy(false); }
                      }}
                      disabled={slicingBusy}
                      className="flex-1 px-4 py-2 text-sm bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-40"
                      title="중앙을 알파 0으로 만든 새 PNG 파일 생성 (frame 패널 용)"
                    >
                      🪟 Frame Cutout (새 PNG)
                    </button>
                  </div>
                  <div className="flex justify-end">
                    <button
                      onClick={() => setSlicing(null)}
                      disabled={slicingBusy}
                      className="px-3 py-1 text-xs text-gray-500 hover:text-gray-700"
                    >
                      취소
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// 인페인팅 모달 — canvas 위에 브러시로 마스크 그리고 그 영역만 새 프롬프트로 재생성
// ─────────────────────────────────────────────────────────────────
function InpaintModal({
  target, onClose, onDone,
}: {
  target: Design;
  onClose: () => void;
  onDone: () => void;
}) {
  const imgRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [brush, setBrush] = useState(40);
  const [eraser, setEraser] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const drawing = useRef(false);

  const filename = target.images[0]?.filename || "";
  const W = target.images[0]?.width || 1024;
  const H = target.images[0]?.height || 1024;

  // 캔버스 초기화 — 원본 이미지 크기 그대로
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    c.width = W;
    c.height = H;
    const ctx = c.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, W, H);
  }, [W, H]);

  function getCoords(e: React.MouseEvent<HTMLCanvasElement>): [number, number] {
    const c = canvasRef.current;
    if (!c) return [0, 0];
    const rect = c.getBoundingClientRect();
    const sx = c.width / rect.width;
    const sy = c.height / rect.height;
    return [(e.clientX - rect.left) * sx, (e.clientY - rect.top) * sy];
  }
  function paint(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const [x, y] = getCoords(e);
    ctx.globalCompositeOperation = eraser ? "destination-out" : "source-over";
    ctx.fillStyle = "rgba(255, 0, 255, 0.5)";  // 마젠타 마스크 (시각적)
    ctx.beginPath();
    ctx.arc(x, y, brush, 0, Math.PI * 2);
    ctx.fill();
  }
  function clearMask() {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, W, H);
  }

  /**
   * 캔버스를 OpenAI edits 마스크 PNG로 변환:
   *  - 원본과 같은 크기 RGBA
   *  - 그린 영역(반투명 마젠타) → 알파 0 (재생성)
   *  - 안 그린 영역 → 알파 255 (보존)
   */
  async function buildMask(): Promise<Blob> {
    const c = canvasRef.current!;
    const ctx = c.getContext("2d")!;
    const src = ctx.getImageData(0, 0, W, H);
    // 새 캔버스 (출력용)
    const out = document.createElement("canvas");
    out.width = W; out.height = H;
    const octx = out.getContext("2d")!;
    const dst = octx.createImageData(W, H);
    for (let i = 0; i < src.data.length; i += 4) {
      const drawnAlpha = src.data[i + 3];
      // RGB 흰색, 알파는 그린 영역이면 0, 아니면 255
      dst.data[i] = 255;
      dst.data[i + 1] = 255;
      dst.data[i + 2] = 255;
      dst.data[i + 3] = drawnAlpha > 30 ? 0 : 255;
    }
    octx.putImageData(dst, 0, 0);
    return await new Promise<Blob>((resolve) => out.toBlob((b) => resolve(b!), "image/png"));
  }

  async function submit() {
    if (!prompt.trim()) { alert("새로 그릴 영역의 프롬프트를 입력하세요"); return; }
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const has = ctx.getImageData(0, 0, W, H).data.some((v, i) => i % 4 === 3 && v > 30);
    if (!has) { alert("마스크 영역을 먼저 칠해주세요 (재생성될 부분)"); return; }

    setBusy(true);
    try {
      const mask = await buildMask();
      const fd = new FormData();
      fd.append("filename", filename);
      fd.append("prompt", prompt.trim());
      fd.append("mask", mask, "mask.png");
      const r = await fetch(`/api/designs/${target._id}/inpaint`, { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) {
        alert(j.error || "재생성 실패");
        return;
      }
      alert(`✅ 재생성 완료. 새 디자인 ID: ${String(j.new_id).slice(-8)}`);
      onDone();
    } catch (e) {
      alert(`오류: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => !busy && onClose()}>
      <div className="bg-white rounded-xl max-w-5xl w-full max-h-[95vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold">🪄 부분 재생성 (Inpainting)</h3>
          <button onClick={() => !busy && onClose()} className="text-gray-400 hover:text-gray-700 text-xl" disabled={busy}>×</button>
        </div>
        <p className="text-xs text-gray-500 mb-3">
          마젠타 브러시로 <b>다시 그릴 영역</b>을 칠하고, 새 프롬프트를 입력하세요. 안 칠한 부분은 원본 그대로 유지됩니다.
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* 왼쪽: 캔버스 + 이미지 */}
          <div className="lg:col-span-2 relative bg-gray-100 rounded-lg overflow-hidden" style={{ aspectRatio: `${W} / ${H}` }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              ref={imgRef}
              src={imgUrl(filename)}
              alt="원본"
              className="absolute inset-0 w-full h-full object-contain pointer-events-none"
              draggable={false}
            />
            <canvas
              ref={canvasRef}
              className="absolute inset-0 w-full h-full cursor-crosshair"
              style={{ touchAction: "none" }}
              onMouseDown={(e) => { drawing.current = true; paint(e); }}
              onMouseMove={paint}
              onMouseUp={() => { drawing.current = false; }}
              onMouseLeave={() => { drawing.current = false; }}
            />
          </div>

          {/* 오른쪽: 도구 + 프롬프트 */}
          <div className="space-y-3 text-sm">
            <div>
              <label className="text-xs text-gray-500 block mb-1">브러시 크기: {brush}px</label>
              <input type="range" min={5} max={200} value={brush} onChange={(e) => setBrush(parseInt(e.target.value, 10))} className="w-full" />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setEraser(false)}
                className={`flex-1 px-3 py-1.5 text-xs rounded border ${!eraser ? "bg-purple-600 text-white border-purple-600" : "border-gray-200"}`}
              >
                🖌 그리기
              </button>
              <button
                onClick={() => setEraser(true)}
                className={`flex-1 px-3 py-1.5 text-xs rounded border ${eraser ? "bg-gray-700 text-white border-gray-700" : "border-gray-200"}`}
              >
                🧹 지우기
              </button>
            </div>
            <button
              onClick={clearMask}
              className="w-full px-3 py-1.5 text-xs border border-gray-200 rounded hover:bg-gray-50"
            >
              마스크 전체 지우기
            </button>

            <div>
              <label className="text-xs text-gray-500 block mb-1">새 프롬프트 (마스크 영역 재생성 지시)</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={5}
                placeholder="예: replace the marked area with a clean wooden texture, no metal"
                className="w-full px-3 py-2 text-xs border border-gray-200 rounded resize-none"
                style={{ color: "#e6e9ef" }}
              />
              <p className="text-[10px] text-gray-400 mt-0.5">
                팁: 영문 + 구체적인 형용사 (color, material, style) 가 잘 먹힙니다.
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <button
                onClick={() => !busy && onClose()}
                disabled={busy}
                className="px-3 py-1.5 text-sm border border-gray-200 rounded hover:bg-gray-50"
              >
                취소
              </button>
              <button
                onClick={submit}
                disabled={busy || !prompt.trim()}
                className="px-4 py-1.5 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-40"
              >
                {busy ? "재생성 중..." : "🪄 재생성 실행"}
              </button>
            </div>
            <p className="text-[10px] text-gray-400">
              원본은 보존됩니다. 결과는 새 디자인으로 저장됩니다 (source: {String(target._id).slice(-8)})
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
