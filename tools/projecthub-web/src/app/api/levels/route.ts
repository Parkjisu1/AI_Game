import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * pixelforge_levels 컬렉션 — design/level 분과가 생성한 격자 레벨 목록.
 *
 * Query:
 *   page (1..)
 *   limit (default 20, max 50)
 *   sort: "newest" | "oldest"
 *   q: 이름·task_title 검색
 *   symmetry: 단일 대칭 종류 필터
 *   author: created_by_email 필터
 *   task_id: 단일 task의 결과물만
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const page = Math.max(1, parseInt(url.searchParams.get("page") || "1", 10));
  const limit = Math.min(50, Math.max(1, parseInt(url.searchParams.get("limit") || "20", 10)));
  const sort = url.searchParams.get("sort") || "newest";
  const q = (url.searchParams.get("q") || "").trim();
  const symmetry = (url.searchParams.get("symmetry") || "").trim();
  const author = (url.searchParams.get("author") || "").trim().toLowerCase();
  const taskId = (url.searchParams.get("task_id") || "").trim();
  const mood = (url.searchParams.get("mood") || "").trim().toLowerCase();
  const teamId = (url.searchParams.get("team_id") || "").trim();
  const unrated = url.searchParams.get("unrated") === "1";
  // width/height/별점 필터
  const width = parseInt(url.searchParams.get("width") || "", 10);
  const height = parseInt(url.searchParams.get("height") || "", 10);
  const minScore = parseInt(url.searchParams.get("min_score") || "", 10);
  const exactScore = parseInt(url.searchParams.get("score") || "", 10);

  const filter: Record<string, unknown> = {};
  if (q) {
    filter.$or = [
      { name: { $regex: q, $options: "i" } },
      { task_title: { $regex: q, $options: "i" } },
    ];
  }
  if (symmetry) filter.symmetry = symmetry;
  if (author) filter.created_by_email = author;
  if (taskId) filter.task_id = taskId;
  if (mood) filter.mood = mood;
  if (teamId) filter.team_id = teamId;
  if (unrated) filter.user_score = null;
  // width / height 정확 일치 필터
  if (Number.isFinite(width) && width > 0) filter.width = width;
  if (Number.isFinite(height) && height > 0) filter.height = height;
  // 별점: exactScore 우선, 없으면 minScore
  if (Number.isFinite(exactScore) && exactScore >= 1 && exactScore <= 5) {
    filter.user_score = exactScore;
  } else if (Number.isFinite(minScore) && minScore >= 1 && minScore <= 5) {
    filter.user_score = { $gte: minScore };
  }
  // style — batch_meta.style 또는 team_id가 batch_<style>_<mood> 형식일 때
  const style = (url.searchParams.get("style") || "").trim();
  if (style) filter["batch_meta.style"] = style;

  const sortSpec: Record<string, 1 | -1> =
    sort === "oldest" ? { created_at: 1 } : { created_at: -1 };

  const db = await getDb();
  // pixelforge_levels는 BalloonFlow 게임 자체 레벨 데이터(chapter/gimmick 등) 300건이 있는 별개 컬렉션.
  // 우리 grid level은 schema가 다르므로 pixelforge_grid_levels로 격리.
  const coll = db.collection("pixelforge_grid_levels");
  const total = await coll.countDocuments(filter);
  const docs = await coll
    .find(filter, {
      projection: {
        // cells는 무거우므로 목록에서는 제외 — 상세 fetch 시에만 포함
        cells: 0,
      },
    })
    .sort(sortSpec)
    .skip((page - 1) * limit)
    .limit(limit)
    .toArray();

  // facet: 사용 중인 symmetry 종류
  const symAgg = await coll
    .aggregate([
      { $group: { _id: "$symmetry", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
    ])
    .toArray();
  const authors = await coll.distinct("created_by_email");
  // facet: mood 분포 (batch + competitive)
  const moodAgg = await coll
    .aggregate([
      { $match: { mood: { $exists: true, $ne: null } } },
      { $group: { _id: "$mood", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
    ])
    .toArray();
  // facet: style 분포 (batch_meta.style)
  const styleAgg = await coll
    .aggregate([
      { $match: { "batch_meta.style": { $exists: true, $ne: null } } },
      { $group: { _id: "$batch_meta.style", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
    ])
    .toArray();
  // facet: 사용 가능한 width / height 값
  const widthAgg = await coll
    .aggregate([
      { $group: { _id: "$width", count: { $sum: 1 } } },
      { $match: { _id: { $ne: null } } },
      { $sort: { _id: 1 } },
    ])
    .toArray();
  const heightAgg = await coll
    .aggregate([
      { $group: { _id: "$height", count: { $sum: 1 } } },
      { $match: { _id: { $ne: null } } },
      { $sort: { _id: 1 } },
    ])
    .toArray();
  // facet: 별점 분포
  const scoreAgg = await coll
    .aggregate([
      { $group: { _id: "$user_score", count: { $sum: 1 } } },
      { $sort: { _id: 1 } },
    ])
    .toArray();

  return NextResponse.json({
    levels: docs.map((d) => ({
      _id: String(d._id),
      name: d.name,
      task_id: d.task_id,
      task_title: d.task_title,
      created_by_email: d.created_by_email,
      created_at: d.created_at,
      width: d.width,
      height: d.height,
      symmetry: d.symmetry,
      palette: d.palette || [],
      per_color_count: d.per_color_count || {},
      seed: d.seed,
      png_filename: d.png_filename,
      validation: d.validation || null,
      mood: d.mood || null,
      team_id: d.team_id || null,
      pattern_chosen: d.pattern_chosen || null,
      user_score: d.user_score ?? null,
    })),
    page,
    limit,
    total,
    pages: Math.ceil(total / limit),
    facets: {
      symmetries: symAgg.map((s) => ({ symmetry: s._id as string, count: s.count as number })),
      authors: authors.filter((a) => typeof a === "string"),
      moods: moodAgg.map((m) => ({ mood: m._id as string, count: m.count as number })),
      styles: styleAgg.map((s) => ({ style: s._id as string, count: s.count as number })),
      widths: widthAgg.map((w) => ({ width: w._id as number, count: w.count as number })),
      heights: heightAgg.map((h) => ({ height: h._id as number, count: h.count as number })),
      scores: scoreAgg.map((s) => ({ score: s._id as number | null, count: s.count as number })),
    },
  });
}
