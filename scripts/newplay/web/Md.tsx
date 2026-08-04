"use client";

import React from "react";

/**
 * Md — 의존성 없는 최소 마크다운 렌더러.
 *
 * 왜 직접 쓰나:
 *   이 앱엔 마크다운 라이브러리가 없고, 코멘트를 whitespace-pre-wrap 으로만 뿌린다.
 *   에이전트 산출물은 표·코드블록·목록이 많은 문서라 평문으로는 읽기가 어렵다.
 *   CDN 로드는 CSP 에 막히고, 새 의존성을 추가하면 빌드 표면이 늘어난다.
 *
 * 안전:
 *   dangerouslySetInnerHTML 을 쓰지 않는다. 전부 React 엘리먼트로 만든다 —
 *   에이전트 출력에 HTML 이 섞여도 그대로 텍스트로 표시될 뿐 실행되지 않는다.
 *
 * 지원: 제목(#~####), 표, 코드펜스, 인용, 순서/비순서 목록, 수평선,
 *       인라인 `코드` · **굵게** · [링크](url)
 */

function inline(text: string, keyPrefix: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // 인라인 토큰을 한 번에 훑는다. 순서: 코드 → 링크 → 굵게
  const re = /(`[^`]+`)|(\[[^\]]+\]\([^)]+\))|(\*\*[^*]+\*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const k = `${keyPrefix}-i${i++}`;
    if (tok.startsWith("`")) {
      out.push(<code key={k} className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[0.92em] text-gray-800">{tok.slice(1, -1)}</code>);
    } else if (tok.startsWith("[")) {
      const mm = tok.match(/\[([^\]]+)\]\(([^)]+)\)/);
      const href = mm?.[2] || "";
      // http(s) 만 링크로. javascript: 같은 스킴은 그냥 텍스트로 둔다.
      if (/^https?:\/\//i.test(href)) {
        out.push(<a key={k} href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">{mm?.[1]}</a>);
      } else {
        out.push(tok);
      }
    } else {
      out.push(<strong key={k} className="font-semibold text-gray-900">{tok.slice(2, -2)}</strong>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function splitRow(line: string): string[] {
  return line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

export default function Md({ text, className = "" }: { text: string; className?: string }) {
  const lines = String(text || "").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 코드 펜스
    if (/^```/.test(line)) {
      const lang = line.slice(3).trim();
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
      i++; // 닫는 펜스
      blocks.push(
        <pre key={key++} className="my-2 max-w-full overflow-x-auto rounded border border-gray-200 bg-gray-50 p-2.5 text-[11px] leading-relaxed">
          {lang && <div className="mb-1 text-[10px] text-gray-400">{lang}</div>}
          <code className="font-mono text-gray-800">{body.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // 표 — 헤더 다음 줄이 구분선이면 표로 본다
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1])) {
      const head = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(splitRow(lines[i++]));
      blocks.push(
        <div key={key++} className="my-2 max-w-full overflow-x-auto">
          <table className="w-full border-collapse text-[11px]">
            <thead>
              <tr>{head.map((h, x) => (
                <th key={x} className="border border-gray-200 bg-gray-50 px-2 py-1 text-left font-semibold text-gray-700">{inline(h, `h${key}-${x}`)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {rows.map((r, y) => (
                <tr key={y}>{r.map((cd, x) => (
                  <td key={x} className="border border-gray-200 px-2 py-1 align-top text-gray-700">{inline(cd, `c${key}-${y}-${x}`)}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // 제목
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const lv = h[1].length;
      const cls = ["text-[15px] font-bold text-gray-900 mt-3 mb-1.5",
                   "text-[14px] font-bold text-gray-900 mt-3 mb-1.5",
                   "text-[13px] font-semibold text-gray-900 mt-2.5 mb-1",
                   "text-[12px] font-semibold text-gray-800 mt-2 mb-1"][lv - 1];
      blocks.push(<div key={key++} className={cls}>{inline(h[2], `h${key}`)}</div>);
      i++;
      continue;
    }

    // 수평선
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push(<hr key={key++} className="my-2.5 border-gray-200" />);
      i++;
      continue;
    }

    // 인용
    if (/^>\s?/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(
        <blockquote key={key++} className="my-2 border-l-2 border-gray-300 bg-gray-50 py-1 pl-2.5 text-[12px] text-gray-600">
          {body.map((b, x) => <div key={x}>{inline(b, `q${key}-${x}`)}</div>)}
        </blockquote>,
      );
      continue;
    }

    // 목록 (중첩은 들여쓰기만 반영)
    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      const items: { depth: number; text: string; ordered: boolean }[] = [];
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])) {
        const raw = lines[i];
        const depth = Math.floor((raw.match(/^\s*/)?.[0].length || 0) / 2);
        const ordered = /^\s*\d+\./.test(raw);
        items.push({ depth, ordered, text: raw.replace(/^\s*([-*+]|\d+\.)\s+/, "") });
        i++;
      }
      blocks.push(
        <ul key={key++} className="my-1.5 space-y-0.5 text-[12px] text-gray-700">
          {items.map((it, x) => (
            <li key={x} style={{ marginLeft: it.depth * 14 }} className="flex gap-1.5">
              <span className="shrink-0 text-gray-400">{it.ordered ? "•" : "–"}</span>
              <span className="min-w-0">{inline(it.text, `l${key}-${x}`)}</span>
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    // 빈 줄
    if (!line.trim()) { i++; continue; }

    // 문단 — 연속된 일반 줄을 묶는다
    const para: string[] = [];
    while (i < lines.length && lines[i].trim()
           && !/^```/.test(lines[i]) && !/^#{1,4}\s/.test(lines[i])
           && !/^>\s?/.test(lines[i]) && !/^\s*([-*+]|\d+\.)\s+/.test(lines[i])
           && !(lines[i].includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1]))) {
      para.push(lines[i++]);
    }
    blocks.push(
      <p key={key++} className="my-1.5 text-[12px] leading-relaxed text-gray-700">
        {para.map((p, x) => <React.Fragment key={x}>{inline(p, `p${key}-${x}`)}{x < para.length - 1 && <br />}</React.Fragment>)}
      </p>,
    );
  }

  return <div className={`min-w-0 ${className}`}>{blocks}</div>;
}
