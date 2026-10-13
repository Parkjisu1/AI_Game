# 검증 기록

2026-09-21 실행. 아래 검증은 수집물·참조·산술에 대한 것이며 게임의 리텐션 성과 검증은 아니다.

## 명령과 결과

```powershell
node --check output/supercent-research-2026-09-21/collect.mjs
node --check output/supercent-research-2026-09-21/build-report.mjs
```

두 명령 모두 종료 코드 0, 구문 오류 출력 없음. 마지막 원문 추출 개선 이후 collect.mjs도 다시 구문 검사했다. Medium 접근 제한 때문에 개선 후 전체 수집 성공을 주장하지 않는다.

```powershell
node output/supercent-research-2026-09-21/build-report.mjs
```

종료 코드 0. 출력: `unique_article_urls=123`, `rss_bodies=106`, `additional_web_bodies=9`, `excerpt_only=8`, `reviewed_source_cards=28`, `completeness=UNVERIFIED_PARTIAL`.

```powershell
node output/supercent-research-2026-09-21/decision-math.mjs
```

종료 코드 0. 출력 재확인:

- 45/100의 95% Wilson 구간: 35.6145~54.7554%.
- 180/400: 40.1952~49.8999%.
- 450/1,000: 41.9415~48.0967%.
- 485/1,000: 45.4141~51.5974%.
- 40%→45% A/B 계획용 표본: 1,534명/군.
- 예시 잔존 유저 획득비용 A/B/C: $0.7333 / $0.5833 / $0.3913.
- Burger CPI 원수치 기준 감소율: 29.2683%.
- Hit & Run D0 원수치 기준 증가율: 55.8824%. 원문 서술 +54%와 불일치하여 근거 카드에 명시.

추가로 `node -e`로 JSON을 파싱해 글 ID 중복, 근거 카드의 원문 ID 매칭, Markdown 상대 경로 존재를 검사했다. 실제 출력은 [validation.json](validation.json)에 저장했다.

```json
{
  "catalog_rows": 123,
  "unique_ids": 123,
  "source_cards": 28,
  "unresolved_source_ids": [],
  "archive_months": 45,
  "broken_local_links": [],
  "invalid_titles": [],
  "status": "PASS"
}
```

RSS 본문에서 명시적인 잘림·유료 문구와 500자 미만 항목을 검색한 결과 표시된 의심 항목은 없었다. 최소 본문 길이는 1,390자였다. 이것만으로 원문과 완전히 동일하다고 증명할 수는 없다. 포함된 영상·이미지 텍스트 전체도 아니다.

광고 실험 이미지 3개의 시각 확인: 퍼널 잔존 증가율 그래프, 리텐션 증가율 그래프, RV 시청 빈도 증가율 그래프. RV가 코호트 인덱스별 +8~24%임을 확인했으며, 제목의 20%를 보편적인 D1 효과로 사용하지 않았다.

## 수행하지 않은 검증

실제 Sort 빌드 플레이, 사용자 행동 계측, D1 코호트 집계, 유료 광고 A/B 집행은 수행하지 않았다. 빌드·운영 데이터·집행 예산을 제공받지 않았기 때문이다. 접근 제한으로 블로그 전체 글 수와 누락 0건도 검증하지 못했다.
