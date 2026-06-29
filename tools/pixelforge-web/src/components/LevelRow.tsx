"use client";
import React, { memo, useCallback } from "react";
import { parseColorDist, PALETTE_HEX, COLOR_NAMES } from "@/lib/palette";
import { computeImageSize } from "@/lib/genUtils";

export interface Level {
  _id?: string;
  level_number: number;
  field_rows: number;
  field_columns: number;
  num_colors: number;
  color_distribution: string;
  purpose_type: string;
  designer_note: string;
  status: string;
  image_base64?: string;
  field_map?: string;
  [key: string]: unknown;
}

export interface ColumnDef {
  key: keyof Level;
  label: string;
  width: string;
}

interface LevelRowProps {
  level: Level;
  rowIdx: number;
  columns: ColumnDef[];
  isSelected: boolean;
  isExpanded: boolean;
  isEditingCell: { row: number; col: keyof Level } | null;
  editVal: string;
  rowColorOverride?: number[];
  generating: boolean;
  transparentBg: boolean;
  maxColors: number;
  statusColors: Record<string, string>;
  onToggleSelect: (num: number) => void;
  onToggleExpand: (num: number) => void;
  onStartEdit: (row: number, col: keyof Level) => void;
  onCommitEdit: () => void;
  onCancelEdit: () => void;
  onEditValChange: (v: string) => void;
  onDelete: (lv: Level) => void;
  onGenerateOne: (lv: Level) => void;
  onSetRowColors: (num: number, ids: number[]) => void;
  onClearRowColors: (num: number) => void;
}

function LevelRowImpl(props: LevelRowProps) {
  const {
    level, rowIdx, columns, isSelected, isExpanded, isEditingCell, editVal,
    rowColorOverride, generating, transparentBg, maxColors, statusColors,
    onToggleSelect, onToggleExpand, onStartEdit, onCommitEdit, onCancelEdit,
    onEditValChange, onDelete, onGenerateOne, onSetRowColors, onClearRowColors,
  } = props;

  const handleSelect = useCallback(() => onToggleSelect(level.level_number), [level.level_number, onToggleSelect]);
  const handleExpand = useCallback(() => onToggleExpand(level.level_number), [level.level_number, onToggleExpand]);
  const handleDelete = useCallback(() => onDelete(level), [level, onDelete]);
  const handleGen = useCallback(() => onGenerateOne(level), [level, onGenerateOne]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") onCommitEdit();
    if (e.key === "Escape") onCancelEdit();
  }

  const rowClassName = `border-b border-gray-100 transition-colors ${
    isSelected ? "bg-blue-50/50" : "hover:bg-gray-50"
  }`;

  return (
    <>
      <tr className={rowClassName}>
        <td className="w-10 px-3 py-2.5 text-center">
          <input
            type="checkbox"
            checked={isSelected}
            onChange={handleSelect}
            className="w-4 h-4 cursor-pointer"
            aria-label={`Level ${level.level_number} 선택`}
          />
        </td>
        {columns.map((col) => {
          const isEditing = isEditingCell?.row === rowIdx && isEditingCell?.col === col.key;
          const val = level[col.key];

          if (isEditing) {
            return (
              <td key={col.key} className="px-1 py-1">
                <input
                  autoFocus
                  value={editVal}
                  onChange={(e) => onEditValChange(e.target.value)}
                  onBlur={onCommitEdit}
                  onKeyDown={handleKeyDown}
                  className="w-full px-2 py-1 border border-blue-400 rounded text-sm outline-none ring-2 ring-blue-100"
                />
              </td>
            );
          }

          if (col.key === "status") {
            return (
              <td
                key={col.key}
                className="px-3 py-2.5 cursor-pointer"
                onClick={() => onStartEdit(rowIdx, col.key)}
              >
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    statusColors[String(val)] ?? "bg-gray-100 text-gray-600"
                  }`}
                >
                  {String(val || "draft")}
                </span>
              </td>
            );
          }

          if (col.key === "color_distribution") {
            const ids = parseColorDist(String(val ?? ""));
            return (
              <td
                key={col.key}
                className="px-3 py-2.5 cursor-pointer hover:bg-blue-50 transition-colors"
                onClick={() => onStartEdit(rowIdx, col.key)}
              >
                {ids.length > 0 ? (
                  <div className="flex flex-wrap gap-0.5" title={String(val)}>
                    {ids.map((id, i) => (
                      <span
                        key={i}
                        className="inline-block w-4 h-4 rounded-sm border border-gray-300"
                        style={{ backgroundColor: PALETTE_HEX[id] || "#ccc" }}
                        title={`c${id} ${COLOR_NAMES[id] || ""}`}
                      />
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-gray-300">—</span>
                )}
              </td>
            );
          }

          return (
            <td
              key={col.key}
              className="px-3 py-2.5 cursor-pointer hover:bg-blue-50 transition-colors group"
              onClick={() => onStartEdit(rowIdx, col.key)}
            >
              <span className="group-hover:underline decoration-dotted underline-offset-2">
                {String(val ?? "")}
              </span>
            </td>
          );
        })}
        <td className="px-2 py-2.5 whitespace-nowrap">
          <div className="flex items-center justify-end gap-1">
            <button
              onClick={handleExpand}
              className="w-7 h-7 flex items-center justify-center text-xs text-blue-600 hover:bg-blue-50 rounded transition-colors"
              title={isExpanded ? "접기" : "펼치기"}
              aria-label={isExpanded ? "접기" : "펼치기"}
            >
              {isExpanded ? "▲" : "▼"}
            </button>
            <button
              onClick={handleDelete}
              className="w-7 h-7 flex items-center justify-center text-sm text-red-500 hover:bg-red-50 rounded transition-colors"
              title="삭제"
              aria-label="삭제"
            >
              ✕
            </button>
          </div>
        </td>
      </tr>
      {isExpanded && (
        <ExpandedSection
          level={level}
          rowColorOverride={rowColorOverride}
          generating={generating}
          transparentBg={transparentBg}
          maxColors={maxColors}
          onGenerateOne={handleGen}
          onSetRowColors={onSetRowColors}
          onClearRowColors={onClearRowColors}
        />
      )}
    </>
  );
}

// 확장 행 — 별도 컴포넌트라 닫혀 있을 땐 아예 mount 안 됨
function ExpandedSection({
  level,
  rowColorOverride,
  generating,
  transparentBg,
  maxColors,
  onGenerateOne,
  onSetRowColors,
  onClearRowColors,
}: {
  level: Level;
  rowColorOverride?: number[];
  generating: boolean;
  transparentBg: boolean;
  maxColors: number;
  onGenerateOne: () => void;
  onSetRowColors: (num: number, ids: number[]) => void;
  onClearRowColors: (num: number) => void;
}) {
  const currentIds = rowColorOverride ?? parseColorDist(String(level.color_distribution || ""));
  const dim = computeImageSize(Number(level.field_columns) || 20, Number(level.field_rows) || 20);

  return (
    <tr className="border-b border-gray-100 bg-blue-50/30">
      <td colSpan={20} className="px-4 py-4">
        <div className="flex flex-col lg:flex-row gap-4">
          {/* 좌측: 이미지 미리보기 */}
          <div className="lg:w-48 shrink-0">
            <div className="text-xs font-semibold mb-1" style={{ color: "#000" }}>이미지</div>
            {level.image_base64 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`data:image/png;base64,${level.image_base64}`}
                alt={`Level ${level.level_number}`}
                className="w-full rounded border border-gray-200 bg-white"
                style={{
                  imageRendering: "pixelated",
                  aspectRatio: `${level.field_columns}/${level.field_rows}`,
                }}
              />
            ) : (
              <div
                className="w-full bg-gray-100 rounded border border-dashed border-gray-300 flex items-center justify-center text-xs text-gray-400"
                style={{ aspectRatio: `${level.field_columns}/${level.field_rows}` }}
              >
                미생성
              </div>
            )}
          </div>

          {/* 우측: 옵션 + 팔레트 + 생성 버튼 */}
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold mb-1" style={{ color: "#000" }}>설계 의도</div>
            <div className="text-xs text-gray-600 bg-white border border-gray-200 rounded p-2 mb-3 max-h-20 overflow-y-auto whitespace-pre-wrap">
              {String(level.designer_note || "(없음)")}
            </div>

            <div className="text-xs font-semibold mb-1" style={{ color: "#000" }}>
              색상 ({currentIds.length}/28)
              <span className="text-gray-400 ml-2 font-normal">— 클릭하여 override</span>
            </div>
            <div className="flex flex-wrap gap-1 mb-3">
              {Object.entries(PALETTE_HEX).map(([id, hex]) => {
                const numId = parseInt(id);
                const isOn = currentIds.includes(numId);
                return (
                  <button
                    key={id}
                    onClick={() => {
                      const next = isOn
                        ? currentIds.filter((c) => c !== numId)
                        : [...currentIds, numId];
                      onSetRowColors(level.level_number, next);
                    }}
                    className={`w-6 h-6 rounded border-2 flex items-center justify-center text-[8px] font-bold transition-all ${
                      isOn ? "border-black scale-110" : "border-gray-200 opacity-60 hover:opacity-100"
                    }`}
                    style={{
                      backgroundColor: hex,
                      color: numId === 7 || numId === 23 || numId === 17 ? "#000" : "#fff",
                    }}
                    title={`c${id} ${COLOR_NAMES[numId] || ""}`}
                  >
                    {id}
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={onGenerateOne}
                disabled={generating}
                className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
              >
                🎨 이 레벨 생성
              </button>
              {rowColorOverride && (
                <button
                  onClick={() => onClearRowColors(level.level_number)}
                  className="text-xs text-blue-600 hover:underline"
                >
                  색상 override 초기화
                </button>
              )}
              <span className="text-xs text-gray-500 ml-auto">
                {dim.width}×{dim.height}px
                {dim.pixelsPerCell > 0 ? ` (${dim.pixelsPerCell}px/cell)` : ""}
                {transparentBg ? " · 투명배경" : ""}
                {maxColors > 0 ? ` · 최대 ${maxColors}색` : ""}
              </span>
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

// 비교 함수: 핵심 prop이 안 바뀌면 리렌더 스킵
export const LevelRow = memo(LevelRowImpl, (prev, next) => {
  return (
    prev.level === next.level &&
    prev.isSelected === next.isSelected &&
    prev.isExpanded === next.isExpanded &&
    prev.rowColorOverride === next.rowColorOverride &&
    prev.generating === next.generating &&
    prev.transparentBg === next.transparentBg &&
    prev.maxColors === next.maxColors &&
    // 편집 상태는 본인 행일 때만 비교
    (prev.isEditingCell?.row === prev.rowIdx) === (next.isEditingCell?.row === next.rowIdx) &&
    (prev.isEditingCell?.row !== prev.rowIdx ||
      (prev.isEditingCell?.col === next.isEditingCell?.col && prev.editVal === next.editVal))
  );
});
