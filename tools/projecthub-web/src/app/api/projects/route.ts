import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

// 프로젝트 목록 — hermes_projects 레지스트리(온보딩) + BalloonFlow(기본).
// 각 프로젝트 진행률은 실제 task(pixelforge_tasks.project) 완료율로 계산.
// 확장성: project_onboard.py로 온보딩하면 여기 자동 반영.
type Meta = { name: string; subtitle: string; icon: string };

export async function GET() {
  try {
    const db = await getDb();
    const col = db.collection("pixelforge_tasks");

    // 레지스트리 로드
    const registry = await db.collection("hermes_projects")
      .find({}, { projection: { project: 1, display_name: 1, genre: 1, repo: 1, profile: 1 } })
      .toArray();

    // 프로젝트 메타 구성 (balloonflow 기본 포함)
    const ids = new Set<string>(["balloonflow"]);
    const meta: Record<string, Meta> = {
      balloonflow: { name: "BalloonFlow", subtitle: "Unity 퍼즐 · 실제 프로젝트", icon: "balloon" },
    };
    for (const r of registry) {
      const id = String(r.project || "").toLowerCase();
      if (!id) continue;
      ids.add(id);
      if (!meta[id]) {
        const engine = (r.profile as { engine?: string } | undefined)?.engine || r.genre || "";
        meta[id] = {
          name: r.display_name || id,
          subtitle: `${engine} · 온보딩`,
          icon: (r.repo as { type?: string } | undefined)?.type === "unity" ? "balloon" : "box",
        };
      }
    }

    // 프로젝트별 카운트 (balloonflow = project==balloonflow OR 미지정 legacy task)
    const projects = await Promise.all(
      [...ids].map(async (id) => {
        const q = id === "balloonflow"
          ? { $or: [{ project: "balloonflow" }, { project: { $exists: false } }, { project: null }, { project: "" }] }
          : { project: id };
        const [total, done, inProgress, review] = await Promise.all([
          col.countDocuments(q),
          col.countDocuments({ ...q, status: "done" }),
          col.countDocuments({ ...q, status: "in_progress" }),
          col.countDocuments({ ...q, status: "review" }),
        ]);
        const m = meta[id];
        return {
          id, name: m.name, subtitle: m.subtitle, icon: m.icon,
          href: `/tasks?project=${id}`,
          progress: total > 0 ? Math.round((done / total) * 100) : 0,
          done, total, inProgress, review,
        };
      })
    );

    projects.sort((a, b) => b.total - a.total);
    return NextResponse.json({ projects });
  } catch (e) {
    return NextResponse.json({ projects: [], error: String(e) }, { status: 500 });
  }
}
