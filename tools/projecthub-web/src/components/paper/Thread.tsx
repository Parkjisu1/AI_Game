"use client";

import { useEffect, useMemo, useRef, useState } from "react";

/* ══════════════════════════════════════════════════════════════
   Thread — 사람과 에이전트가 같은 방에 있는 대화

   이 제품의 시그니처다. 지금까지 스레드는 회색 상자를 세로로 쌓은
   "댓글 목록"이었다. 그래서 누가 사람이고 누가 기계인지, 무엇이 지시이고
   무엇이 결과인지 읽는 사람이 매번 다시 판단해야 했다.

   세 종류를 형태로 구분한다 — 색이 아니라 형태로.
     사람   : 흰 종이 위 본문. 이니셜 도장.
     에이전트: 살짝 파인 면 + **왼쪽 잉크 스트립**. 여백에 적힌 기계 메모.
     시스템  : 아바타 없는 한 줄 괘선. 상태 변화는 대화가 아니다.

   연속 발언은 묶는다(같은 화자면 머리글 생략, 간격 축소). 시각이 늘 보이면
   노이즈라 hover 에서만 드러낸다 — 대신 그룹의 첫 줄엔 항상 남긴다.
   ══════════════════════════════════════════════════════════════ */

export interface ThreadComment {
  author?: string;
  text?: string;
  created_at?: string;
  id?: string;
}

type Kind = "human" | "agent" | "system";

/** 에이전트 발언인가 — 역할 이름 규칙으로 판정한다(hermes/헤르메스/*_coder 등). */
const AGENT_RE = /hermes|헤르메스|jarvis|agent|bot|translator|lead|coder|reviewer|validator|optimizer|prompter|analyst|pm\b/i;
/** 상태만 알리는 한 줄인가 — 대화가 아니라 로그다. */
const SYSTEM_RE = /^(✅|⚠️|🔴|🟠|📊|📎|⏱|▶|⏸|🔒|ℹ️)/u;

function kindOf(c: ThreadComment): Kind {
  const t = (c.text || "").trim();
  if (SYSTEM_RE.test(t) && t.length < 220) return "system";
  return AGENT_RE.test(c.author || "") ? "agent" : "human";
}

function initials(name: string): string {
  const n = (name || "?").trim();
  // 한글은 첫 글자 하나가 이미 충분한 식별자다. 라틴은 두 글자.
  if (/[가-힣]/.test(n)) return n.slice(0, 1);
  const parts = n.split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] || "?") + (parts[1]?.[0] || "")).toUpperCase();
}

function timeOf(s?: string): string {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(+d)) return "";
  return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** 같은 화자가 5분 안에 이어 말하면 한 덩어리로 본다. */
const GROUP_MS = 5 * 60 * 1000;

export default function Thread({
  comments,
  onSend,
  onDelete,
  busy,
  placeholder = "지시를 적으세요 — Enter 전송 · Shift+Enter 줄바꿈",
}: {
  comments: ThreadComment[];
  onSend?: (text: string) => void | Promise<void>;
  onDelete?: (index: number) => void;
  busy?: boolean;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const [composing, setComposing] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  const rows = useMemo(() => {
    return comments.map((c, i) => {
      const kind = kindOf(c);
      const prev = comments[i - 1];
      const sameAuthor = prev && (prev.author || "") === (c.author || "") && kindOf(prev) === kind;
      const near =
        prev && c.created_at && prev.created_at
          ? Math.abs(+new Date(c.created_at) - +new Date(prev.created_at)) < GROUP_MS
          : false;
      return { c, i, kind, grouped: kind !== "system" && !!sameAuthor && !!near };
    });
  }, [comments]);

  // 새 발언이 붙으면 바닥으로. 읽는 중이면 방해하지 않는다.
  useEffect(() => {
    const el = endRef.current;
    if (!el) return;
    const box = el.parentElement;
    if (!box) return;
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 160;
    if (atBottom) el.scrollIntoView({ block: "end" });
  }, [comments.length]);

  async function send() {
    const t = draft.trim();
    if (!t || busy) return;
    setDraft("");
    if (taRef.current) taRef.current.style.height = "auto";
    await onSend?.(t);
  }

  return (
    <div className="pp-thread">
      <div className="pp-thread-scroll thin-scroll">
        {rows.length === 0 && (
          <div className="pp-thread-empty">
            아직 아무도 말하지 않았습니다.
            <span> 첫 지시를 적으면 담당 에이전트가 이 스레드로 들어옵니다.</span>
          </div>
        )}

        {rows.map(({ c, i, kind, grouped }) => {
          if (kind === "system") {
            return (
              <div key={c.id || i} className="pp-sysline">
                <span className="pp-sysline-text">{c.text}</span>
                <span className="pp-sysline-time">{timeOf(c.created_at)}</span>
              </div>
            );
          }
          return (
            <div key={c.id || i} className={`pp-msg pp-msg-${kind} ${grouped ? "grouped" : ""} group`}>
              <div className="pp-msg-gutter">
                {!grouped && (
                  <span className={`pp-avatar pp-avatar-${kind}`} title={c.author || ""}>
                    {initials(c.author || "")}
                  </span>
                )}
              </div>
              <div className="pp-msg-body">
                {!grouped && (
                  <div className="pp-msg-head">
                    <span className="pp-msg-author">{c.author || "(이름 없음)"}</span>
                    {kind === "agent" && <span className="pp-msg-tag">에이전트</span>}
                    <span className="pp-msg-time">{timeOf(c.created_at)}</span>
                    {onDelete && (
                      <button
                        className="pp-msg-del press"
                        onClick={() => onDelete(i)}
                        title="이 발언 삭제"
                        aria-label="발언 삭제"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                )}
                <div className="pp-msg-text">{c.text}</div>
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>

      {onSend && (
        <div className="pp-compose">
          <textarea
            ref={taRef}
            className="pp-compose-input"
            rows={1}
            value={draft}
            placeholder={placeholder}
            disabled={busy}
            onCompositionStart={() => setComposing(true)}
            onCompositionEnd={() => setComposing(false)}
            onChange={(e) => {
              setDraft(e.target.value);
              // 내용만큼 자란다 — 한 줄짜리 input 은 긴 지시를 쓰기 어렵다
              const el = e.target;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 200) + "px";
            }}
            onKeyDown={(e) => {
              // 한글 조합 중 Enter 는 확정이지 전송이 아니다
              if (e.key === "Enter" && !e.shiftKey && !composing) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <button className="pp-compose-send press" onClick={() => void send()} disabled={busy || !draft.trim()}>
            {busy ? "보내는 중" : "보내기"}
          </button>
        </div>
      )}
    </div>
  );
}
