"use client";
import { useState } from "react";

interface Props {
  count: number;          // 선택된 레벨 수
  onClose: () => void;
  onConfirm: (strength: number) => void;
}

// 일괄 Correction 시작 전 strength 슬라이더 다이얼로그.
// API key 안 받음 (서버측 봇이 storage_state로 인증).
export function BatchCorrectionDialog({ count, onClose, onConfirm }: Props) {
  const [strength, setStrength] = useState(0.10);

  const estMinutes = Math.max(1, Math.ceil(count * 60 / 60));

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl p-5 w-full max-w-sm shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-base" style={{ color: "#000" }}>
            🩹 일괄 Correction — {count}개 레벨
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none px-2">×</button>
        </div>

        <p className="text-xs text-gray-500 mb-4">
          선택된 {count}개 레벨을 순차로 처리합니다 (1개당 30~90초, 총 약 {estMinutes}분).
          결과는 자동으로 각 레벨의 이미지·JSON에 반영되고 원본은 백업됩니다.
        </p>

        <label className="block mb-4 text-sm" style={{ color: "#000" }}>
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium">Correction strength</span>
            <span className="text-cyan-600 font-bold">{strength.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={strength}
            onChange={(e) => setStrength(Number(e.target.value))}
            className="w-full accent-emerald-500"
          />
          <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
            <span>Subtle (0.00)</span>
            <span>PixelLab default 0.10</span>
            <span>Strong (1.00)</span>
          </div>
        </label>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded"
            style={{ color: "#000" }}
          >
            취소
          </button>
          <button
            onClick={() => onConfirm(strength)}
            className="px-4 py-1.5 text-sm bg-emerald-500 text-black rounded font-medium hover:bg-emerald-400"
          >
            시작
          </button>
        </div>
      </div>
    </div>
  );
}
