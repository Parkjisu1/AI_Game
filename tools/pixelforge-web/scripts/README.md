# Field-map V2 migration scripts

V1(`snapToGrid`, 픽셀당 28색 매칭) → V2(`snapToGridV2`, unfake-style K색 정제 + Lab ΔE K→28) 전환용.

## 사전 준비

- `.env.local` 에 `MONGODB_URI` 있어야 함 (프로덕션과 동일 DB 쓰지 말 것 — 먼저 스테이징/사본에서 테스트 권장)
- `tsx` 설치: `npm i -D tsx` (또는 `npx tsx ...`로 즉석 실행)

## 1. 샘플 비교 (DB 쓰기 없음)

레벨 1개만 V1/V2 나란히 돌려서 diff·팔레트 매핑 출력.

```bash
npx tsx scripts/compare-fieldmap-v1-v2.ts --level 1
npx tsx scripts/compare-fieldmap-v1-v2.ts --level 1 --verbose   # field_map 전체 덤프
```

`--verbose`는 V1/V2 field_map 전체를 찍어줌 — 눈으로 셀별 차이 확인용.

## 2. 백업 (필수, 1회)

모든 레벨의 `field_map`을 `field_map_v1_backup`으로 복사. 중복 실행 안전(이미 있으면 skip).

```bash
npx tsx scripts/migrate-fieldmap-v2.ts --backup
```

`--migrate`는 `field_map_v1_backup` 없는 문서가 있으면 **중단**됨.

## 3. Dry-run (전체 레벨 대상, DB 쓰기 없음)

V2로 변환만 해보고 레벨별 변경 셀 수·비율만 출력.

```bash
npx tsx scripts/migrate-fieldmap-v2.ts --dry-run | tee dryrun-$(date +%Y%m%d).log
```

상위 20개 변경 많은 레벨 + 전체 요약(변경 셀 / 총 셀 / %)이 마지막에 나옴.
의심 레벨이 있으면 `--level N`으로 좁혀 재확인.

## 4. 실제 마이그레이션

Dry-run OK면:

```bash
npx tsx scripts/migrate-fieldmap-v2.ts --migrate
```

각 문서에 세팅되는 필드:
- `field_map`: V2 결과로 덮어씀
- `palette_mapping`: `{K인덱스: 28팔레트ID}` 맵
- `field_map_pipeline`: `"unfake_v1"`
- `field_map_migrated_at`: ISO timestamp
- (`field_map_v1_backup`은 그대로 보존 — 롤백용)

## 5. 롤백 (문제 발생 시)

`field_map_v1_backup`을 `field_map`으로 복원.

```bash
npx tsx scripts/migrate-fieldmap-v2.ts --rollback
```

## 권장 실행 순서

```
(0) MongoDB 전체 덤프  →  mongodump --uri "..."   # 최후 안전장치
(1) --backup           # field_map_v1_backup 생성
(2) --dry-run          # 변경량 확인
(3) --level N로 샘플 2~3개 compare-fieldmap-v1-v2.ts로 시각 확인
(4) --migrate          # 실제 전환
(5) Vercel 재배포      # 코드(4개 route)는 이미 V2 호출하게 되어 있음
(6) 갤러리 UI에서 레벨 몇 개 JSON 다운받아 유니티 이식 확인
```

문제 없으면 끝. 문제 있으면 `--rollback`.
