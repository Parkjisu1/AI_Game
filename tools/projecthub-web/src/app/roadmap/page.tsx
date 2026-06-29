"use client";
import { useEffect, useState } from "react";
import { RoadmapView } from "@/components/RoadmapChart";
import Icon from "@/components/Icon";
import type { RoadmapData, RoadmapTask, RoadmapSprint } from "@/lib/roadmap";

const ROLE_OPTIONS = ["기획", "개발", "아트", "★", "ALL"];

export default function RoadmapEditorPage() {
  const [data, setData] = useState<RoadmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");

  // 모달 state
  const [taskModal, setTaskModal] = useState<{
    mode: "add" | "edit";
    idx: number;
    task: RoadmapTask;
  } | null>(null);
  const [sprintModal, setSprintModal] = useState<{
    mode: "add" | "edit";
    sprint: RoadmapSprint;
  } | null>(null);
  const [startDateModal, setStartDateModal] = useState(false);
  const [startDateVal, setStartDateVal] = useState("");

  useEffect(() => {
    fetch("/api/roadmap")
      .then((r) => r.json())
      .then((j) => { if (j.ok && j.data) setData(j.data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function flash(msg: string) {
    setNotice(msg);
    setTimeout(() => setNotice(""), 2000);
  }

  async function saveData(updated: RoadmapData) {
    setSaving(true);
    try {
      const res = await fetch("/api/roadmap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: updated }),
      });
      if (!res.ok) {
        flash("저장 실패");
        return;
      }
      setData(updated);
      flash("저장됨");
    } catch {
      flash("저장 실패");
    } finally {
      setSaving(false);
    }
  }

  // ── Task CRUD
  function openAddTask() {
    if (!data) return;
    const newTask: RoadmapTask = {
      role: "기획",
      title: "",
      period: "",
      weekStart: 0, // 0 = 미설정 — 사용자가 직접 입력
      weekEnd: 0,
      sprintId: data.sprints[0]?.id ?? 0,
    };
    setTaskModal({ mode: "add", idx: -1, task: newTask });
  }

  function openEditTask(task: RoadmapTask, idx: number) {
    setTaskModal({ mode: "edit", idx, task: { ...task } });
  }

  async function commitTask() {
    if (!taskModal || !data) return;
    const t = taskModal.task;
    if (!t.title.trim()) { flash("title 필수"); return; }
    t.period = t.weekStart === t.weekEnd ? `W${t.weekStart}` : `W${t.weekStart}~W${t.weekEnd}`;
    const newTasks = [...data.tasks];
    if (taskModal.mode === "add") newTasks.push(t);
    else newTasks[taskModal.idx] = t;
    await saveData({ ...data, tasks: newTasks });
    setTaskModal(null);
  }

  async function deleteTask() {
    if (!taskModal || !data || taskModal.mode === "add") return;
    if (!confirm(`"${taskModal.task.title}" 삭제?`)) return;
    const newTasks = data.tasks.filter((_, i) => i !== taskModal.idx);
    await saveData({ ...data, tasks: newTasks });
    setTaskModal(null);
  }

  // ── Sprint CRUD
  function openAddSprint() {
    if (!data) return;
    const nextId = data.sprints.length > 0
      ? Math.max(...data.sprints.map((s) => s.id)) + 1
      : 0;
    setSprintModal({
      mode: "add",
      sprint: { id: nextId, label: `SPRINT ${nextId}: 신규 스프린트`, weekStart: 1, weekEnd: 1 },
    });
  }

  function openEditSprint(sprint: RoadmapSprint) {
    setSprintModal({ mode: "edit", sprint: { ...sprint } });
  }

  async function commitSprint() {
    if (!sprintModal || !data) return;
    const s = sprintModal.sprint;
    if (!s.label.trim()) { flash("label 필수"); return; }
    let newSprints: RoadmapSprint[];
    if (sprintModal.mode === "add") {
      newSprints = [...data.sprints, s];
    } else {
      newSprints = data.sprints.map((existing) => existing.id === s.id ? s : existing);
    }
    newSprints.sort((a, b) => a.id - b.id);
    await saveData({ ...data, sprints: newSprints });
    setSprintModal(null);
  }

  async function deleteSprint() {
    if (!sprintModal || !data || sprintModal.mode === "add") return;
    const sprintTasks = data.tasks.filter((t) => t.sprintId === sprintModal.sprint.id);
    if (!confirm(`Sprint ${sprintModal.sprint.id} 삭제? (이 sprint의 ${sprintTasks.length}개 task도 함께 삭제됨)`)) return;
    const newSprints = data.sprints.filter((s) => s.id !== sprintModal.sprint.id);
    const newTasks = data.tasks.filter((t) => t.sprintId !== sprintModal.sprint.id);
    await saveData({ ...data, sprints: newSprints, tasks: newTasks });
    setSprintModal(null);
  }

  // ── Start date
  function openStartDate() {
    if (!data) return;
    setStartDateVal(data.startDate || "");
    setStartDateModal(true);
  }

  async function commitStartDate() {
    if (!data) return;
    await saveData({ ...data, startDate: startDateVal });
    setStartDateModal(false);
  }

  if (loading) {
    return <div className="text-sm text-gray-400">로딩 중...</div>;
  }

  if (!data) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h1 className="text-xl font-bold mb-2">로드맵 편집</h1>
        <p className="text-sm text-gray-500 mb-3">로드맵 데이터가 없습니다. 대시보드에서 CSV를 먼저 업로드하거나 빈 로드맵을 만들어 시작하세요.</p>
        <button
          onClick={() => saveData({
            uploadedAt: new Date().toISOString(),
            startDate: new Date().toISOString().slice(0, 10),
            sprints: [],
            tasks: [],
          })}
          className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800"
        >
          빈 로드맵 만들기
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2"><Icon name="map" size={24} /> 로드맵 편집</h1>
          <p className="text-sm text-gray-500 mt-1 leading-relaxed">
            클릭으로 task/sprint 편집 · {data.tasks.length} task · {data.sprints.length} sprints
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {notice && <span className="text-sm text-green-600 font-medium">{notice}</span>}
          {saving && <span className="text-sm text-gray-400">저장 중...</span>}
          <button
            onClick={openStartDate}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
            style={{ color: "#e6e9ef" }}
          >
            <span className="inline-flex items-center gap-1"><Icon name="calendar" size={13} /> 시작일: {data.startDate || "미설정"}</span>
          </button>
          <button
            onClick={openAddSprint}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
            style={{ color: "#e6e9ef" }}
          >
            + Sprint
          </button>
          <button
            onClick={openAddTask}
            className="px-3 py-1.5 text-sm bg-black text-white rounded-lg hover:bg-gray-800"
          >
            + Task
          </button>
        </div>
      </div>

      <RoadmapView
        data={data}
        editable
        onTaskClick={openEditTask}
        onSprintClick={openEditSprint}
        onTaskDrop={async (task, idx, newWs, newWe) => {
          if (!data) return;
          const updated = { ...task, weekStart: newWs, weekEnd: newWe, period: newWs === newWe ? `W${newWs}` : `W${newWs}~W${newWe}` };
          const newTasks = [...data.tasks];
          newTasks[idx] = updated;
          await saveData({ ...data, tasks: newTasks });
        }}
      />

      {/* Task Modal */}
      {taskModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-3" onClick={() => setTaskModal(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold mb-4">
              {taskModal.mode === "add" ? "Task 추가" : "Task 편집"}
            </h2>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Title *</label>
                <input
                  value={taskModal.task.title}
                  onChange={(e) => setTaskModal({ ...taskModal, task: { ...taskModal.task, title: e.target.value } })}
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                  style={{ color: "#e6e9ef" }}
                  autoFocus
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">역할</label>
                  <select
                    value={taskModal.task.role}
                    onChange={(e) => setTaskModal({ ...taskModal, task: { ...taskModal.task, role: e.target.value } })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    style={{ color: "#e6e9ef" }}
                  >
                    {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Sprint</label>
                  <select
                    value={taskModal.task.sprintId}
                    onChange={(e) => setTaskModal({ ...taskModal, task: { ...taskModal.task, sprintId: Number(e.target.value) } })}
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
                    style={{ color: "#e6e9ef" }}
                  >
                    {data.sprints.map((s) => (
                      <option key={s.id} value={s.id}>Sprint {s.id} (W{s.weekStart}~W{s.weekEnd})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">시작 주</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={taskModal.task.weekStart || ""}
                    onChange={(e) => setTaskModal({ ...taskModal, task: { ...taskModal.task, weekStart: Number(e.target.value) || 0 } })}
                    onFocus={(e) => e.target.select()}
                    placeholder="예: 4"
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    style={{ color: "#e6e9ef" }}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">종료 주</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={taskModal.task.weekEnd || ""}
                    onChange={(e) => setTaskModal({ ...taskModal, task: { ...taskModal.task, weekEnd: Number(e.target.value) || 0 } })}
                    onFocus={(e) => e.target.select()}
                    placeholder="예: 6"
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    style={{ color: "#e6e9ef" }}
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-between items-center mt-5">
              {taskModal.mode === "edit" ? (
                <button onClick={deleteTask} className="text-sm text-red-600 hover:underline">삭제</button>
              ) : <span />}
              <div className="flex gap-2">
                <button onClick={() => setTaskModal(null)} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50" style={{ color: "#e6e9ef" }}>취소</button>
                <button onClick={commitTask} className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800">저장</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sprint Modal */}
      {sprintModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-3" onClick={() => setSprintModal(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-[440px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold mb-4">
              {sprintModal.mode === "add" ? "Sprint 추가" : "Sprint 편집"}
            </h2>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Sprint ID</label>
                <input
                  type="number"
                  value={sprintModal.sprint.id}
                  onChange={(e) => setSprintModal({ ...sprintModal, sprint: { ...sprintModal.sprint, id: Number(e.target.value) || 0 } })}
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                  style={{ color: "#e6e9ef" }}
                  disabled={sprintModal.mode === "edit"}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Label</label>
                <input
                  value={sprintModal.sprint.label}
                  onChange={(e) => setSprintModal({ ...sprintModal, sprint: { ...sprintModal.sprint, label: e.target.value } })}
                  className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                  style={{ color: "#e6e9ef" }}
                  placeholder="SPRINT 0: 프리프로덕션"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">시작 주</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={sprintModal.sprint.weekStart || ""}
                    onChange={(e) => setSprintModal({ ...sprintModal, sprint: { ...sprintModal.sprint, weekStart: Number(e.target.value) || 0 } })}
                    onFocus={(e) => e.target.select()}
                    placeholder="예: 1"
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    style={{ color: "#e6e9ef" }}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">종료 주</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={sprintModal.sprint.weekEnd || ""}
                    onFocus={(e) => e.target.select()}
                    onChange={(e) => setSprintModal({ ...sprintModal, sprint: { ...sprintModal.sprint, weekEnd: Number(e.target.value) || 0 } })}
                    placeholder="예: 3"
                    className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    style={{ color: "#e6e9ef" }}
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-between items-center mt-5">
              {sprintModal.mode === "edit" ? (
                <button onClick={deleteSprint} className="text-sm text-red-600 hover:underline">삭제</button>
              ) : <span />}
              <div className="flex gap-2">
                <button onClick={() => setSprintModal(null)} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50" style={{ color: "#e6e9ef" }}>취소</button>
                <button onClick={commitSprint} className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800">저장</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Start date modal */}
      {startDateModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-3" onClick={() => setStartDateModal(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-[360px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold mb-4">시작일 (W1)</h2>
            <input
              type="date"
              value={startDateVal}
              onChange={(e) => setStartDateVal(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              style={{ color: "#e6e9ef" }}
            />
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setStartDateModal(false)} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50" style={{ color: "#e6e9ef" }}>취소</button>
              <button onClick={commitStartDate} className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800">저장</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
