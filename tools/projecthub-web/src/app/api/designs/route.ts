import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * 갤러리 목록 조회
 * Query:
 *   page (1..)
 *   limit (default 20, max 50)
 *   sort: "newest" | "oldest" | "prompt"
 *   q: 프롬프트 검색어
 *   tag: 단일 태그 필터
 *   author: created_by_email 필터
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const page = Math.max(1, parseInt(url.searchParams.get("page") || "1", 10));
  const limit = Math.min(50, Math.max(1, parseInt(url.searchParams.get("limit") || "20", 10)));
  const sort = url.searchParams.get("sort") || "newest";
  const q = (url.searchParams.get("q") || "").trim();
  const tag = (url.searchParams.get("tag") || "").trim();
  const author = (url.searchParams.get("author") || "").trim().toLowerCase();

  const source = (url.searchParams.get("source") || "").trim();
  const taskId = (url.searchParams.get("task_id") || "").trim();

  const filter: Record<string, unknown> = {};
  if (q) {
    filter.prompt = { $regex: q, $options: "i" };
  }
  if (tag) filter.tags = tag;
  if (author) filter.created_by_email = author;
  if (source === "task" || source === "gallery") filter.source = source;
  if (taskId) filter.task_id = taskId;

  const sortSpec: Record<string, 1 | -1> =
    sort === "oldest"
      ? { created_at: 1 }
      : sort === "prompt"
      ? { prompt: 1 }
      : { created_at: -1 };

  const db = await getDb();
  const coll = db.collection("pixelforge_designs");
  const total = await coll.countDocuments(filter);
  const docs = await coll
    .find(filter, {
      projection: {
        prompt: 1,
        user_prompt: 1,
        tags: 1,
        model: 1,
        size: 1,
        n: 1,
        images: 1,
        created_by_email: 1,
        created_at: 1,
        source: 1,
        task_id: 1,
        task_title: 1,
        reference_filename: 1,
        has_ref: 1,
        mode_9slice: 1,
        border_px: 1,
        nine_slice: 1,
        source_design_id: 1,
        stars: 1,
        star_ratings: 1,
        comments: 1,
        inpaint: 1,
      },
    })
    .sort(sortSpec)
    .skip((page - 1) * limit)
    .limit(limit)
    .toArray();

  // 태그·작성자 집계 (필터 UI용)
  const tagAgg = await coll
    .aggregate([
      { $unwind: { path: "$tags", preserveNullAndEmptyArrays: false } },
      { $group: { _id: "$tags", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
      { $limit: 30 },
    ])
    .toArray();
  const authors = await coll.distinct("created_by_email");

  return NextResponse.json({
    designs: docs.map((d) => ({
      _id: String(d._id),
      prompt: d.prompt,
      user_prompt: d.user_prompt,
      tags: d.tags || [],
      model: d.model,
      size: d.size,
      n: d.n,
      images: d.images || [],
      created_by_email: d.created_by_email,
      created_at: d.created_at,
      source: d.source || "gallery",
      task_id: d.task_id,
      task_title: d.task_title,
      reference_filename: d.reference_filename || null,
      has_ref: Boolean(d.has_ref),
      mode_9slice: Boolean(d.mode_9slice),
      border_px: d.border_px,
      nine_slice: d.nine_slice || null,
      source_design_id: d.source_design_id || null,
      stars: d.stars || {},
      star_ratings: d.star_ratings || {},
      comments: d.comments || [],
      inpaint: Boolean(d.inpaint),
    })),
    page,
    limit,
    total,
    pages: Math.ceil(total / limit),
    facets: {
      tags: tagAgg.map((t) => ({ tag: t._id as string, count: t.count as number })),
      authors: authors.filter((a) => typeof a === "string"),
    },
  });
}
