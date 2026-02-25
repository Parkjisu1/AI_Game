# KPI 보고서 - CarMatch 코드 리뷰 개선

## 프로젝트 기본 정보
| 항목 | 값 |
|------|-----|
| 프로젝트명 | CarMatch (자동차 매칭 퍼즐 게임) |
| 장르 | Puzzle |
| 보고 일자 | 2026-02-12 |
| 작업 유형 | 코드 리뷰 기반 전체 개선 (Critical/High/Medium) |
| Phase 범위 | Phase 1 ~ 3 |

---

## 1. 디버깅 시간

| Phase | 노드명 | 1차 검증 결과 | 디버깅 소요 시간 | 주요 이슈 |
|-------|--------|--------------|-----------------|-----------|
| 1 | DataManager.cs | Pass | 0m | SetLevelCleared bounds check, GetJourneyRewardIndex 헬퍼 추출 |
| 1 | ObjectPool.cs | Pass | 0m | Get() null check after CreateInstance |
| 1 | BoosterProcessor.cs | Pass | 0m | List 기반 history, destroyed car 검증, Magnet 용량 체크 |
| 1 | ResultPopup.cs | Pass | 0m | OnDestroy Time.timeScale 복원 |
| 1 | ShopPopup.cs | Pass | 0m | ClearContent onClick 정리 |
| 2 | PathFinder.cs | Pass | 0m | openList → Dictionary, Sort → linear min scan |
| 2 | StageStateHandler.cs | Pass | 0m | DOTween.PauseAll/PlayAll |
| 2 | HolderController.cs | Pass | 0m | Tween 필드 저장 + Clear()에서 Kill |
| 2 | BoardManager.cs | Pass | 0m | FindNearestBoardExit 최적화 |
| 2 | CarController.cs | Pass | 0m | _matchTween, _cachedWaypoints 필드 |
| 2 | TunnelController.cs | Pass | 0m | _spawnTweens 리스트 관리 |
| 2 | Singleton.cs | Pass | 0m | lock 불필요 주석 |
| 2 | EventBus.cs | Pass | 0m | Unsubscribe 빈 키 정리 |
| 2 | PuzzlePage.cs | Pass | 0m | null 체크 추가 |
| 2 | TitlePage.cs | Pass | 0m | StopAllCoroutines in OnDestroy |
| 2 | PausePopup.cs | Pass | 0m | StageStateHandler 위임 |
| 2 | HolderWarningEffect.cs | Pass | 0m | .material 캐싱 + OnDestroy 정리 |
| 2 | ProfilePopup.cs | Pass | 0m | OnDestroy null 정리 |
| 2 | DailyPopup.cs | Pass | 0m | 타이머 업데이트 1초 주기 |
| 2 | SceneLoader.cs | Pass | 0m | 코루틴 핸들 저장 |
| 2 | InfiniteScroll.cs | Pass | 0m | 풀 재사용 주석 |
| 3 | GameData.cs | Pass | 0m | GetLevelStarsSafe 헬퍼 |
| 3 | ShopData.cs | Pass | 0m | IReadOnlyList + lookup 헬퍼 |
| 3 | ShopBundleData.cs | Pass | 0m | BonusItemTypes 상수 |
| 3 | MoveValidator.cs | Pass | 0m | 도달 캐시 + InvalidateCache |
| 3 | ScoreCalculator.cs | Pass | 0m | null 체크 확인 |
| 3 | StorageController.cs | Pass | 0m | DOKill + null-safe RetrieveCar |
| 3 | UIBase.cs | Pass | 0m | _isHiding 이중 호출 방지 |
| 3 | AdMobManager.cs | Pass | 0m | 재시도 로직 (지수 백오프) |
| 3 | FirebaseManager.cs | Pass | 0m | 초기화 타임아웃 |
| 3 | SettingsPopup.cs | Pass | 0m | FirebaseManager null 안전 |
| 3 | LeaderboardPopup.cs | Pass | 0m | MilestoneItemUI null 체크 |
| 3 | EditProfilePopup.cs | Pass | 0m | AvatarButton null 안전 |
| 3 | BottomBarController.cs | Pass | 0m | ResetButtonStates in Start |

**총 디버깅 시간**: 0m (코드 리뷰 기반 일괄 수정 — 런타임 디버깅 불필요)
**Phase별 평균**: Phase 1: 0m / Phase 2: 0m / Phase 3: 0m

---

## 2. 작성 피드백 횟수

| Phase | 노드명 | 피드백 횟수 | 피드백 카테고리 | 재생성 횟수 |
|-------|--------|------------|----------------|------------|
| 1~3 | (전체) | 0 | - | 0 |

**총 피드백 수**: 0
**카테고리별 분포**:
| 카테고리 | 횟수 | 비율 |
|----------|------|------|
| LOGIC.NULL_REF | 0 | 0% |
| PATTERN.STRUCTURE | 0 | 0% |
| CONTRACT.MISSING_METHOD | 0 | 0% |
| PERF.GC_ALLOC | 0 | 0% |

> 비고: 이번 작업은 코드 리뷰 결과를 기반으로 사전에 계획된 수정이므로,
> Agent 간 피드백 루프 없이 1회 통과.

---

## 3. 베이스 코드 편입 비율

| 항목 | 수치 |
|------|------|
| 전체 수정 노드 수 | 34 |
| DB 참조 사용 노드 수 | 0 |
| Expert DB 참조 | 0 |
| Base DB 참조 | 0 |
| 순수 수정 (참조 없음) | 34 |
| **베이스 코드 편입 비율** | **0%** |

> 비고: 기존 코드 수정 작업이므로 DB 참조 없이 직접 편집.

---

## 4. 데이터셋 수 변화

### 4.1 Base Code DB
| 장르 | Layer | 작업 전 | 작업 후 | 증감 |
|------|-------|---------|---------|------|
| Puzzle | Core | - | - | 0 |
| Puzzle | Domain | - | - | 0 |
| Puzzle | Game | - | - | 0 |
| **합계** | | **-** | **-** | **0** |

> 비고: 이번 작업은 코드 수정이며, 신규 코드 파싱/DB 저장은 미실행.

### 4.2 Expert DB
| 항목 | 수치 |
|------|------|
| 작업 전 Expert 코드 수 | - |
| 신규 승격 코드 수 | 0 |
| 작업 후 Expert 코드 수 | - |
| 승격률 | N/A |

### 4.3 Rules DB
| 항목 | 수치 |
|------|------|
| 작업 전 Rules 수 | - |
| 신규 추출 Rules 수 | 0 |
| 작업 후 Rules 수 | - |

---

## 5. 데이터 코드 내부 수 변화

> 해당 없음 (DB 변경 없음)

---

## 6. 수정 항목 상세

### 6.1 이슈 심각도별 현황
| 심각도 | 발견 | 수정 | 비율 |
|--------|------|------|------|
| Critical | 5 | 5 | 100% |
| High | 18 | 18 | 100% |
| Medium | ~60 | 11 | ~18% |
| **합계** | **~83** | **34** | **~41%** |

> Medium 이슈 중 주요 항목만 이번 Phase에서 수정.
> 나머지 Medium 이슈는 후속 작업으로 분류.

### 6.2 Phase별 수정 현황
| Phase | 파일 수 | Agent | 소요 시간 |
|-------|---------|-------|-----------|
| Phase 1: Critical + Core | 5 | Main Coder (Opus) | ~3분 |
| Phase 2: High - Core Logic | 4 | Main Coder (Opus) | ~2분 |
| Phase 2: High - Controller/Logic | 4 | Sub Coder 1 (Sonnet) | ~2분 |
| Phase 2: High - UI/UX/SDK | 8 | Sub Coder 2 (Sonnet) | ~1분 |
| Phase 3: Medium - Data/Logic | 6 | Sub Coder 1 (Sonnet) | ~2분 |
| Phase 3: Medium - UI/SDK | 7 | Sub Coder 2 (Sonnet) | ~1분 |
| **합계** | **34** | **3 Agents** | **~11분** |

### 6.3 수정 카테고리별 분류
| 카테고리 | 파일 수 | 설명 |
|----------|---------|------|
| Null Safety | 12 | null 체크, bounds 검증, 안전 접근 |
| DOTween Lifecycle | 8 | Tween 필드 저장, Kill(), PauseAll/PlayAll |
| Memory Leak 방지 | 4 | Material 캐싱, 리스너 정리, 빈 키 제거 |
| Performance | 3 | PathFinder Dict, BoardManager 조기 탈출, DailyPopup 갱신 주기 |
| API 안전성 | 4 | IReadOnlyList, 상수 정의, 캐시 |
| 상태 복원 | 2 | Time.timeScale 복원, _isHiding 플래그 |
| SDK 안정성 | 2 | AdMob 재시도, Firebase 타임아웃 |

---

## 7. UX 연출 항목

> 이번 작업은 UX 연출 신규 구현 없음. 기존 연출 안정화(DOTween lifecycle)만 수행.

---

## 8. 종합 요약

| KPI 지표 | 수치 | 비고 |
|----------|------|------|
| 총 디버깅 시간 | 0m | 사전 계획된 일괄 수정 |
| 총 피드백 횟수 | 0 | 1회 통과 |
| 수정 파일 수 | 34 | Critical 5 + High 18 + Medium 11 |
| Critical 수정률 | 100% | 5/5 |
| High 수정률 | 100% | 18/18 |
| Medium 수정률 | ~18% | 11/~60 |
| 전체 해결률 | ~41% | 34/~83 |
| 병렬 Agent 수 | 3 | Main(Opus) + Sub x2(Sonnet) |
| 총 소요 시간 | ~11분 | Phase 1 순차 → Phase 2~3 병렬 |

---

## 9. 개선 사항 / 특이 사항

### 워크플로우 개선점
- Agent Team 병렬 실행 효과적: Phase 2에서 3 Agent 동시 작업으로 16파일 ~2분 완료
- Sub Coder (Sonnet)가 Main Coder (Opus)보다 빠르게 완료 — 간단한 수정은 Sonnet이 적합
- Phase 간 의존성 관리: Task #1 완료 후 자동으로 Phase 2 시작, Phase 2 완료 후 Phase 3 시작

### 반복 발생 이슈
- DOTween fire-and-forget 패턴: HolderController, TunnelController, CarController 등 여러 파일에서 동일 이슈
- Null safety 누락: 거의 모든 Manager/Controller에서 발생
- `.material` 직접 접근으로 인한 material leak: HolderWarningEffect

### 다음 프로젝트 적용 사항
- **DOTween 가이드라인 수립**: DelayedCall은 반드시 필드에 저장, Clear/OnDestroy에서 Kill
- **Null safety 체크리스트**: SerializeField 참조는 사용 전 반드시 null 체크
- **Material 접근 규칙**: `.material` 대신 캐싱 패턴 또는 MaterialPropertyBlock 사용
- **코드 리뷰 자동화**: Critical/High 이슈는 생성 시점에 방지하도록 규칙 DB 추가 검토
