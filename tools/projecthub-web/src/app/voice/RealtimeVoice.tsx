"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";

// 실시간 음성 대화 (OpenAI Realtime, WebRTC) — 배치형 녹음과 별개의 라이브 모드.
// 서버(/api/voice/realtime)가 단기 client secret 발급 → 브라우저가 OpenAI에 직접 연결.
// 툴: get_status(작업 현황), create_task(작업 생성 — 모델이 구두 확인 후 호출).

type LogLine = { who: "user" | "ai" | "sys"; text: string };

interface RtEvent {
  type: string;
  transcript?: string;
  call_id?: string;
  name?: string;
  arguments?: string;
  item?: { type?: string; call_id?: string; name?: string; arguments?: string };
  error?: { message?: string };
}

export default function RealtimeVoice() {
  const [live, setLive] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [err, setErr] = useState("");
  const [log, setLog] = useState<LogLine[]>([]);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const handledCalls = useRef<Set<string>>(new Set());
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const push = (l: LogLine) => setLog((xs) => [...xs.slice(-40), l]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [log]);

  const cleanup = () => {
    try { dcRef.current?.close(); } catch { /* ignore */ }
    try { pcRef.current?.close(); } catch { /* ignore */ }
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* ignore */ }
    dcRef.current = null; pcRef.current = null; streamRef.current = null;
    setLive(false);
  };
  useEffect(() => cleanup, []);

  const sendEvent = (ev: Record<string, unknown>) => {
    const dc = dcRef.current;
    if (dc && dc.readyState === "open") dc.send(JSON.stringify(ev));
  };

  async function execTool(name: string, args: Record<string, unknown>): Promise<unknown> {
    if (name === "get_status") {
      const r = await fetch("/api/assistant/status");
      return await r.json();
    }
    if (name === "create_task") {
      const title = String(args.title || "").trim();
      if (!title) return { ok: false, error: "제목 없음" };
      const r = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          description: String(args.description || ""),
          assignee: "hermes", status: "todo", priority: "medium",
          created_via: "voice_realtime",
        }),
      });
      if (r.ok) push({ who: "sys", text: `📝 작업 생성됨: ${title}` });
      return { ok: r.ok };
    }
    return { error: "unknown tool: " + name };
  }

  async function handleFunctionCall(callId?: string, name?: string, argsStr?: string) {
    if (!callId || !name || handledCalls.current.has(callId)) return;
    handledCalls.current.add(callId);
    push({ who: "sys", text: `⚙️ ${name} 실행 중…` });
    let out: unknown;
    try { out = await execTool(name, JSON.parse(argsStr || "{}")); }
    catch (e) { out = { error: e instanceof Error ? e.message : String(e) }; }
    sendEvent({
      type: "conversation.item.create",
      item: { type: "function_call_output", call_id: callId, output: JSON.stringify(out).slice(0, 8000) },
    });
    sendEvent({ type: "response.create" });
  }

  function handleEvent(ev: RtEvent) {
    switch (ev.type) {
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done":
        if (ev.transcript) push({ who: "ai", text: ev.transcript });
        break;
      case "conversation.item.input_audio_transcription.completed":
        if (ev.transcript) push({ who: "user", text: ev.transcript });
        break;
      case "response.function_call_arguments.done":
        handleFunctionCall(ev.call_id, ev.name, ev.arguments);
        break;
      case "response.output_item.done":
        if (ev.item?.type === "function_call")
          handleFunctionCall(ev.item.call_id, ev.item.name, ev.item.arguments);
        break;
      case "error":
        push({ who: "sys", text: "⚠️ " + (ev.error?.message || "오류") });
        break;
    }
  }

  const start = async () => {
    setConnecting(true); setErr(""); setLog([]); handledCalls.current.clear();
    try {
      const r = await fetch("/api/voice/realtime", { method: "POST" });
      const j = await r.json();
      if (!r.ok || !j.value) throw new Error(j.error ? `${j.error}${j.detail ? " — " + j.detail : ""}` : "세션 생성 실패");

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      stream.getTracks().forEach((t) => pc.addTrack(t, stream));
      pc.ontrack = (e) => { if (audioRef.current) audioRef.current.srcObject = e.streams[0]; };
      pc.onconnectionstatechange = () => {
        if (["failed", "disconnected", "closed"].includes(pc.connectionState)) {
          push({ who: "sys", text: "연결 종료됨" });
          cleanup();
        }
      };
      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;
      dc.onmessage = (e) => { try { handleEvent(JSON.parse(e.data)); } catch { /* ignore */ } };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const sdpRes = await fetch(`https://api.openai.com/v1/realtime/calls?model=${encodeURIComponent(j.model)}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${j.value}`, "Content-Type": "application/sdp" },
        body: offer.sdp,
      });
      if (!sdpRes.ok) throw new Error("WebRTC 연결 실패: " + (await sdpRes.text()).slice(0, 200));
      await pc.setRemoteDescription({ type: "answer", sdp: await sdpRes.text() });
      setLive(true);
      push({ who: "sys", text: "🎙️ 연결됨 — 말씀하세요 (예: \"지금 뭐 하고 있어?\", \"작업 하나 만들어줘\")" });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      cleanup();
    } finally {
      setConnecting(false);
    }
  };

  const IS_CLEAN = process.env.NEXT_PUBLIC_APP_THEME === "clean";
  return (
    <div className={`glass ${IS_CLEAN ? "" : "hud"} p-4 space-y-3`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={IS_CLEAN ? { background: "rgba(75,139,250,0.15)", color: "#6ca0f8" } : { background: "rgba(34,211,238,0.14)", color: "var(--neon)" }}>
            <Icon name="chat" size={15} />
          </span>
          <div>
            <div className="text-sm font-semibold">실시간 대화</div>
            <div className="text-[10px] mono tracking-hud text-gray-500 flex items-center gap-1">
              <span className={`dot ${live ? "dot-ok" : ""}`} style={live ? {} : { background: "#556" }} />
              {live ? "LIVE — 듣고 있음" : "OFFLINE"}
            </div>
          </div>
        </div>
        {!live ? (
          <button onClick={start} disabled={connecting}
            className="text-xs px-3 py-1.5 rounded-lg font-medium disabled:opacity-50"
            style={IS_CLEAN ? { background: "#2f6fed", color: "#ffffff" } : { background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018" }}>
            {connecting ? "연결 중…" : "대화 시작"}
          </button>
        ) : (
          <button onClick={cleanup}
            className="text-xs px-3 py-1.5 rounded-lg font-medium text-white"
            style={{ background: "var(--err)" }}>
            종료
          </button>
        )}
      </div>

      {err && <div className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs text-rose-700">{err}</div>}

      {log.length > 0 && (
        <div className="rounded-lg bg-black/20 p-2.5 max-h-52 overflow-y-auto space-y-1.5">
          {log.map((l, i) => (
            <div key={i} className="text-xs leading-relaxed flex gap-1.5">
              <span className="shrink-0">
                {l.who === "user" ? "🗣️" : l.who === "ai" ? "🤖" : "·"}
              </span>
              <span className={l.who === "sys" ? "text-gray-500" : l.who === "user" ? "text-gray-300" : "text-cyan-200"}>
                {l.text}
              </span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      <audio ref={audioRef} autoPlay className="hidden" />
      <div className="text-[10px] text-gray-500">
        현황 질문은 실데이터(get_status)로 답하고, 작업 생성은 구두 확인 후 보드에 등록됩니다.
      </div>
    </div>
  );
}
