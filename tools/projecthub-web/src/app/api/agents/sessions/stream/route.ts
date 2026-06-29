import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, authDisabled } from "@/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * hermes_agent_sessions 컬렉션 Change Stream을 SSE로 전파.
 * 에이전트가 새 호출을 기록할 때마다 대시보드 실시간 갱신.
 *
 * event: session   data: { session: {...} }
 * event: ping      data: {}  (25초마다 keep-alive)
 */
export async function GET(req: NextRequest) {
  if (!authDisabled) {
    const session = await auth();
    if (!session?.user?.email) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
  }

  const db = await getDb();
  const collection = db.collection("hermes_agent_sessions");

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      let closed = false;
      const safeEnqueue = (chunk: string) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(chunk));
        } catch {
          closed = true;
        }
      };
      const sendEvent = (event: string, data: unknown) => {
        safeEnqueue(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
      };

      sendEvent("ready", { ts: Date.now() });

      const changeStream = collection.watch([], { fullDocument: "updateLookup" });

      changeStream.on("change", (change) => {
        try {
          if (change.operationType === "insert" && change.fullDocument) {
            sendEvent("session", { session: change.fullDocument });
          }
        } catch { /* ignore */ }
      });

      const ping = setInterval(() => {
        if (closed) return;
        sendEvent("ping", { ts: Date.now() });
      }, 25_000);

      // 단일 정리 함수 — 에러/연결종료 양쪽에서 동일하게 자원 해제 (ping 타이머 + changeStream 누수 방지)
      const cleanup = () => {
        if (closed) return;
        closed = true;
        clearInterval(ping);
        changeStream.close().catch(() => {});
        req.signal.removeEventListener("abort", cleanup);
        try { controller.close(); } catch { /* ignore */ }
      };

      changeStream.on("error", (err) => {
        sendEvent("error", { message: err?.message || "changeStream error" });
        cleanup();
      });

      req.signal.addEventListener("abort", cleanup);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
