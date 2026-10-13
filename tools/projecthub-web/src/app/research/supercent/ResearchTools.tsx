"use client";
import { useMemo, useState } from "react";
import styles from "./research.module.css";

type Article = { id: string; title: string; url: string; published_at: string | null; body_status: string; topic_auto: string; review_note: string | null };

export default function ResearchTools({ catalog, mode }: {catalog: Article[]; mode: "calculator" | "catalog"}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [count, setCount] = useState("");
  const [returned, setReturned] = useState("");
  const [spend, setSpend] = useState("");
  const [installs, setInstalls] = useState("");
  const articles = useMemo(() => catalog.filter(a => {
    const match = `${a.title} ${a.topic_auto} ${a.id}`.toLowerCase().includes(query.trim().toLowerCase());
    return match && (status === "all" || (status === "excerpt" ? a.body_status === "web_excerpt_or_shell" : status === "reviewed" ? !!a.review_note : a.body_status !== "web_excerpt_or_shell"));
  }).sort((a,b) => (b.published_at || "").localeCompare(a.published_at || "")), [catalog,query,status]);
  const n = Number(count), r = Number(returned), cost = Number(spend), paidInstalls = Number(installs);
  const valid = count !== "" && returned !== "" && Number.isSafeInteger(n) && Number.isSafeInteger(r) && n > 0 && r >= 0 && r <= n;
  const validCost = spend !== "" && Number.isFinite(cost) && cost >= 0;
  const validInstalls = installs !== "" && Number.isSafeInteger(paidInstalls) && paidInstalls > 0;
  const p = valid ? r/n : 0, z=1.959963984540054;
  const denom = 1+z*z/n, center=(p+z*z/(2*n))/denom, margin=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom;
  const pct = (v: number) => `${(v*100).toFixed(2)}%`;

  if (mode === "calculator") return (
    <section id="calculator" className={styles.section}>
      <p className={styles.kicker}>03 / 의사결정 계산</p>
      <h2>45%를 관측한 것과, 안정적으로 넘은 것은 다릅니다.</h2>
      <p>관측이 끝난 같은 국가·OS·빌드·유입 코호트를 넣으세요. D1은 전체 신규 플레이어가 분모입니다. 입력값은 브라우저 안에서만 계산하며 저장·전송하지 않습니다.</p>
      <div className={styles.calculator}>
        <div className={styles.fields}>
          <label>성숙 신규 플레이어 수<input inputMode="numeric" type="number" min="1" step="1" value={count} onChange={e=>setCount(e.target.value)} placeholder="관측 창이 끝난 인원" /></label>
          <label>그중 D1 재방문자 수<input inputMode="numeric" type="number" min="0" step="1" value={returned} onChange={e=>setReturned(e.target.value)} placeholder="다음 날 돌아온 인원" /></label>
          <label>같은 코호트 광고비 (선택)<input inputMode="decimal" type="number" min="0" step="any" value={spend} onChange={e=>setSpend(e.target.value)} placeholder="사용 중인 통화 단위" /></label>
          <label>같은 광고비의 설치 수 (선택)<input inputMode="numeric" type="number" min="1" step="1" value={installs} onChange={e=>setInstalls(e.target.value)} placeholder="CPI 계산용 MMP 설치 수" /></label>
        </div>
        <div className={styles.result} aria-live="polite">
          {valid ? <>
            <p>D1 <strong>{pct(p)}</strong></p>
            <p>95% Wilson 구간 <b>{pct(Math.max(0,center-margin))} ~ {pct(Math.min(1,center+margin))}</b></p>
            <p>{p < .45 ? "D1 점추정이 목표에 미달합니다." : center-margin >= .45 ? "이 표본 가정에서는 구간 하한도 45% 이상입니다." : "점추정은 목표를 충족하지만 구간 하한은 45% 미만입니다."}</p>
            {validCost && <p>D1 잔존 유저당 획득비용: <b>{r > 0 ? (cost/r).toFixed(3) : "계산 불가 · 재방문자 0명"}</b> (입력 통화)</p>}
          </> : <p>{count || returned ? "신규 인원은 1 이상, 재방문자는 0 이상이며 신규 인원 이하인 정수로 입력하세요." : "실제 코호트 인원을 입력하면 결과가 표시됩니다."}</p>}
          {validCost && validInstalls && <p>CPI: <b>{(cost/paidInstalls).toFixed(3)}</b> (입력 통화 / 설치)</p>}
          {spend !== "" && !validCost && <p>광고비는 0 이상의 유효한 숫자여야 합니다.</p>}
          {installs !== "" && !validInstalls && <p>설치 수는 1 이상의 정수여야 합니다.</p>}
        </div>
      </div>
      <p className={styles.small}>달력 D1과 설치 후 24~48시간 D1을 섞지 않습니다. 비용은 동일 코호트에 대응할 때만 의미가 있고 LTV·이익을 뜻하지 않습니다. Wilson 구간은 독립된 사용자 표본을 가정하며, 유입 편향이나 매일 결과를 보다가 종료하는 문제를 해결하지 않습니다.</p>
    </section>
  );
  return (
    <section id="catalog" className={styles.section}>
      <p className={styles.kicker}>05 / 수집 목록</p>
      <h2>어떤 글을 확보했는지 추적할 수 있습니다.</h2>
      <div className={styles.filters}>
        <label>제목·주제 검색<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="FTUE, 광고, CPI…" /></label>
        <label>수집·검토 상태<select value={status} onChange={e=>setStatus(e.target.value)}><option value="all">전체</option><option value="body">본문 확보</option><option value="excerpt">발췌·껍데기만 확인</option><option value="reviewed">근거카드 작성</option></select></label>
      </div>
      <p className={styles.small} aria-live="polite">{articles.length} / {catalog.length}건 · 날짜 내림차순 · 주제는 자동 분류</p>
      <div className={styles.catalog}>
        {articles.length === 0 ? <p>조건에 맞는 글이 없습니다. 검색어 또는 필터를 바꿔보세요.</p> : articles.map(article => (
          <article key={article.id}>
            <div><time>{article.published_at?.slice(0,10) || "날짜 미확인"}</time><span>{article.body_status === "web_excerpt_or_shell" ? "발췌·껍데기" : "본문 확보"}</span>{article.review_note && <span>근거카드</span>}</div>
            <a href={article.url} target="_blank" rel="noreferrer">{article.title} ↗</a>
            <p>{article.topic_auto}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
