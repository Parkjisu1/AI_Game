# PixelForge 색상 제한(Color Constraint) 동작 가이드

> 대상: PixelForge(ProjectHub 내 `/pixelforge`) "레벨 → 이미지 생성" 기능
> 목적: 생성 옵션의 **색상 제한**이 *언제 / 어디서 / 어떻게* 적용되는지, 설계 CSV의 `colors`가
> 이미지·레벨 JSON에 무엇을 바꾸는지 코드 기준으로 정리.
> 기준 소스: `E:\AI\tools\pixelforge-web\src` (로컬), 배포처는 `pixelforge-web` 서비스.
> 민감정보(API 키, DB URI, 서버 자격증명)는 제외.

---

## 0. 30초 요약 (먼저 결론)

| 질문 | 결론 |
|---|---|
| **Q1. 색상 제한은 언제 적용되나?** | 이미지 **생성 단계가 아니라**, 생성 후 **스냅(snap-to-grid) 양자화 단계**에서 적용. PixelLab은 색상 제약 없이 그림. |
| **Q2. "색상제한 ON + 최대색 제한없음" == "색상제한 OFF"?** | **아니다 (다르다).** ON은 드롭다운 제한만 없을 뿐 **CSV `num_colors` 기반 색상 압축은 그대로 동작**. OFF는 그 압축까지 모두 끈다. |
| **Q3. 설계 CSV의 `colors`가 이미지/레벨 JSON에 영향?** | **이미지 픽셀 생성에는 영향 없음**(PixelLab에 색상 미전송). **레벨 JSON에는 영향 있음**(메타 `num_colors` 기록 + ON일 때 field_map 색상 압축). |
| **Q4. 색상 제한이 없어도 JSON에 색상 가공이 들어가나?** | **들어간다.** 제한과 무관하게 **28색 게임 팔레트 양자화는 항상 수행**됨. 제한은 그 위에 얹는 추가 압축일 뿐. |

핵심 한 줄: **"색상 가공"은 2층 구조다 — (1) 28색 팔레트 양자화(항상) + (2) num_colors 개수 압축(색상 제한 ON일 때만).**

---

## 1. 전체 파이프라인 개요

PixelForge는 "픽셀아트 이미지를 생성 → 게임 보드 그리드(field_map)로 변환 → Unity가 읽는 레벨 JSON 산출"을 담당한다.

```
[레벨 메타 CSV 입력]
   │  (Google Sheets → CSV 업로드)
   ▼
[levels/page.tsx]  레벨 테이블 + 생성 옵션 UI (색상 제한 / 최대 색 / 투명 배경)
   │  buildGenPayload() → POST /api/generate
   ▼
[/api/generate]   프롬프트 번역 → PixelLab generate-image-v2 비동기 시작
   │              (color_palette:false — 색상 제약 없이 픽셀아트 생성)
   │              job 컨텍스트(color_ids, target_color_count)를 pixelforge_jobs에 저장
   ▼
[/api/pro-poll]   5초마다 폴링 → 완료 시 raw→PNG 변환
   │              snapImageToGridAndPaletteV2()  ★ 여기서 색상 가공/제한 발생
   │              결과(image_base64, field_map, palette_mapping)를 pixelforge_levels 저장
   ▼
[buildLevelJson]  레벨 메타 + field_map(designer_note 내부 임베드) → Unity용 JSON
```

관련 파일:

| 단계 | 파일 |
|---|---|
| 생성 옵션 UI / 페이로드 빌드 | `src/app/levels/page.tsx` |
| 생성 진입점 | `src/app/api/generate/route.ts` |
| PixelLab API 클라이언트 | `src/lib/pixellab.ts` |
| 비동기 결과 폴링 + 스냅 호출 | `src/app/api/pro-poll/route.ts` |
| **색상 양자화/제한 핵심** | `src/lib/snapToGridV2.ts` |
| 28색 게임 팔레트 정의 | `src/lib/palette.ts` |
| 레벨 JSON 빌더 | `src/lib/levelJson.ts` |
| 색상 보조 유틸(limitColors 등) | `src/lib/genUtils.ts` |
| 수동 색상 보정 | `src/app/api/correction/route.ts` |

> 참고: 처음 `generate-image-v2`(고품질, async)를 시도하고, 실패 시 `create-image-pixflux`(sync)로 폴백한다(`generate/route.ts:106-185`). 두 경로 모두 **같은 `snapImageToGridAndPaletteV2`** 를 통과하므로 색상 처리 로직은 동일하다.

---

## 2. 핵심 개념: 색상 제한은 "두 개의 별개 메커니즘"이다

혼동의 근원은, UI상 "색상 제한" 영역이 **서로 다른 두 가지 제한**을 한 줄에 묶어 놓았다는 점이다.

### 메커니즘 A — 입력 팔레트 제한 (`maxColors` 드롭다운)
- UI: `최대 색: [제한없음 / 5색 / 8색 / 13색 / 전체 28색]` (`levels/page.tsx:716-731`)
- 동작: CSV의 `color_distribution`에서 파싱한 색상 ID 목록(`ids`)을 균등 샘플링으로 N개로 줄인다.
  - `if (useColorLimit && maxColors > 0 && ids.length > maxColors) ids = limitColors(ids, maxColors);` (`levels/page.tsx:88-89`)
  - `limitColors`는 앞에서 자르지 않고 분포를 유지하며 샘플링 (`genUtils.ts:47-56`)
- **중요한 함정**: 이렇게 만든 `color_distribution`(=`color_ids`)는 서버 스냅 V2에서 **실제로는 강제되지 않는다**.
  - `snapToGridV2.ts:159-160` 주석: *"K→28 mapping is always open (all 28 palette). allowedIds is NOT enforced here"*
  - 즉 `allowedIds`(=color_ids)는 V2 파이프라인에서 **무시**된다(설계상 의도 — "unfake가 정확한 색을 뽑게 두고, 틀리면 사람이 palette_mapping 수정").
  - 결과적으로 **maxColors 드롭다운은 현재 V2 경로에서 최종 색상에 거의 영향을 주지 못한다.** (메타 표기/구버전 호환용 잔재에 가깝다.)

### 메커니즘 B — 출력 색 개수 압축 (`num_colors`, CSV의 `colors`)
- 출처: CSV `colors`/`color_count`/`색상수` → `num_colors`로 매핑 (`levels/page.tsx:439-441`)
- 동작: 생성된 이미지를 28색으로 양자화한 뒤, **상위 빈도 N(=num_colors)색만 남기고** 나머지는 가장 가까운 top-N 색으로 재매핑.
  - `generate/route.ts:43-44`: `applyColorLimit = use_color_limit !== false; targetColorCount = applyColorLimit ? num_colors : 0`
  - `snapToGridV2.ts:285-322`: `targetFinalColors > 0`일 때 top-N 압축 수행
- **이것이 실제로 동작하는 "색상 제한"이다.** 색상 제한 체크박스의 진짜 효과는 메커니즘 B의 on/off.

> 정리: **"색상 제한" 체크박스 = 메커니즘 B(num_colors 압축) 스위치** + 메커니즘 A(maxColors) 활성화 게이트.
> 그런데 메커니즘 A는 V2에서 무력화되어 있으므로, **실질적으로 체크박스는 num_colors 압축의 on/off로 동작**한다.

---

## 3. 데이터 흐름 상세 (코드 인용)

### 3-1. 프론트엔드 페이로드 (`levels/page.tsx:63-108`)

```ts
// 색상 ID 결정 우선순위
let ids = colorOverride        // 1. 명시적 override
       ?? rowColors[lv]        // 2. 확장 행 수동 선택
       ?? parseColorDist(lv.color_distribution); // 3. CSV color_distribution

// 메커니즘 A (maxColors)
if (useColorLimit && maxColors > 0 && ids.length > maxColors)
    ids = limitColors(ids, maxColors);

// 색상 제한 OFF면 color_distribution 자체를 빈 문자열로 전송
const colorDist = useColorLimit ? ids.map(c => `c${c}:1`).join(",") : "";

return {
  prompt, width, height,
  color_distribution: colorDist,     // → 서버 colorIds
  level_data: lv,                    // ← num_colors 포함
  no_background: transparentBg,
  use_color_limit: useColorLimit,    // ← 메커니즘 B 스위치
};
```

포인트:
- `use_color_limit === false`이면 `color_distribution = ""` → 서버 `colorIds = []`.
- `level_data`(=행 전체)에는 항상 `num_colors`가 들어간다 (제한 OFF여도 전송됨).

### 3-2. 생성 진입점 (`generate/route.ts:41-95`)

```ts
const colorIds = parseColorDist(color_distribution || "");        // 빈 문자열이면 []
const applyColorLimit = use_color_limit !== false;                // 명시적 false만 OFF
const targetColorCount = applyColorLimit ? (num_colors || 0) : 0; // ★ 메커니즘 B 값
// ...
await db.collection("pixelforge_jobs").updateOne({ jobId }, { $set: {
  color_ids: colorIds,
  target_color_count: targetColorCount,   // 스냅 단계로 전달되는 핵심 값
  field_cols, field_rows, no_background,
}});
```

- **이미지 생성 호출(`generateImageV2Start`)에는 `colorIds`도 `num_colors`도 전달되지 않는다.** 색상은 전적으로 후처리(스냅)에서 결정.

### 3-3. PixelLab 호출 — 색상 미전송 증거 (`pixellab.ts:65-91`)

```ts
const payload = {
  description: prompt,          // 프롬프트(designer_note에서 추출)
  image_size: { width, height },
  no_background,
  style_options: {
    color_palette: false,      // ★ 스타일 이미지의 팔레트도 따라하지 않음
    outline: true, detail: true, shading: true,
  },
  // style_image (있으면) — 형태/쉐이딩만 참조, 색은 무시
};
```

- 색상 관련해 PixelLab에 가는 정보는 **없다**. `color_palette:false`는 "(스타일 레퍼런스가 있어도) 색은 따라하지 말라"는 뜻.
- 즉 **AI가 그리는 픽셀아트의 색은 CSV `colors`/`color_distribution`과 무관**하게 프롬프트만으로 정해진다.

### 3-4. 스냅 = 색상 가공/제한 실제 발생 지점 (`pro-poll/route.ts:82-94` → `snapToGridV2.ts`)

```ts
const snapped = await snapImageToGridAndPaletteV2(base64, {
  cols, rows,
  allowedIds: jobCtx.color_ids?.length > 0 ? jobCtx.color_ids : undefined, // V2에서 미강제
  transparentBg: jobCtx.no_background === true,
  targetColorCount: jobCtx.target_color_count > 0 ? jobCtx.target_color_count : undefined,
});
```

`snapImageToGridAndPaletteV2` 내부(요약, `snapToGridV2.ts`):

1. **항상 수행 — 28색 양자화**
   - median-cut으로 이미지를 K개 클러스터로 압축 (K = `max(8, min(16, num_colors*2 or 8))`, `:155-158`)
   - 각 셀을 K-index로 다수결 투표 (`:216-253`)
   - K 클러스터 → 28색 게임 팔레트 중 가장 가까운 색으로 매핑 (RGB 유클리드, `:260-278`)
   - 결과: 모든 셀이 1~28 팔레트 색으로 채워진 `matrix` 생성
2. **조건부 수행 — num_colors 압축 (메커니즘 B)**
   - `targetFinalColors > 0`일 때만: 셀 빈도 top-N색만 남기고 나머지는 최근접 top-N으로 재매핑 (`:285-322`)
   - `targetColorCount = 0`(제한 OFF / 제한없음)이면 이 블록 **건너뜀** → 28색 양자화 결과 그대로 유지

스냅 결과(`field_map`, `palette_mapping`, `generated_colors`)가 `pixelforge_levels`에 저장됨 (`pro-poll/route.ts:99-116`).

### 3-5. 레벨 JSON 산출 (`levelJson.ts:49-102`)

```ts
buildLevelJson(level) → {
  num_colors,                 // CSV 값 그대로 기록 (메타)
  color_distribution,         // CSV 값 그대로 기록 (메타)
  designer_note: note + "\n[FieldMap]\n" + field_map,  // ★ 양자화된 색상 매트릭스 임베드
  // ... 그 외 그리드/기믹 메타
}
```

- 실제 보드 색은 `designer_note` 안 `[FieldMap]` 블록(=스냅 결과 matrix)으로 들어간다.
- `num_colors`/`color_distribution`은 **참고 메타**로 별도 기록(이미지 픽셀과 별개).

---

## 4. 네 가지 질문 — 코드 기준 정밀 답변

### Q1. 픽셀포지에서 생성옵션을 선택할 때 **색상 제한이 언제 적용되는가?**

- **적용 시점**: 이미지가 **생성된 후의 스냅(양자화) 단계**. 정확히는 `snapImageToGridAndPaletteV2`의 top-N 압축(`snapToGridV2.ts:285-322`).
- **생성 단계에는 적용 안 됨**: PixelLab `generate-image-v2`/`pixflux` 호출에 색상 정보가 가지 않음(`pixellab.ts`, `color_palette:false`).
- 전달 경로: 체크박스 `useColorLimit` → 페이로드 `use_color_limit` → 서버 `applyColorLimit` → `targetColorCount = num_colors` → job 컨텍스트 `target_color_count` → 스냅 `targetColorCount` → top-N 압축.
- 즉 **"색상 제한 = 생성 결과를 num_colors개 색으로 줄이는 후처리"**. 생성 자체의 색을 강제하는 기능이 아니다.

### Q2. "색상 제한 **true** + 최대색 **제한없음**" 과 "색상 제한 **false**" 는 같은 입력인가?

**아니다. 서로 다른 입력이며 결과 JSON도 달라질 수 있다.**

| 구분 | 색상제한 ON + 최대색 제한없음(0) | 색상제한 OFF |
|---|---|---|
| `color_distribution` 전송 | `ids.map(...)` (CSV 값 그대로, 비어있지 않을 수 있음) | `""` (빈 값) |
| `use_color_limit` | `true` | `false` |
| 서버 `targetColorCount` | **`num_colors` (CSV 값!)** | **`0`** |
| 스냅 top-N 압축 | **수행됨 (num_colors개로 압축)** | **건너뜀** |
| 28색 양자화 | 수행 | 수행 |

- "최대 색: 제한없음"은 **메커니즘 A(maxColors 드롭다운 추가 샘플링)만** 끈다.
- 메커니즘 B(num_colors 압축)는 체크박스가 ON인 한 **계속 동작**한다 (`targetColorCount = num_colors`).
- 따라서 CSV에 `num_colors`(=colors)가 채워져 있으면, "ON+제한없음"은 그 개수로 색을 압축하지만 "OFF"는 압축하지 않는다 → **결과 field_map의 색 개수가 달라진다.**
- 두 입력이 *우연히 동일한 결과*가 되는 경우: CSV `num_colors`가 0/빈값이라 양쪽 다 `targetColorCount=0`이 될 때뿐. 그 외에는 다르다.

### Q3. 입력한 설계 CSV의 `colors`가 **이미지 생성 / 레벨 JSON 파일**에 영향을 미치는가?

- CSV `colors` → `num_colors`로 매핑됨 (`levels/page.tsx:439`).
- **이미지 생성(PixelLab 픽셀): 영향 없음.** `num_colors`도 `color_distribution`도 PixelLab API에 전송되지 않음. AI는 프롬프트(designer_note)만으로 색을 정함.
- **레벨 JSON: 영향 있음 (두 갈래).**
  1. **메타 기록**: JSON `num_colors`, `color_distribution` 필드에 CSV 값이 그대로 적힌다 (`levelJson.ts:68-69`).
  2. **field_map 색상 압축**: 색상 제한 ON일 때, `num_colors` → 스냅 top-N 압축 → `[FieldMap]`(실제 보드 색 매트릭스)에 반영 → JSON에 임베드된다. (제한 OFF면 압축 미반영)
- 요약: **`colors`는 "AI가 그리는 그림 색"은 못 바꾸지만, "JSON 메타 + (제한 ON시) 양자화 후 보드 색 개수"는 바꾼다.**

### Q4. 색상 제한이 **없을 때에도** 기본적으로 JSON에 색상 가공이 들어가는가?

- **그렇다. 들어간다.**
- 색상 제한 여부와 무관하게 스냅은 **항상** 실행되고, 그 1단계인 **28색 게임 팔레트 양자화는 무조건 수행**된다(`snapToGridV2.ts:163-283`).
  - PixelLab 원본이 수백~수천색이어도, field_map은 항상 1~28 팔레트 색으로 변환된다.
- 색상 제한이 없으면(=`targetColorCount=0`) 단지 **2단계 top-N 압축만 건너뛸 뿐**(`:286` 조건), 28색 양자화 자체는 그대로 일어난다.
- 즉 "색상 가공 없음"이라는 상태는 존재하지 않는다. 최소한 28색 팔레트 매핑은 항상 적용된다.

---

## 5. 색상 처리 2층 구조 (시각화)

```
PixelLab 원본 이미지 (자유 색상, 수백~수천색)
        │
        ▼  ── snapToGridV2 ──────────────────────────────
  [1층] median-cut(K) → 셀 다수결 → 28색 게임 팔레트 매핑     ← 항상 적용 (제한 무관)
        │
        ▼
  [2층] top-N(num_colors) 압축 + 최근접 재매핑               ← 색상 제한 ON & num_colors>0 일 때만
        │
        ▼
   field_map (보드 색 매트릭스) → 레벨 JSON [FieldMap]
```

- 색상 제한 OFF: [1층]만 → 28색 범위 내 자유로운 색 개수
- 색상 제한 ON + num_colors=N: [1층]+[2층] → 최대 N색
- maxColors 드롭다운(메커니즘 A): 입력 ids 샘플링이지만 **V2 스냅에서 미강제 → 최종 색에 거의 무영향**

---

## 6. 28색 게임 팔레트 (참고)

양자화 목표 팔레트는 `src/lib/palette.ts`의 `GAME_PALETTE`(고정 28색). 모든 field_map 색은 이 1~28 ID로 표현된다.

| ID | 이름 | ID | 이름 | ID | 이름 | ID | 이름 |
|---|---|---|---|---|---|---|---|
| 1 | 핑크 | 8 | 검정 | 15 | 연파랑 | 22 | 코랄 |
| 2 | 시안 | 9 | 하늘 | 16 | 갈색 | 23 | 연회색 |
| 3 | 보라 | 10 | 초록 | 17 | 살구 | 24 | 회색 |
| 4 | 노랑 | 11 | 빨강 | 18 | 연분홍 | 25 | 마젠타 |
| 5 | 라임 | 12 | 파랑 | 19 | 와인 | 26 | 연주황 |
| 6 | 주황 | 13 | 청록 | 20 | 연초록 | 27 | 진빨강 |
| 7 | 흰 | 14 | 연보라 | 21 | 진보라 | 28 | 민트 |

- `color_distribution` 표기 형식: `c<ID>:<weight>` 쉼표 구분 (예: `c1:1,c4:1,c10:1`). 파서: `parseColorDist` (`palette.ts:30-33`).
- `0`은 빈 셀(투명/배경)을 의미.

---

## 7. 운영자가 알아둘 함정 & 권장 사용법

1. **"색상 제한 ON + 제한없음"으로 무압축을 기대하면 안 된다.** num_colors가 채워져 있으면 그 개수로 압축된다. 정말 압축을 끄려면 **체크박스 OFF** 또는 **num_colors를 비우기**.
2. **maxColors 드롭다운(5/8/13/28색)은 현재 V2 경로에서 최종 색에 거의 영향이 없다.** 실제 색 개수 통제는 CSV `num_colors`로 한다.
3. **CSV `colors`로 "이 색만 써라"를 지정할 수 없다.** allowedIds가 V2에서 미강제이기 때문. 특정 팔레트를 강제하려면 생성 후 **수동 보정**(`/api/correction`, `paletteOverride`)이나 `palette_mapping` 편집을 사용.
4. **field_map은 항상 28색 양자화를 거친다.** 원본 이미지 색감과 보드 색이 다를 수 있는 건 정상(게임 팔레트로 스냅되기 때문).
5. **레벨 JSON의 `num_colors`/`color_distribution`은 "선언 메타"**다. 실제 보드 색은 `[FieldMap]` 블록을 봐야 한다. 둘이 다를 수 있음(특히 제한 OFF일 때).
6. **pixflux 폴백 경로**(`generate/route.ts:106-185`)도 동일한 스냅·동일한 색상 규칙을 탄다. v2/폴백 여부와 색상 처리 결과는 무관.

---

## 8. 관련 코드 빠른 참조표

| 동작 | 위치 |
|---|---|
| 색상 제한 체크박스 / 최대색 드롭다운 | `levels/page.tsx:707-731` |
| 페이로드 색상 결정 로직 | `levels/page.tsx:72-107` |
| maxColors 샘플링(`limitColors`) | `genUtils.ts:47-56` |
| CSV `colors`→`num_colors` 매핑 | `levels/page.tsx:439-441` |
| `applyColorLimit` / `targetColorCount` 산출 | `generate/route.ts:43-44` |
| PixelLab v2 payload(`color_palette:false`) | `pixellab.ts:65-91` |
| job 컨텍스트 저장(`target_color_count`) | `generate/route.ts:82-95` |
| 스냅 호출(폴링) | `pro-poll/route.ts:82-94` |
| 28색 양자화(항상) | `snapToGridV2.ts:163-283` |
| top-N 압축(조건부) | `snapToGridV2.ts:285-322` |
| 레벨 JSON 빌드 / FieldMap 임베드 | `levelJson.ts:49-102` |
| 28색 팔레트 정의 | `palette.ts:1-33` |
| 수동 색상 보정 | `app/api/correction/route.ts` |

---

*작성 기준: 위 파일들의 현재 소스. 코드 변경 시 인용 라인이 달라질 수 있으니 §8 참조표로 재확인 권장.*

---
---

# Part B. Level Batches — "Art 생성 (cowork patterns)" 동작 가이드

> 대상: ProjectHub `/agents/batches` 페이지의 **🎨 Art 생성 (cowork patterns)** 기능.
> ⚠️ 주의: 이 기능은 **PixelForge(Part A)와 완전히 다른 서브시스템**이다.
> - Part A(PixelForge): PixelLab AI로 픽셀아트 **이미지**를 생성 → 스냅.
> - Part B(Level Batches): AI/이미지 없이 **알고리즘으로 기하 패턴 격자(field_map)를 직접 합성**.
> 코드 위치: UI `tools/projecthub-web/src/app/agents/batches/page.tsx`, API `.../api/agents/batches/route.ts`,
> 실제 생성기 `hermes/watcher/batch_generate_levels.py` + `hermes/watcher/pattern_lib/`(Mother 서버에서 실행).
>
> ✅ **검증 기준(중요)**: 본 Part B는 **Mother 실서버(`aimed@100.77.190.68`)의 라이브 파일을 SSH로 직접 확인(2026-06-04)**해 작성했다.
> 로컬 미러(`E:\AI\hermes\watcher\`)는 2026-04-29판으로 **구버전**이라 bl_metaphor 매핑이 빠져 있었음 — 라이브는 2026-05-22판(`batch_generate_levels.py`, 34,900 bytes)으로 bl_metaphor를 **1순위**로 사용한다.

---

## B0. 30초 요약 (먼저 결론)

| 질문 | 결론 |
|---|---|
| **레벨별/시도별로 유의미한 차이가 안 난다** | **정상 동작이자 구조적 한계.** ① CSV 첨부 시 mood/style 무시 ② 패턴은 `bl_metaphor`(한글) → `designer_note`(영어) 순으로만 결정 — **둘 다 매핑 표에 안 걸리면 전부 fallback `kaleidoscope` 동일** ③ seed가 `level_number`로 고정(`level_no*13+7`)이라 **재실행해도 결과 동일(완전 결정성)**. |
| **Level Batches가 CSV에서 쓰는 데이터** | `level_number, field_columns(width), field_rows(height), num_colors, color_distribution, designer_note, bl_metaphor, purpose_type(메타)`. **패턴을 바꾸는 건 bl_metaphor / designer_note 둘뿐.** |
| **bl_metaphor를 쓰는가?** | **✅ 쓴다 (라이브 1순위).** 2026-05-22 패치로 `_pattern_from_bl_metaphor(bl_metaphor)`가 `designer_note`보다 **먼저** 평가됨(`batch_generate_levels.py:487-488` 라이브). 한글 메타포 48종을 cowork 패턴에 substring 매핑. *(주의: 로컬 구버전 미러엔 이 기능이 없어 처음엔 "안 쓴다"로 보였음 — 라이브 확인 후 정정.)* |
| **mood/style을 생성 전에 입력 가능?** | UI에 드롭다운은 있다(mood: random/warm/cool/pastel/vivid/all · style: ""/kaleidoscope/tile/organic/motif/all). **그러나 CSV를 첨부하면 mood·style·size 전부 무시된다**(`route.ts:158`). CSV 없이 "랜덤 생성" 모드일 때만 적용. |
| **cowork가 실제 대응하는 키워드** | bl_metaphor 한글 48종(`KO_METAPHOR_TO_PATTERN`) + designer_note 영어 32키워드→17패턴(`MOTIF_KEYWORDS`) → 엔진 패턴 19종. **만화경·격자(픽셀 그리드)·스트라이프(줄무늬)·픽셀·빛·그라데이션·삼각은 라이브에서 대응됨** — 단 CSV `bl_metaphor` 값이 표의 정확한 한글 구절을 **포함**해야 함. 모자이크는 미대응. §B5 표 참조. |

핵심 한 줄: **"Art 생성(cowork)"은 AI가 아니라 결정성 알고리즘이다. CSV에서 패턴을 바꾸는 입력은 `bl_metaphor`(한글, 1순위)와 `designer_note`(영어, 2순위)뿐이고, 이 값이 매핑 표의 키를 포함하지 않으면 전부 kaleidoscope로 떨어져 레벨이 똑같아 보인다. seed도 레벨번호 고정이라 재실행 다양성은 0이다.**

---

## B1. 파이프라인 개요

```
[batches/page.tsx]  CSV 업로드 → parseCsvText() → ParsedCsvRow[]
   │  선택된 행만 필터 → POST /api/agents/batches
   │  payload(batch 모드) = { csv_rows: filteredCsvRows, csv_source, allow_duplicate }   (page.tsx:1055)
   ▼
[/api/agents/batches]  pixelforge_batch_requests 에 doc 저장 (csv_rows 포함)
   │  ★ CSV 있으면 mood/style/size 무시, count = csv_rows.length        (route.ts:158, 196-213)
   │  watcher의 batch_generate_levels.py 를 spawn (--request <id>)       (route.ts:229-238)
   ▼
[batch_generate_levels.py]  _pull_request → csv_rows 추출 → run_csv_batch()
   │  행마다 generate_one_from_csv():
   │    · width/height = CSV field_columns/field_rows
   │    · palette = color_distribution → BF 인덱스 변환 (없으면 앞에서부터 채움)
   │    · pattern = row.pattern(항상 없음)
   │              ?? _pattern_from_bl_metaphor(bl_metaphor)   ← 1순위(한글, 라이브)  ★
   │              ?? _pattern_from_motif(designer_note)        ← 2순위(영어)
   │              ?? "kaleidoscope" (fallback)
   │    · seed = level_number*13 + 7   ← 결정성
   │  process_level(entry, extended_seeds=10) → 9~10 변형 생성 → score → best 채택
   ▼
[pixelforge_grid_levels]  격자 + PNG 저장 (갤러리 /levels 에 표시)
```

관련 파일:

| 단계 | 파일 |
|---|---|
| CSV 파싱 / 헤더 alias / 폼 | `projecthub-web/src/app/agents/batches/page.tsx` |
| batch 요청 생성 + watcher spawn | `projecthub-web/src/app/api/agents/batches/route.ts` |
| **배치 생성기(핵심)** | `hermes/watcher/batch_generate_levels.py` |
| 패턴 생성 함수 레지스트리 | `hermes/watcher/pattern_lib/pixel_pattern_api.py` (`PATTERN_FUNCS`) |
| 변형/스코어/빈칸 차단 | `hermes/watcher/pattern_lib/variant_pipeline.py`, `blank_engine.py` |

---

## B2. 왜 "레벨별/시도별로 유의미한 차이가 안 나는가" (가장 중요)

세 가지 원인이 겹친다.

### 원인 ① CSV 첨부 시 mood/style이 통째로 무시됨
- `route.ts:158` 주석: *"CSV 모드: csv_rows[]가 있으면 mood/style/size 무시"*. 실제로 `csvRows.length > 0`이면 doc에 mood/style/size를 넣지 않고 `csv_rows`만 저장(`route.ts:196-213`).
- 라이브 `batch_generate_levels.py:810-812`: `if csv_rows:` → 주석 *"CSV 모드: row별로 처리. mood/style/size 무시."* → `run_csv_batch(...)` 한 갈래로만 가고 mood/style 분기(`elif args.style:`)를 안 탄다.
- 결과: UI에서 mood=warm, style=tile 등을 골라도 **CSV가 붙어 있으면 아무 효과 없음.** 색감은 CSV `color_distribution`에서만 온다.

### 원인 ② 패턴이 bl_metaphor/designer_note 매핑에만 의존 — 둘 다 안 걸리면 전부 동일 fallback
- 라이브 패턴 결정 순서(`batch_generate_levels.py:485-488`, 2026-05-22판):
  ```python
  pattern = str(row.get("pattern") or "").strip()         # 항상 비어있음
  if not pattern:
      bl_meta = str(row.get("bl_metaphor") or "")
      pattern = _pattern_from_bl_metaphor(bl_meta) \       # 1순위: 한글 메타포
                or _pattern_from_motif(str(row.get("designer_note") or ""))  # 2순위: 영어 노트(없으면 kaleidoscope)
  ```
- **함정 1 — `pattern` 컬럼은 사실상 항상 비어 있다.** 프론트 `HEADER_ALIASES`에 `pattern` 별칭이 없다(`page.tsx:43-71`). CSV에 `pattern` 열이 있어도 파싱 안 됨 → 항상 bl_metaphor/designer_note 추론으로 떨어진다.
- **함정 2 — 매칭은 "표의 키를 값이 포함(substring)"해야 성립.** `_pattern_from_bl_metaphor`는 `if kw in text`로 검사(`:229`). 즉 **CSV `bl_metaphor` 값이 표의 한글 구절(예: "픽셀 그리드", "줄무늬", "삼각")을 substring으로 포함**해야 매핑된다. 표에 없는 표현이거나, 표 키보다 짧은 값(예: 값이 그냥 "픽셀"이면 키 "픽셀 그리드"를 포함하지 못함)은 **매칭 실패 → None → designer_note(영어)로 폴백 → 그것도 실패면 kaleidoscope**.
- **함정 3 — designer_note 폴백은 영어만.** `_pattern_from_motif`(`:235`)는 `[Motif]`/`[Shape]` 텍스트(없으면 노트 전체)를 소문자화 후 **영어 substring LUT**(`MOTIF_KEYWORDS` `:128`, 매칭 루프 `:251`)와 비교. 한글 노트는 매칭 안 됨.
- 결과: **bl_metaphor가 비어있거나 표에 없는 값이고 designer_note에도 영어 모티프가 없으면, 모든 레벨이 동일한 kaleidoscope로 생성**되어 W/H/팔레트만 빼면 구조가 사실상 같다. → "레벨별 차이 없음"의 가장 흔한 실제 원인.
  - 추가로, 여러 레벨의 bl_metaphor가 **같은 패턴으로 매핑**되는 경우(예: "나선"·"물방울"·"성운"이 모두 `wave`)도 구조가 비슷해진다.

### 원인 ③ seed가 level_number로 고정 → 시도(재실행)별 차이 0
- `seed = level_no * 13 + 7` (`batch_generate_levels.py:416`). 같은 레벨번호면 **언제 몇 번을 돌려도 같은 seed → 같은 결과.**
- 파일 헤더에도 명시: *"LLM 안 씀. 결정성 — 같은 mood/i면 같은 결과."*(`:15`).
- `process_level(..., extended_seeds=10)`이 내부적으로 9~10개 변형을 만들어 score로 best를 뽑지만, 시작 seed가 고정이라 **best 선택까지 결정적**이다.
- 결과: "다시 생성"해도 동일 산출물. **시도별 다양성을 기대하면 안 된다**(이 엔진은 의도적으로 재현가능/결정성 설계).

> 종합: cowork 배치에서 레벨 간 차이를 만드는 입력은 **딱 4개 — width, height, palette(color_distribution/num_colors), designer_note의 영어 모티프 태그**. 이 4개가 행마다 안 바뀌면 결과도 안 바뀐다. mood/style/bl_metaphor/purpose/gimmick 컬럼은 cowork 결과에 영향 없음.

### 차이를 만들려면 (실무 처방)
1. **`designer_note`에 영어 모티프 태그를 행마다 다르게** 넣는다. 예: `[Motif] hex`, `[Shape] maze`, `[Motif] concentric`, `[Shape] stripe` … (§B5 LUT의 영어 키워드 사용).
2. CSV `color_distribution`/`num_colors`를 행마다 달리해 팔레트 변주.
3. `field_columns`/`field_rows`를 변주(보드 크기).
4. mood/style로 색감을 바꾸고 싶으면 **CSV를 떼고** "랜덤 생성" 모드로 돌린다(그때만 mood/style 적용).

---

## B3. Level Batches가 CSV에서 읽는 데이터 (정확 목록)

### 프론트가 인식하는 CSV 헤더 별칭 (`page.tsx:43-71`)
파서는 첫 5줄 중 가장 많이 매칭되는 줄을 헤더로 자동 선택하고, 다음 별칭들을 캐논 필드로 매핑한다:

| 캐논 필드 | 허용 별칭(일부) | cowork 생성에 **실제 사용?** |
|---|---|---|
| `level_number` | level, lv, stage, 레벨, 스테이지 | ✅ seed/이름/pkg·pos |
| `field_columns` | cols, x, 열 | ✅ width |
| `field_rows` | rows, y, 행 | ✅ height |
| `num_colors` | colors, color count, 색상수 | ✅ 팔레트 개수 |
| `color_distribution` | color_dist, 색상분포 | ✅ 팔레트 색 |
| `designer_note` | note, 노트 | ✅ **패턴 결정 2순위(영어 모티프)** |
| `bl_metaphor` | metaphor, 메타포 | ✅ **패턴 결정 1순위(한글 메타포, 라이브)** |
| `purpose_type` | purpose, 목적 | ⚠️ 메타로만 저장, 생성엔 미사용 |
| `total_cells` | cells, 총셀수 | ⚠️ 메타/field-complete용 |
| `queue_columns`, `rail_capacity` | … | ❌ cowork 미사용(field-complete용) |
| `pkg`, `pos` | … | ⚠️ 저장 메타 |
| `gimmick_*` (13종) | hidden, chain, pinata … | ❌ cowork 미사용(field-complete 단계용) |

### 백엔드가 실제 소비하는 키 (`generate_one_from_csv`, 라이브)
```
width(=field_columns), height(=field_rows), n_colors(=num_colors),
color_dist(=color_distribution), bl_metaphor(패턴 1순위), designer_note(패턴 2순위),
level_number(seed/이름), purpose(메타)
```
→ **`gimmick_*`, `queue_columns`, `rail_capacity`, `total_cells`는 cowork 생성 로직에서 호출되지 않는다**(field-complete 단계 전용).

### bl_metaphor 사용 — 라이브 확인 결과 (정정)
- **처음엔 "안 쓴다"로 판단했으나, 그건 로컬 미러가 구버전이었기 때문**이다. Mother 실서버에서 직접 확인한 결과:
  - `batch_generate_levels.py:169` `KO_METAPHOR_TO_PATTERN`(한글 48종 매핑) 존재
  - `:222` `_pattern_from_bl_metaphor()` 함수 존재
  - `:487-488` `pattern = _pattern_from_bl_metaphor(bl_meta) or _pattern_from_motif(designer_note)` — **bl_metaphor가 1순위**
  - 파일 mtime 2026-05-22, 34,900 bytes (로컬 미러는 2026-04-29판)
- 즉 **CSV `bl_metaphor` 열이 cowork 패턴을 결정하는 가장 강력한 입력**이다(한글 지원). designer_note는 bl_metaphor가 매칭 실패할 때만 보조로 평가된다.
- (별개로 bl_metaphor는 field-complete / 큐 기믹 화면 `page.tsx:3463,3492`에서도 표시·참고용으로 쓰인다.)

---

## B4. mood / style 생성 전 입력 가능 여부

### UI에 존재하는 선택지 (`page.tsx:38-40`)
- **mood**: `random, warm, cool, pastel, vivid, all` — *색감(팔레트 군)*
- **style**: `(없음), kaleidoscope, tile, organic, motif, all` — *구조 패턴 군*
- **size**: `medium, small, large, tall, wide, mixed, custom` — *보드 크기*

사용자가 질문에 적은 `Cool/Warm/Pastel/Vivid`는 **mood**, `Tile/Kaleidoscope/Organic/Motif`는 **style**에 해당한다. (둘은 다른 축이다.)

### 적용 조건 — 핵심
| 모드 | mood | style | size | 팔레트 출처 | 패턴 출처 |
|---|---|---|---|---|---|
| **CSV 첨부 (지금 쓰는 방식)** | ❌무시 | ❌무시 | ❌무시 | CSV `color_distribution` | CSV `designer_note` 모티프 |
| **CSV 없이 랜덤 생성** | ✅적용 | ✅적용 | ✅적용 | mood 팔레트군에서 샘플 | style 패턴군에서 랜덤 |

- mood 팔레트군 정의: `batch_generate_levels.py:62-67` (warm/cool/pastel/vivid 각각 BF 24색 중 일부 묶음).
- style 패턴군 정의: `:82-95` (kaleidoscope→{concentric_sq,x_motif,plus_motif}, tile→{hex_tile,brick,checkerboard,truchet,argyle,stripe}, organic→{maze,wave}, motif→{t_motif,rect_grid}).

### 결론
- **"CSV를 첨부한 채 mood/style을 바꿔도 결과가 안 변한다"가 정상**이다(원인 ①과 동일).
- mood/style을 실제로 먹이려면 **CSV를 떼고 랜덤 생성** 모드로 실행해야 한다. 단, 이 경우 레벨번호·designer_note 매핑이 사라지고 임의 생성물이 된다.
- 사용자가 적은 8개 중 **Cool/Warm/Pastel/Vivid/Tile/Kaleidoscope/Organic/Motif는 모두 실재하는 옵션**이지만 위 조건부로만 동작. (그 외 "Pixel/Light/Gradient" 같은 항목은 mood/style 선택지에 없음.)

---

## B5. cowork가 실제 대응하는 키워드 / 패턴 어휘

### 엔진이 지원하는 전체 패턴 19종 (`pixel_pattern_api.py:2485` `PATTERN_FUNCS`)
```
kaleidoscope, hex_tile, maze, brick, i_tetromino, rect_grid, diamond_check,
stripe, xor_fractal, sierpinski_carpet, truchet, chevron, argyle, wave,
concentric_sq, checkerboard, x_motif, t_motif, plus_motif
```

- 이 중 **cowork 랜덤 풀(13종)** = `hex_tile, maze, brick, rect_grid, stripe, truchet, argyle, wave, concentric_sq, checkerboard, x_motif, t_motif, plus_motif` (`batch_generate_levels.py:73-79`).
- **랜덤 풀 제외 4종** = `chevron, kaleidoscope, diamond_check, i_tetromino` (2026-04-29 제외: 빈칸 cluster≥13 "쥐 파먹은" 모양 → `variant_pipeline` 차단 로직이 REJECT, `:70-72`). **단 CSV designer_note 키워드로는 명시 요청 가능**(다만 REJECT/저품질 위험).
- **노이즈 2종** = `xor_fractal, sierpinski_carpet` — 배치에서 제외(`:78`).

### ⭐ 1순위 — bl_metaphor 한글 메타포 → 패턴 매핑 (라이브 `KO_METAPHOR_TO_PATTERN`, 48종)
CSV `bl_metaphor` 값이 아래 **한글 키 구절을 substring으로 포함**하면 해당 패턴으로 결정(첫 매칭 우선). 매칭 실패 시 None → designer_note(영어, 2순위)로 폴백.

| bl_metaphor 한글 키 | 패턴 | | bl_metaphor 한글 키 | 패턴 |
|---|---|---|---|---|
| 나선 / 물방울 / 우주 성운 / 성운 / 추상 그라데 / 구름 그라데 | wave | | 동심 사각 / 그라데이션 사각 | concentric_sq |
| 헤링본 | chevron | | 추상 라인 / 색조 분할 / 색상 띠 / 줄무늬 | stripe |
| 도형 조합 / 불꽃 / X | x_motif | | 체크 패턴 / 외곽 체크 | checkerboard |
| 방사 패턴 / 빛 산란 / 빛의 분산 / 빛 입자 / 광선 다발 / 광선 패턴 / 컬러 휠 / 꽃 만다라 / 눈송이 만다라 / 만다라 | kaleidoscope | | 도트 패턴 / 픽셀 그리드 / 컬러 블록 / 컬러 픽셀 | rect_grid |
| 다이아몬드 | diamond_check | | 추상 형상 / 프랙탈 | xor_fractal |
| 미궁 / 미로 | maze | | 6각형 / 육각 | hex_tile |
| 삼각 패턴 | i_tetromino | | 삼각 | truchet |
| 브릭 / 벽돌 | brick | | 아가일 | argyle |
| 시에르핀 | sierpinski_carpet | | 플러스 / 십자 | plus_motif |
| T | t_motif | | | |

> 매칭은 `if 키 in 값`(substring), **리스트 위에서부터 첫 매칭**. 즉 한 값이 여러 키를 포함하면 표 상단 키가 우선한다(예: `"그라데이션 사각"`이 `"추상 그라데"`보다 위라 둘 다 포함하는 값은 concentric_sq로 감). 또 값이 그냥 `"픽셀"`이면 키 `"픽셀 그리드"`를 포함하지 못해 **매칭 실패** → designer_note로 폴백. **짧은 단일 단어보다 표의 구절을 그대로 쓰는 게 안전.**

### 2순위 — designer_note 모티프 키워드 → 패턴 매핑 LUT (`MOTIF_KEYWORDS`, 영어)
bl_metaphor 매칭 실패 시에만 평가. 첫 매칭 우선, 실패 시 **`kaleidoscope` fallback**. **영어 substring만 인식**(한글 미인식).

| 입력 영어 키워드 | 매핑 패턴 | 랜덤풀 포함 |
|---|---|---|
| `kaleidoscope`, `mandala` | kaleidoscope | ✖(제외, 키워드로만) |
| `ring`, `circle`, `concentric` | concentric_sq | ✔ |
| `dart`, `x-shape`, `x_motif` | x_motif | ✔ |
| `plus` | plus_motif | ✔ |
| `t-shape`, `t_motif` | t_motif | ✔ |
| `hex` | hex_tile | ✔ |
| `brick`, `wall` | brick | ✔ |
| `maze`, `labyrinth` | maze | ✔ |
| `wave`, `ripple` | wave | ✔ |
| `diamond`, `rhomb` | diamond_check | ✖(제외, 키워드로만) |
| `chevron`, `zigzag` | chevron | ✖(제외, 키워드로만) |
| `argyle` | argyle | ✔ |
| `truchet` | truchet | ✔ |
| `stripe`, `line` | stripe | ✔ |
| `checker` | checkerboard | ✔ |
| `grid`, `rectang` | rect_grid | ✔ |
| `tetro`, `L-shape` | i_tetromino | ✖(제외, 키워드로만) |
| `tile` | hex_tile (일반 fallback) | ✔ |

### 사용자가 물은 키워드들의 실제 대응 여부 (라이브 기준)
**핵심: `bl_metaphor` 열에 표의 한글 구절을 넣으면 대부분 대응된다.** 아래 "권장 입력값"을 CSV `bl_metaphor`에 그대로 쓰면 된다.

| 사용자 키워드 | 라이브 대응 | 권장 CSV `bl_metaphor` 입력값 | 매핑 패턴 | 비고 |
|---|---|---|---|---|
| **만화경** | ✅ | `만다라` / `방사 패턴` / `컬러 휠` | kaleidoscope | 랜덤풀 제외 패턴이라 빈칸 cluster 차단으로 REJECT 가능성 있음 |
| **격자** | ✅ | `픽셀 그리드` / `도트 패턴` / `컬러 블록` | rect_grid | (그냥 "격자"는 표에 없음 — 위 구절로) |
| **스트라이프** | ✅ | `줄무늬` / `색상 띠` / `색조 분할` / `추상 라인` | stripe | |
| **삼각** | ✅ | `삼각` → truchet, `삼각 패턴` → i_tetromino | truchet / i_tetromino | "삼각"만 쓰면 truchet, "삼각 패턴"이면 i_tetromino(제외 패턴) |
| **픽셀** | ✅ | `픽셀 그리드` / `컬러 픽셀` | rect_grid | "픽셀" 단독은 매칭 실패 — 반드시 구절로 |
| **빛** | ✅ | `빛 산란` / `빛의 분산` / `빛 입자` / `광선 패턴` | kaleidoscope | 구조적으론 방사형. 진짜 발광/글로우는 cowork로 불가(이미지 생성 영역) |
| **그라데이션** | ✅(근사) | `그라데이션 사각`→concentric_sq, `추상 그라데`/`구름 그라데`→wave | concentric_sq / wave | cowork는 **이산 타일**이라 *진짜 연속 그라데이션은 못 만든다*. 동심/물결로 근사만. |
| **모자이크** | ❌ | (표·LUT에 없음) | — fallback kaleidoscope | 근사 대체: `체크 패턴`(checkerboard) / `육각`(hex_tile) / `도트 패턴`(rect_grid) |

> 한 줄 요약(라이브): **bl_metaphor 한글 48종 + designer_note 영어 32키워드(17패턴)가 모두 동작**한다. 사용자가 든 8개 중 **모자이크만 직접 대응이 없고**, 나머지(만화경·격자·스트라이프·삼각·픽셀·빛·그라데이션)는 위 "권장 입력값"으로 대응된다. 단 ① **표의 구절을 정확히 포함**해야 하고 ② **그라데이션/빛은 구조 근사**일 뿐 진짜 연속 명암은 cowork로 불가(그건 Part A PixelForge 이미지 생성 영역)이며 ③ kaleidoscope/diamond_check/i_tetromino로 매핑되는 값은 랜덤풀 제외 패턴이라 cluster 차단으로 결과가 누락될 수 있다.

---

## B5.5 실전 CSV 예시 (나쁜 예 vs 좋은 예)

### ❌ 나쁜 예 — 모든 레벨이 똑같이 나오는 CSV
```csv
level_number,field_columns,field_rows,num_colors,color_distribution,bl_metaphor,designer_note
1,25,25,4,c1 c2 c3 c4,,
2,25,25,4,c1 c2 c3 c4,,
3,25,25,4,c1 c2 c3 c4,,
```
→ `bl_metaphor` 비어있음 + `designer_note` 비어있음 → **3개 레벨 전부 `kaleidoscope`**, W/H/팔레트도 동일 → **완전히 같은 결과**. (이게 사용자가 겪은 증상)

### ✅ 좋은 예 — 레벨마다 다른 패턴/색/크기
```csv
level_number,field_columns,field_rows,num_colors,color_distribution,bl_metaphor,designer_note
1,20,20,3,c1 c4 c7,줄무늬,
2,25,25,4,c2 c9 c12 c14,육각,
3,30,20,4,c5 c10 c6 c17,미로,
4,25,30,5,c1 c3 c11 c25 c8,동심 사각,
5,28,28,4,c13 c20 c2 c14,헤링본,
6,22,22,3,c4 c6 c17,픽셀 그리드,
```
→ 패턴: stripe / hex_tile / maze / concentric_sq / chevron* / rect_grid, 색·크기 모두 변주 → **레벨마다 뚜렷이 다른 결과**.
*(chevron은 랜덤풀 제외 패턴 — cluster 차단으로 누락될 수 있음. 안정성 우선이면 randompool 13종으로.)*

### 핵심 규칙
- **`bl_metaphor`를 행마다 다른 값으로** 채우는 것이 가장 효과적(한글, §B5 표 구절 포함).
- bl_metaphor 없이 쓰려면 `designer_note`에 `[Motif] hex` 처럼 **영어** 태그를 행마다 다르게.
- 같은 패턴이라도 **`color_distribution`/`num_colors`/`field_columns`/`field_rows`를 변주**하면 차이가 생긴다.
- ⚠️ **재실행으로는 절대 다양성이 안 생긴다** (seed가 `level_number` 고정). 입력 자체를 바꿔야 함.

---

## B6. Part B 운영자 체크리스트 (지금 증상 해결)

1. **레벨이 다 비슷하다** → 행마다 `bl_metaphor`(한글, §B5 표의 구절)가 **서로 다른 패턴으로** 채워졌는지 확인. 비어있거나 같은 패턴으로 매핑되면 전부 비슷해진다. bl_metaphor가 없으면 `designer_note`의 영어 `[Motif]`/`[Shape]`라도 채울 것.
2. **mood/style을 바꿔도 그대로다** → CSV 첨부 모드에선 정상(무시됨). 색감은 CSV `color_distribution`/`num_colors`로 조절.
3. **bl_metaphor를 채웠는데 반영 안 된다** → ① 값이 §B5 표의 한글 구절을 **substring으로 포함**하는지 확인(짧은 단어는 매칭 실패). ② 서버가 2026-05-22판 이상인지 확인(구버전은 미지원). ③ 여러 값이 같은 패턴(예: 나선/물방울/성운=wave)으로 수렴하지 않는지 확인.
4. **재생성해도 똑같다** → seed가 `level_number` 고정이라 결정성. 다른 결과가 필요하면 입력(bl_metaphor/W/H/팔레트)을 바꿔야 함. *재실행만으로는 절대 안 바뀐다.*
5. **모자이크가 필요** → 직접 대응 없음. `체크 패턴`/`육각`/`도트 패턴`으로 근사하거나, Part A PixelForge 이미지 생성으로.
6. **진짜 그라데이션/발광(빛)이 필요** → cowork는 이산 타일이라 불가. 동심/물결 근사만 됨. 연속 명암은 **Part A PixelForge(PixelLab, motif)** 또는 v43/v47 파이프라인으로.
7. **만화경/마름모/삼각패턴(kaleidoscope/diamond_check/i_tetromino)을 넣었는데 결과가 빠진다** → 이들은 cowork 랜덤풀 **제외 패턴**이라 빈칸 cluster≥ 한계로 `variant_pipeline`이 REJECT할 수 있음. dedup_skip/fail 로그 확인.

---

## B7. Part B 코드 빠른 참조표

| 동작 | 위치 |
|---|---|
| CSV 헤더 별칭 / bl_metaphor 파싱 | `batches/page.tsx:43-71`, `:208-209` |
| batch 모드 payload(csv_rows) | `batches/page.tsx:1055` |
| CSV 첨부 시 mood/style 무시 | `api/agents/batches/route.ts:158`, `:196-213` |
| watcher spawn | `api/agents/batches/route.ts:229-238` |
| CSV 모드 분기(mood/style 무시) | `batch_generate_levels.py:810-812` (라이브) |
| `generate_one_from_csv` 진입 | `batch_generate_levels.py:446` (라이브) |
| **패턴 결정(pattern ?? bl_metaphor ?? motif)** | `batch_generate_levels.py:485-488` (라이브) |
| **bl_metaphor 한글 매핑 48종** | `batch_generate_levels.py:169` `KO_METAPHOR_TO_PATTERN` (라이브) |
| **`_pattern_from_bl_metaphor`** | `batch_generate_levels.py:222-231` (라이브) |
| designer_note 영어 모티프 LUT | `batch_generate_levels.py:128` `MOTIF_KEYWORDS` (라이브) |
| `_pattern_from_motif` (영어만) | `batch_generate_levels.py:235`, 매칭 루프 `:251` (라이브) |
| seed 결정성 | `batch_generate_levels.py:491` `seed = level_no*13+7` (라이브) |
| run_csv_batch | `batch_generate_levels.py:614` (라이브) |
| cowork 랜덤풀 13종 / 제외 4종 | `batch_generate_levels.py` `COWORK_PATTERNS` |
| 전체 패턴 19종 레지스트리 | `pattern_lib/pixel_pattern_api.py:2485` `PATTERN_FUNCS` |
| 빈칸 cluster 차단(REJECT) | `pattern_lib/variant_pipeline.py`, `blank_engine.py` |

> ⚠️ Part B의 일부 라인 번호는 **로컬 구버전 미러 기준**이고, bl_metaphor 관련 라인(`:169/:222/:485-488`)은 **Mother 라이브 파일(2026-05-22판)에서 직접 확인**한 값이다. 두 버전이 섞여 있으니, 정확한 라인은 라이브 파일에서 재확인할 것:
> `ssh aimed@100.77.190.68 'grep -n "bl_metaphor\|KO_METAPHOR\|_pattern_from" /home/aimed/.hermes/watcher/batch_generate_levels.py'`

---

*Part B 작성·검증 기준: Mother 실서버(`aimed@100.77.190.68`) 라이브 `batch_generate_levels.py`(2026-05-22, 34,900 bytes)를 SSH로 직접 확인(2026-06-04) + `projecthub-web` 프론트(로컬 미러). 로컬 watcher 미러(2026-04-29)는 구버전이라 bl_metaphor 미지원 — 본 문서는 라이브 동작을 정본으로 한다.*
