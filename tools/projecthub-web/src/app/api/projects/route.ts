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

    // 레지스트리 로드 — board_hidden=true는 작업 보드에서 제외.
    // (게임이 아닌 내부 도구는 Hermes 라우팅은 유지하되 보드엔 노출하지 않는다.
    //  레지스트리에서 지우면 hermes_projects.repo 기반 라우팅이 깨지므로 삭제 대신 플래그.)
    const registry = await db.collection("hermes_projects")
      .find({ board_hidden: { $ne: true } },
            { projection: { project: 1, display_name: 1, genre: 1, repo: 1, profile: 1 } })
      .toArray();

    // 프로젝트 메타 구성. clean 인스턴스(비게임 팀)는 balloonflow 기본값 없이 레지스트리만.
    const IS_CLEAN = process.env.NEXT_PUBLIC_APP_THEME === "clean";
    const ids = new Set<string>(IS_CLEAN ? [] : ["balloonflow"]);
    const meta: Record<string, Meta> = IS_CLEAN ? {} : {
      balloonflow: { name: "BalloonFlow", subtitle: "Unity 퍼즐 · 실제 프로젝트", icon: "balloon" },
    };
    for (const r of registry) {
      const id = String(r.project || "").toLowerCase();
      if (!id) continue;
      ids.add(id);
      if (!meta[id]) {
        const engine = (r.profile as { engine?: string } | undefined)?.engine || r.genre || "";
        const repo = r.repo as { type?: string; owner?: string; name?: string } | undefined;
        meta[id] = {
          name: r.display_name || id,
          subtitle: IS_CLEAN && repo?.owner && repo?.name ? `${repo.owner}/${repo.name}` : `${engine} · 온보딩`,
          icon: repo?.type === "unity" ? "balloon" : "box",
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
