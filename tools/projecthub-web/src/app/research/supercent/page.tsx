import type { Metadata } from "next";
import Link from "next/link";
import content from "./content.json";
import ResearchTools from "./ResearchTools";
import styles from "./research.module.css";

export const metadata: Metadata = {
  title: "Sort 퍼즐 성장 연구 | ProjectHub",
  description: "Supercent 공개 자료를 Sort 퍼즐의 D1 45%와 CPI 개선 실험으로 연결한 PM 실행안",
};

export default function ResearchPage() {
  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <Link href="/" className={styles.back}>← ProjectHub 홈</Link>
        <p className={styles.kicker}>게임 성장 연구 / SUPERCENT / 2026.09.21</p>
        <h1>Sort 퍼즐,<br />다시 플레이하게 만드는 것부터.</h1>
        <p className={styles.lead}>D1 <strong>45% 이상</strong>을 목표로, 유입의 질을 지키면서 CPI를 낮추는 실행안.</p>
        <p>첫 이동 → 첫 완료 → 첫 실패와 재도전. 실제로 막히는 구간 하나를 찾고, 작은 수정으로 검증합니다.</p>
        <div className={styles.stats}>
          <div><strong>9</strong><span>조건별 실험</span></div>
          <div><strong>{content.notes.length}</strong><span>검토한 근거</span></div>
          <div><strong>{content.catalog.length}</strong><span>발견한 글</span></div>
          <div><strong>{content.coverage.rss_bodies + content.coverage.additional_web_bodies}</strong><span>본문 확보</span></div>
        </div>
      </header>
      <div className={styles.notice}>
        <strong>읽기 전 알아둘 범위</strong>
        <p>현재 빌드와 실측 지표가 없는 상태에서 만든 PM 가설입니다. Supercent 사례의 수치를 이 게임의 예상 개선폭으로 사용하지 않습니다. 발견한 123건 중 본문 115건, 발췌·껍데기만 확인한 글 8건입니다. Medium 접근 제한으로 전체 글 수를 확정하지 못했으며, 전수 수집 완료가 아닙니다.</p>
      </div>
      <nav className={styles.jump} aria-label="연구 목차">
        <a href="#first">먼저 할 일</a><a href="#plan">전체 실행안</a><a href="#calculator">D1·비용 계산</a><a href="#sources">근거 28개</a><a href="#catalog">수집 목록</a><a href="#downloads">다운로드</a>
      </nav>
      <section id="first" className={styles.section}>
        <p className={styles.kicker}>01 / 먼저 할 일</p>
        <h2>기능보다, 이탈하는 순간을 먼저 고릅니다.</h2>
        <div className={styles.priorities}>
          <article><span>01</span><h3>첫 정리를 스스로 끝내는가</h3><p>선택한 대상·가능한 목적지·이동 불가 이유가 읽히는지 관찰합니다. 첫 수에서 막힐 때 E01, 완료 후 멈출 때 E02를 선택합니다.</p></article>
          <article><span>02</span><h3>실패 후 한 판 더 하는가</h3><p>첫 실패가 납득되는지, 무료 재시작을 찾는지 확인합니다. 특정 레벨에 집중되면 E03, 재시작 과정에 막히면 E04입니다.</p></article>
          <article><span>03</span><h3>광고의 재미가 게임에도 있는가</h3><p>실제 플레이로 정리 쾌감·한 수 해결·완성 변화의 세 훅을 비교합니다. 싼 CPI 후보도 성숙 D1을 확인한 뒤 남깁니다.</p></article>
        </div>
        <p className={styles.small}>우선순위는 현재 지표가 없을 때의 조사 순서입니다. 이미 잘되는 구간을 다시 만들지 말고, 관측된 병목에 해당하는 실험 하나를 고릅니다.</p>
      </section>
      <section id="plan" className={styles.section}>
        <p className={styles.kicker}>02 / 실행안</p>
        <h2>적용 조건, 바꿀 것, 채택·중단 기준</h2>
        <p>제목을 열면 보고서의 해당 내용을 읽을 수 있습니다. 실험 카드와 판정 기준을 그대로 수록했습니다.</p>
        {content.sections.map((section, i) => (
          <details key={section.id} id={section.id} className={styles.chapter} open={i === 3}>
            <summary>{section.title}</summary>
            <div className={styles.prose} dangerouslySetInnerHTML={{ __html: section.html }} />
          </details>
        ))}
      </section>
      <ResearchTools catalog={content.catalog} mode="calculator" />
      <section id="sources" className={styles.section}>
        <p className={styles.kicker}>04 / 근거</p>
        <h2>확인한 사실과 Sort 적용 가설을 나눠 읽습니다.</h2>
        <p>A는 회사가 보고한 대조군 실험, B는 복합 개선 전후 사례입니다. 개별 등급의 설명과 한계를 함께 확인하세요. 발췌만 확보한 자료는 그 범위를 표시했습니다.</p>
        <div className={styles.sources}>
          {content.notes.map(note => (
            <details key={note.key} id={note.key} className={styles.source}>
              <summary><span>{note.key}</span>{note.title}<small>{note.evidence}</small></summary>
              <dl>
                <dt>원문에서 확인한 내용</dt><dd>{note.observed}</dd>
                <dt>이번 Sort에 적용할 가설</dt><dd>{note.sort_application}</dd>
                <dt>이 근거의 한계</dt><dd>{note.limitations}</dd>
              </dl>
              <p className={styles.small}>원문 내 위치: {note.locator}</p>
              <a href={note.url} target="_blank" rel="noreferrer">원문 열기 ↗</a>
            </details>
          ))}
        </div>
      </section>
      <ResearchTools catalog={content.catalog} mode="catalog" />
      <section id="downloads" className={styles.section}>
        <p className={styles.kicker}>06 / 다운로드</p>
        <h2>팀과 함께 검토하고, 실험 기록을 남기세요.</h2>
        <div className={styles.downloads}>{content.downloads.map(item => (
          <a key={item.file} href={`/research/supercent/files/${item.file}`} download>{item.label} <span>↓</span></a>
        ))}</div>
        <p className={styles.small}>원문 전문을 재배포하는 자료집이 아닙니다. 직접 작성한 분석·요약, 출처 링크, 수집 상태와 재현 자료를 제공합니다. 수집 방법과 누락 범위는 ‘수집 범위 JSON’과 ‘조사 방법과 파일 안내’에서 확인할 수 있습니다.</p>
      </section>
    </div>
  );
}
