// 모티프 유형별 style 레퍼런스 선택 (PixelLab 생성용)
//
// 문제: style_image 1개만 쓰면 캐릭터는 잘 나오지만 배경/구조 모티프가 약함.
// 해결: character / background / structure 3종 레퍼런스를 두고, 레벨 유형에 맞춰 선택.
//   - 유형 = 레벨의 style_type(수동 override) → 없으면 bl_category 자동 매핑
//   - 선택된 슬롯이 비면 공통 'style_image'로 fallback
import type { Db } from "mongodb";

export type StyleType = "character" | "background" | "structure";
export const STYLE_TYPES: StyleType[] = ["character", "background", "structure"];

// bl_category → style 유형 자동 매핑
export function categoryToStyleType(category?: string): StyleType {
  const c = (category || "").trim().toLowerCase();
  if (["nature", "seasonal", "holiday", "art"].includes(c)) return "background";
  if (["geometric", "symbol", "abstract"].includes(c)) return "structure";
  // animal / character / food / object / 미상 → 캐릭터(단일 모티프)
  return "character";
}

// 레벨 유형 결정: 수동 override(style_type) 우선, 없으면 category 자동
export function resolveStyleType(level: { style_type?: string; bl_category?: string } | undefined): StyleType {
  const ov = (level?.style_type || "").trim().toLowerCase();
  if (ov === "character" || ov === "background" || ov === "structure") return ov;
  return categoryToStyleType(level?.bl_category);
}

export interface StyleRef {
  base64: string;
  width: number;
  height: number;
  styleType: StyleType;
  usedKey: string; // 실제 사용된 settings key (디버깅/로그용)
}

// 유형별 레퍼런스 조회 (없으면 공통 style_image로 fallback)
export async function getStyleRef(db: Db, styleType: StyleType): Promise<StyleRef | null> {
  const keys = [`style_image_${styleType}`, "style_image"];
  for (const key of keys) {
    const doc = await db.collection("pixelforge_settings").findOne({ key });
    if (doc?.base64) {
      return {
        base64: doc.base64 as string,
        width: (doc.width as number) || 64,
        height: (doc.height as number) || 64,
        styleType,
        usedKey: key,
      };
    }
  }
  return null;
}
