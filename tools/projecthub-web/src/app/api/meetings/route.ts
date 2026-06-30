import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";

// 저장된 회의 전사·요약 (meeting_transcripts) — 본인 것만.
export async function GET() {
  const session = await auth();
  const email = (session?.user?.email || "").toLowerCase();
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    const db = await getDb();
    const docs = await db.collection("meeting_transcripts")
      .find({ created_by_email: email })
      .sort({ created_at: -1 })
      .limit(20)
      .toArray();
    const meetings = docs.map((d) => ({
      _id: String(d._id),
      summary: d.summary || "",
      transcript: d.transcript || "",
      tasks: Array.isArray(d.tasks) ? d.tasks : [],
      created_at: d.created_at || "",
    }));
    return NextResponse.json({ meetings });
  } catch (e) {
    return NextResponse.json({ meetings: [], error: String(e) }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  const session = await auth();
  const email = (session?.user?.email || "").toLowerCase();
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const id = new URL(req.url).searchParams.get("id");
  if (!id || !/^[a-f0-9]{24}$/i.test(id)) return NextResponse.json({ error: "id 필요/형식 오류" }, { status: 400 });
  try {
    const db = await getDb();
    await db.collection("meeting_transcripts").deleteOne({ _id: new ObjectId(id), created_by_email: email });
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
