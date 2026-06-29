"use client";
import { useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import { parseRoadmapCSV, currentWeek, ROLE_COLORS, type RoadmapData, type RoadmapTask, type RoadmapSprint } from "@/lib/roadmap";

export default function RoadmapChart() {
  const [data, setData] = useState<RoadmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/roadmap")
      .then((r) => r.json())
      .then((j) => {
        if (j.ok && j.data) setData(j.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function decodeBytes(buf: ArrayBuffer): string {
    const bytes = new Uint8Array(buf);
    if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
      return new TextDecoder("utf-8").decode(bytes.slice(3));
    }
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      try {
        return new TextDecoder("euc-kr").decode(bytes);
      } catch {
        return new TextDecoder("utf-8").decode(bytes);
      }
    }
  }

  async function handleUpload(file: File) {
    setUploading(true);
    setError("");
    try {
      const buf = await file.arrayBuffer();
      const text = decodeBytes(buf);
      const parsed = parseRoadmapCSV(text);
      if (parsed.tasks.length === 0) {
        setError("파싱된 task가 0건 — CSV 형식 확인");
        return;
      }
      const res = await fetch("/api/roadmap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: parsed }),
      });
      if (!res.ok) {
        setError("저장 실패");
        return;
      }
      setData(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드 실패");
    } finally {
      setUploading(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="text-sm text-gray-400">로드맵 로딩 중...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-base font-bold mb-2 flex items-center gap-2"><Icon name="map" size={16} /> 프로젝트 로드맵</h2>
        <p className="text-xs text-gray-500 mb-3">
          Sort Puzzle Roadmap CSV를 업로드하여 주별 작업 볼륨을 확인하세요.
        </p>
        <label className="inline-flex items-center gap-1.5 px-3 py-2 text-xs border border-dashed border-gray-300 rounded-lg cursor-pointer hover:bg-gray-50">
          <Icon name="calendar" size={13} /> {uploading ? "업로드 중..." : "CSV 업로드"}
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={uploading}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f);
            }}
            className="hidden"
          />
        </label>
        {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
      </div>
    );
  }

  // 데이터가 있을 때만 내부 view 컴포넌트 mount → 훅 순서 안정
  return <RoadmapView data={data} onUpload={handleUpload} />;
}

// ───────────────────────────────────────────────────────────────────
// 차트 본문 — data가 항상 존재한다고 가정. useMemo 등 hook 사용 가능.
export interface RoadmapViewProps {
  data: RoadmapData;
  onUpload?: (f: File) => void;
  editable?: boolean;
  onTaskClick?: (task: RoadmapTask, idx: number) => void;
  onSprintClick?: (sprint: RoadmapSprint) => void;
  onTaskDrop?: (task: RoadmapTask, idx: number, newWeekStart: number, newWeekEnd: number) => void;
}

export function RoadmapView({ data, onUpload, editable, onTaskClick, onSprintClick, onTaskDrop }: RoadmapViewProps) {
  const today = currentWeek(data.startDate);

  const maxWeek = useMemo(() => Math.max(
    12,
    ...data.tasks.map((t) => t.weekEnd || 0),
    ...data.sprints.map((s) => s.weekEnd || 0),
  ), [data]);

  const sortedTasks = useMemo(() => {
    return [...data.tasks].sort((a, b) => {
      if (a.sprintId !== b.sprintId) return a.sprintId - b.sprintId;
      if (a.role !== b.role) return a.role.localeCompare(b.role);
      return (a.weekStart || 0) - (b.weekStart || 0);
    });
  }, [data]);

  const sprintCounts = useMemo(() => data.sprints.map((s) => ({
    ...s,
    count: data.tasks.filter((t) => t.sprintId === s.id).length,
  })), [data]);

  const allRoles = useMemo(
    () => Array.from(new Set(data.tasks.map((t) => t.role))),
    [data]
  );

  const colWidth = 56;
  const labelWidth = 280;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
        <div>
          <h2 className="text-base font-bold flex items-center gap-2"><Icon name="map" size={16} /> 프로젝트 로드맵</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            전체 {data.tasks.length} task · {data.sprints.length} sprints
            {today > 0 ? ` · 현재 W${today}` : ""}
            {data.startDate ? ` · 시작 ${data.startDate}` : ""}
          </p>
        </div>
        {onUpload && (
          <label className="text-xs text-blue-600 hover:underline cursor-pointer self-start sm:self-auto">
            CSV 업데이트
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUpload(f);
              }}
              className="hidden"
            />
          </label>
        )}
      </div>

      {/* Sprint header cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-5">
        {sprintCounts.map((s) => {
          const isActive = today >= s.weekStart && today <= s.weekEnd;
          return (
            <div
              key={s.id}
              className={`relative px-3.5 py-2.5 rounded-xl border text-xs transition-colors ${
                isActive
                  ? "border-blue-400 bg-blue-50 ring-1 ring-blue-300/40"
                  : "border-gray-200 bg-gray-50"
              }`}
              style={{ color: "#e6e9ef" }}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold tracking-tight">Sprint {s.id}</span>
                {isActive && (
                  <span className="text-[9px] font-semibold text-blue-600 bg-blue-100 rounded-full px-1.5 py-0.5">
                    현재
                  </span>
                )}
              </div>
              <div className="text-gray-500 mt-0.5">W{s.weekStart} ~ W{s.weekEnd}</div>
              <div className="font-bold mt-1 text-sm">{s.count}<span className="font-normal text-gray-500 text-[11px] ml-1">tasks</span></div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-3 pb-3 border-b border-gray-100">
        <span className="text-[11px] font-medium text-gray-400 uppercase tracking-wide">역할</span>
        {allRoles.map((role) => (
          <div key={role} className="flex items-center gap-1.5 text-xs">
            <span
              className="inline-block w-3 h-3 rounded-full shadow-sm"
              style={{ backgroundColor: ROLE_COLORS[role] || "#94a3b8" }}
            />
            <span style={{ color: "#e6e9ef" }}>{role}</span>
          </div>
        ))}
        {today > 0 && (
          <div className="flex items-center gap-1.5 text-xs ml-auto">
            <span className="inline-block w-4 h-0.5 rounded-full bg-red-500" />
            <span style={{ color: "#e6e9ef" }}>현재 W{today}</span>
          </div>
        )}
      </div>

      {/* Vertical Gantt chart — task rows × week columns */}
      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <div style={{ minWidth: labelWidth + colWidth * maxWeek }}>
          {/* Header row: week labels */}
          <div className="flex sticky top-0 bg-white z-10 border-b border-gray-200">
            <div
              className="shrink-0 px-3 py-2 text-xs font-semibold border-r border-gray-200 bg-gray-50"
              style={{ width: labelWidth, color: "#e6e9ef" }}
            >
              Task
            </div>
            <div className="flex relative">
              {Array.from({ length: maxWeek }, (_, i) => i + 1).map((w) => (
                <div
                  key={w}
                  className={`shrink-0 text-center text-[10px] py-2 border-r border-gray-100 ${
                    w === today ? "bg-red-50 font-bold text-red-600" : "bg-gray-50"
                  }`}
                  style={{ width: colWidth, color: w === today ? undefined : "#e6e9ef" }}
                >
                  W{w}
                </div>
              ))}
              {today > 0 && today <= maxWeek && (
                <div
                  className="absolute top-0 bottom-0 w-px bg-red-500/70 z-20 pointer-events-none"
                  style={{ left: (today - 1) * colWidth + colWidth / 2 }}
                />
              )}
            </div>
          </div>

          {/* Task rows grouped by sprint */}
          {data.sprints.map((sprint) => {
            const sprintTasks = sortedTasks.filter((t) => t.sprintId === sprint.id);
            if (sprintTasks.length === 0 && !editable) return null;
            return (
              <div key={sprint.id}>
                {/* Sprint header row */}
                <div
                  className={`flex bg-gray-100 border-b border-gray-200 ${
                    editable ? "cursor-pointer hover:bg-gray-200" : ""
                  }`}
                  onClick={editable && onSprintClick ? () => onSprintClick(sprint) : undefined}
                >
                  <div
                    className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold border-r border-gray-200"
                    style={{ width: labelWidth + colWidth * maxWeek, color: "#e6e9ef" }}
                  >
                    <Icon name="flag" size={12} />
                    <span>Sprint {sprint.id} · {sprint.label.replace(/^SPRINT\s+\d+:\s*/i, "")}</span>
                    {editable && <Icon name="edit" size={12} className="text-blue-600 ml-1" />}
                  </div>
                </div>
                {/* Task rows */}
                {sprintTasks.map((task) => {
                  // 원본 data.tasks에서의 index 찾기 (편집/삭제 시 필요)
                  const origIdx = data.tasks.indexOf(task);
                  const ws = task.weekStart || 0;
                  const we = task.weekEnd || 0;
                  const span = we - ws + 1;
                  const handleTaskClick = editable && onTaskClick
                    ? () => onTaskClick(task, origIdx)
                    : undefined;
                  return (
                    <div
                      key={`${sprint.id}-${origIdx}`}
                      className={`flex border-b border-gray-100 hover:bg-blue-50/30 ${
                        editable ? "cursor-pointer" : ""
                      }`}
                      style={{ minHeight: 26 }}
                      onClick={handleTaskClick}
                    >
                      <div
                        className="shrink-0 flex items-center gap-2 px-3 py-1 text-xs border-r border-gray-100 truncate"
                        style={{ width: labelWidth }}
                        title={task.title}
                      >
                        <span
                          className="inline-block w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: ROLE_COLORS[task.role] || "#94a3b8" }}
                          title={task.role}
                        />
                        <span style={{color:"#e6e9ef"}} className="truncate">{task.title}</span>
                      </div>
                      <div className="flex relative">
                        {Array.from({ length: maxWeek }, (_, i) => i + 1).map((w) => (
                          <div
                            key={w}
                            className={`shrink-0 border-r border-gray-100 ${
                              w === today ? "bg-red-50/40" : ""
                            }`}
                            style={{ width: colWidth, height: 26 }}
                            onDragOver={editable ? (e) => { e.preventDefault(); e.currentTarget.classList.add("bg-blue-100"); } : undefined}
                            onDragLeave={editable ? (e) => { e.currentTarget.classList.remove("bg-blue-100"); } : undefined}
                            onDrop={editable && onTaskDrop ? (e) => {
                              e.preventDefault();
                              e.currentTarget.classList.remove("bg-blue-100");
                              try {
                                const d = JSON.parse(e.dataTransfer.getData("text/plain"));
                                const newWs = w;
                                const newWe = w + d.span - 1;
                                onTaskDrop(data.tasks[d.origIdx], d.origIdx, newWs, newWe);
                              } catch {}
                            } : undefined}
                          />
                        ))}
                        {/* 현재 주 마커 라인 */}
                        {today > 0 && today <= maxWeek && (
                          <div
                            className="absolute top-0 bottom-0 w-px bg-red-500/40 z-10 pointer-events-none"
                            style={{ left: (today - 1) * colWidth + colWidth / 2 }}
                          />
                        )}
                        {/* Task bar — editable 시 드래그 가능 */}
                        {ws > 0 && we > 0 && (
                          <div
                            className={`absolute top-1/2 -translate-y-1/2 rounded-full h-4 shadow-sm ring-1 ring-black/5 flex items-center px-2 transition-shadow hover:shadow-md ${
                              editable && onTaskDrop ? "cursor-grab active:cursor-grabbing" : ""
                            }`}
                            style={{
                              left: (ws - 1) * colWidth + 2,
                              width: span * colWidth - 4,
                              backgroundColor: ROLE_COLORS[task.role] || "#94a3b8",
                            }}
                            title={`${task.role} · ${task.title} · W${ws}~W${we}${editable ? " (드래그로 이동)" : ""}`}
                            draggable={editable && !!onTaskDrop}
                            onDragStart={(e) => {
                              if (!editable || !onTaskDrop) return;
                              e.dataTransfer.setData("text/plain", JSON.stringify({ origIdx, ws, we, span }));
                              e.dataTransfer.effectAllowed = "move";
                            }}
                          >
                            <span className="text-[9px] text-white font-medium truncate">
                              {span > 1 ? `W${ws}~W${we}` : `W${ws}`}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
