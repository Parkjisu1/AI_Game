import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

// 실제 프로젝트 — 현재 Mother에는 BalloonFlow 하나만 존재.
// 진행률은 실제 task 완료율로 계산(빈껍데기 아님). 프로젝트가 늘면 여기서 확장.
export async function GET() {
  try {
    const db = await getDb();
    const col = db.collection("pixelforge_tasks");
    const [total, done, inProgress, review] = await Promise.all([
      col.countDocuments({}),
      col.countDocuments({ status: "done" }),
      col.countDocuments({ status: "in_progress" }),
      col.countDocuments({ status: "review" }),
    ]);
    const progress = total > 0 ? Math.round((done / total) * 100) : 0;
    const latest = await col.find({}, { projection: { updated_at: 1 } }).sort({ updated_at: -1 }).limit(1).toArray();

    const projects = [
      {
        id: "balloonflow",
        name: "BalloonFlow",
        subtitle: "Unity 퍼즐 · 실제 프로젝트",
        icon: "balloon",
        progress,
        done,
        total,
        inProgress,
        review,
        href: "/balloonflow",
        updatedAt: latest[0]?.updated_at || null,
      },
    ];
    return NextResponse.json({ projects });
  } catch (e) {
    return NextResponse.json({ projects: [], error: String(e) }, { status: 500 });
  }
}
