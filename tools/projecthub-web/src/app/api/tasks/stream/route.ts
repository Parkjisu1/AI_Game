import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, authDisabled } from "@/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Server-Sent Events 스트림 — pixelforge_tasks 변경사항 실시간 푸시.
 *
 * 이벤트 형식:
 *   event: insert  data: { task: {...} }
 *   event: update  data: { task: {...} }
 *   event: delete  data: { _id: "..." }
 *   event: ping    data: {}                  (25초마다 keep-alive)
 *
 * 클라이언트는 EventSource로 연결. 끊기면 브라우저가 자동 재연결.
 * Hermes watcher가 update를 쓰면 여기서 감지되어 모든 열린 세션에 브로드캐스트.
 */
export async function GET(req: NextRequest) {
  // 인증: middleware/proxy에서 제외했으므로 여기서 직접 검사 (SSE 버퍼링 방지용)
  if (!authDisabled) {
    const session = await auth();
    if (!session?.user?.email) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
  }

  const db = await getDb();
  const collection = db.collection("pixelforge_tasks");

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

      // 최초 연결 확인 이벤트
      sendEvent("ready", { ts: Date.now() });

      // MongoDB Change Stream 시작 (fullDocument: updateLookup → update시 전체 문서 반환)
      const changeStream = collection.watch([], { fullDocument: "updateLookup" });

      changeStream.on("change", (change) => {
        try {
          if (change.operationType === "insert") {
            sendEvent("insert", { task: change.fullDocument });
          } else if (change.operationType === "update" || change.operationType === "replace") {
            if (change.fullDocument) {
              sendEvent("update", { task: change.fullDocument });
            }
          } else if (change.operationType === "delete") {
            sendEvent("delete", { _id: String(change.documentKey?._id || "") });
          }
        } catch {
          /* ignore single-event errors */
        }
      });

      // Keep-alive ping (일부 프록시가 30초 이상 idle이면 끊음)
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
        // Change Stream 에러 — 클라이언트에 알리고 자원 전체 정리 (재연결은 브라우저가 담당)
        sendEvent("error", { message: err?.message || "changeStream error" });
        cleanup();
      });

      // 클라이언트 연결 종료 시 정리
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
