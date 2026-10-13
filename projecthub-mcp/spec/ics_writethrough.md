# ICS Write-through Adapter — Design Spec

> ProjectHub Unity MCP의 **ICS write-through adapter**. Modify RPC가 Unity 상태를 바꿀 때마다, 같은 트랜잭션 안에서 `_CONTRACTS.yaml`과 `_ASSET_MANIFEST.yaml`을 자동 갱신해 코드/씬과 yaml 사이 드리프트를 0으로 만든다.
>
> 위치: MCP 서버(Node.js) 안의 라이브러리 모듈. 별도 서비스 X.
> 버전: 0.1-draft (2026-05-07)

---

## 1. 책임 범위

**들어오는 것**: 각 Modify 툴이 끝난 직후의 `IcsChange` 후보 리스트 (`tier1_rpc.yaml`의 `ics_write_through.rules`에서 derive).

**하는 것**:
- 프로젝트 yaml 파일 디스커버리
- 변경 후보 → 기존 yaml과 충돌 검사 → atomic write
- 실패 시 호출자(MCP)에 에러 반환 (호출자는 `tx.undo`로 Unity 상태 롤백)

**안 하는 것**:
- yaml 초기 생성 (Phase 0 부트스트랩은 별도 도구)
- 양방향 검증 (`validate.contracts` 툴이 담당)
- 코드 → yaml 역방향 추출 (이건 Validator Stage 5.5의 일)

---

## 2. 파일 디스커버리

```
{unity_project_root}/
├── Assets/
└── ProjectSettings/

{unity_project_root}/_ics/      ← 어댑터가 관리하는 yaml 디렉토리
├── _CONTRACTS.yaml
├── _ASSET_MANIFEST.yaml
└── .lock                        ← 동시 쓰기 가드
```

- `unity_project_root`는 MCP 서버 시작 시 환경변수 `UNITY_PROJECT_ROOT`로 주입.
- yaml은 **`Assets/` 밖**에 둔다 — Unity가 import하지 않게. Editor 스크립트가 파싱할 때만 명시적으로 읽음.
- 부재 시 어댑터가 빈 골격으로 자동 생성 (`project: ""`, `version: 1`, 모든 섹션 `[]`).

---

## 3. yaml 스키마 (검증 + 추가 키)

CLAUDE.md의 기존 스키마를 준수하되, 어댑터가 추가하는 메타 필드 정의:

### `_CONTRACTS.yaml`

```yaml
project: "BalloonFlow"
version: 1
last_updated: "2026-05-07T13:42:11Z"     # ISO 8601 UTC, 어댑터가 매 갱신마다 업데이트

events:
  - name: OnBalloonPopped
    struct_file: GameEvents.cs
    fields: { balloonId: int, color: int, position: Vector3 }
    publishers: [BalloonController]
    subscribers: [PopProcessor, ScoreManager]
    _meta:                                # 어댑터 전용
      created_by: "mcp"                   # "mcp" | "main_coder" | "manual"
      tx_id: "tx_2026-05-07_18:42:03_a3f"  # 추적용

pool_keys:
  - key: "Balloon"
    prefab_path: "Assets/Prefabs/Balloon.prefab"
    consumers: [BalloonController]
    required_components: [SpriteRenderer, CircleCollider2D]
    initial_size: 30
    _meta: { created_by: "mcp", tx_id: "..." }

serialized_fields:
  - class: GameBootstrap
    field: _titlePage
    type: CanvasGroup
    wired_by: SceneBuilder
    scene_object_name: "TitlePage"
    _meta: { created_by: "mcp", tx_id: "..." }

method_calls: [...]                       # MCP 1차에서는 자동 derive 안 함 (수동만)
asset_requirements: [...]
```

### `_ASSET_MANIFEST.yaml`

```yaml
project: "BalloonFlow"
version: 1
last_updated: "2026-05-07T13:42:11Z"

prefabs:
  - name: Balloon
    path: "Assets/Prefabs/Balloon.prefab"
    components: [SpriteRenderer, CircleCollider2D]
    pool_key: "Balloon"
    created_by: "mcp"
    _meta: { tx_id: "...", first_created: "2026-05-07T...", last_modified: "..." }

scenes:
  - name: GameScene
    path: "Assets/Scenes/GameScene.unity"
    created_by: "mcp" | "SceneBuilder"
    manager_objects: [...]
    serialized_field_wiring: [...]
    _meta: { ... }

editor_scripts: [...]                     # SceneBuilder.cs 등 — 어댑터가 갱신 안 함
resources: [...]
```

**`_meta` 정책**: yaml 사람도 읽기 위해 핵심 필드는 그대로, 추적용은 `_meta`에 격리. 사람이 yaml 손으로 편집할 때 `_meta` 무시 가능.

---

## 4. 동시성

```
HTTP 요청 N개 → MCP 서버 큐 → 직렬화 → Unity 메인 스레드 1개씩 실행
                                    ↓
                              Modify 성공
                                    ↓
                    ICS adapter (이 모듈) 호출
                                    ↓
              flock(_ics/.lock, LOCK_EX) ← 어댑터 자체 락
                                    ↓
                  yaml 읽기 → 변경 적용 → atomic write
                                    ↓
                              flock 해제
```

- MCP 서버 큐가 이미 직렬화하므로 MCP 1개 인스턴스에서는 lock 사실상 불필요.
- 그러나 사람이 IDE/에디터에서 yaml을 동시에 편집할 가능성 → **lockfile 필수**. `proper-lockfile` 라이브러리 사용 (Node.js).
- 락 timeout 5초. 초과 시 `ics.lock_timeout` 에러 반환 → MCP가 호출자에게 그대로 전파 → 호출자가 `tx.undo` 결정.

---

## 5. atomic write

```js
async function atomicWrite(filepath, content) {
  const tmp = filepath + ".tmp." + crypto.randomBytes(4).toString('hex');
  await fs.writeFile(tmp, content, 'utf8');
  await fs.rename(tmp, filepath);   // POSIX atomic. Windows는 fs.rename도 atomic이지만 fail 시 .tmp 잔존.
}
```

- Windows에서 같은 파일을 다른 프로세스가 lock 중이면 rename 실패 → 1회 재시도 후 실패.
- `_ics/.tmp.*` 잔존 파일은 어댑터 시작 시 청소.

---

## 6. derive 함수 — Modify 툴 → IcsChange[]

각 Modify 툴이 `tier1_rpc.yaml`에 정의된 룰대로 IcsChange 리스트를 만든다. 함수 구현은 `derive.ts`:

```typescript
type DeriveContext = {
  toolName: string;
  params: any;          // 호출자가 보낸 RPC 파라미터
  result: any;          // Unity 브릿지가 반환한 데이터 (예: created prefab 의 실제 GUID, 검출된 SerializeField 목록)
  txId: string;
};

function derive(ctx: DeriveContext): IcsChange[];
```

**예시 1 — `modify.prefab.create`**:
```typescript
function deriveForPrefabCreate(ctx) {
  const changes: IcsChange[] = [];
  const components = ctx.params.components.map(c => stripNamespace(c.type_name));
  changes.push({
    file: "_ASSET_MANIFEST.yaml",
    op: "append_prefab",
    entry: {
      name: basenameNoExt(ctx.params.path),
      path: ctx.params.path,
      components,
      pool_key: ctx.params.pool_key ?? null,
      created_by: "mcp",
      _meta: { tx_id: ctx.txId, first_created: nowIso() },
    },
  });
  if (ctx.params.pool_key) {
    changes.push({
      file: "_CONTRACTS.yaml",
      op: "append_pool_key",
      entry: {
        key: ctx.params.pool_key,
        prefab_path: ctx.params.path,
        consumers: [],            // 사용자가 나중에 채움 또는 코드 스캐너 발견
        required_components: components,
        initial_size: 30,
        _meta: { created_by: "mcp", tx_id: ctx.txId },
      },
    });
  }
  return changes;
}
```

**예시 2 — `modify.serializedfield.set`**:
```typescript
function deriveForSerializedFieldSet(ctx) {
  // Unity 브릿지가 반환한 result에 has_serialize_attribute 포함됐다고 가정
  if (!ctx.result.has_serialize_attribute && !ctx.result.is_public) return [];
  const isSceneRef = ctx.params.value.kind === "scene_object_ref";
  const isAssetRef = ctx.params.value.kind === "asset_ref";
  if (!isSceneRef && !isAssetRef) return [];   // primitive 값은 SerializeField 계약과 무관

  const change: IcsChange = {
    file: "_CONTRACTS.yaml",
    op: "append_serialized_field",
    entry: {
      class: stripNamespace(ctx.params.target.type_name),
      field: ctx.params.field_name,
      type: ctx.result.field_type,
      wired_by: "mcp",
      scene_object_name: isSceneRef
        ? ctx.params.value.ref.hierarchy_path.split("/").pop()
        : null,
      _meta: { created_by: "mcp", tx_id: ctx.txId },
    },
  };
  return [change];
}
```

각 derive 함수는 순수 함수 (I/O 없음). 테스트 작성 용이.

---

## 7. apply 함수 — IcsChange[] 적용

```typescript
async function applyChanges(changes: IcsChange[], txId: string): Promise<ApplyResult> {
  const release = await lockfile.lock(LOCK_PATH, { retries: 5 });
  try {
    const grouped = groupBy(changes, c => c.file);
    const written: string[] = [];

    for (const [file, fileChanges] of grouped) {
      const filepath = path.join(ICS_DIR, file);
      const doc = await loadYaml(filepath) ?? emptySkeleton(file);

      for (const ch of fileChanges) {
        applyOpInPlace(doc, ch);   // op-별 swich (append_prefab, append_event 등)
      }
      doc.last_updated = nowIso();
      doc.version = doc.version ?? 1;

      validateSchema(doc, file);   // 누락 필수 필드 / 중복 키 / 타입 위배 검사
      await atomicWrite(filepath, yamlStringify(doc));
      written.push(file);
    }
    return { ok: true, written };
  } catch (err) {
    return { ok: false, error: classify(err) };
  } finally {
    await release();
  }
}
```

**중복 검사 — append op는 idempotent**:
- `append_prefab`: 같은 `path`가 이미 있으면 *update*로 강등 (components/pool_key/_meta 갱신).
- `append_event`: 같은 `name` + `struct_file`이면 publishers/subscribers union으로 병합.
- `append_pool_key`: 같은 `key`면 update.
- `append_serialized_field`: 같은 `class`+`field`면 update (type/wiring 변경 가능).

→ 여러 번 호출해도 yaml 안전하게 안정.

---

## 8. 실패 처리 + 롤백

```
[Modify RPC 도착]
    ↓
[Unity 브릿지 호출] → 성공/실패
    ↓ 성공
[derive(ctx) → IcsChange[]]
    ↓
[applyChanges(changes)] → 성공/실패
    ↓ 실패
[ROLLBACK: 호출자에게 ics.write_through_failed 반환]
    ↓
[MCP 서버: 자동으로 tx.undo(undo_group_id) 호출]
    ↓
[Unity 브릿지: Undo.RevertAllDownToGroup]
    ↓
[클라이언트에 최종 응답: 실패 + 롤백 완료]
```

**중요**: ICS write 실패는 Modify를 "성공한 척" 두지 않는다. yaml과 코드의 진실이 다르면 시스템 전체가 망가진다.

**예외**: `applyChanges`가 락 timeout으로 실패 시는 yaml 자체는 변경 안 됨 → 호출자에게 `ics.lock_timeout` 반환, MCP는 자동 롤백. 단, 락 timeout이 흔하면 시스템 설계 결함 (다른 프로세스가 yaml을 너무 오래 잡고 있다).

---

## 9. 디버깅 + 감사

각 적용된 IcsChange는 `_ics/audit.jsonl`에 한 줄씩 append:

```json
{"ts": "2026-05-07T13:42:11Z", "tx_id": "tx_...", "tool": "modify.prefab.create", "file": "_ASSET_MANIFEST.yaml", "op": "append_prefab", "entry_summary": "Balloon @ Assets/Prefabs/Balloon.prefab"}
```

- 한 줄/IcsChange. 디버그 + 감사 추적용.
- 어댑터 자체는 회전/삭제 안 함. cron으로 주기 archive (별도 작업).

---

## 10. 테스트 전략

### 단위 테스트 (Node.js, vitest 가정)
- derive 함수 17개 (1차 MCP의 Modify 7툴 × 평균 2~3개 yaml 영향 = ~17 derive 시나리오)
- apply 함수: 빈 yaml에 append, 기존에 update, 중복 idempotent, 스키마 위배

### 통합 테스트
- 픽스처 yaml + 시뮬 RPC 호출 → 결과 yaml 비교 (snapshot)
- 락 timeout 시뮬

### 로컬 e2e
- 실제 Unity 안 띄우고: MCP 서버 + ICS 어댑터만 띄움 + dummy Unity bridge (HTTP mock)
- `modify.prefab.create` 호출 → yaml 갱신 확인 → audit 로그 확인

---

## 11. 외부 의존

| 라이브러리 | 용도 |
|---|---|
| `js-yaml` | yaml parse/stringify |
| `proper-lockfile` | flock |
| `zod` 또는 `ajv` | schema validation |
| `vitest` | 테스트 |

전부 Node.js 표준 라이브러리 외 4개. 가벼운 편.

---

## 12. 1차 범위 명시

**들어가는 것**:
- `modify.prefab.create` → prefab + (옵션) pool_key
- `modify.prefab.modify` → 컴포넌트 추가/제거/필드 변경 → prefab manifest update + serialized_field append
- `modify.gameobject.add_to_scene` → scenes.manager_objects 또는 scenes.serialized_field_wiring
- `modify.gameobject.modify` → 위와 동일
- `modify.serializedfield.set` → serialized_fields append
- `modify.asset.move` → manifest에서 path 일괄 갱신
- `modify.asset.delete` → manifest에서 제거 (부서진 ref 있어도 force=true면 진행)

**1차에서 자동 derive 하지 않는 것** (수동 갱신 또는 별도 도구):
- `events` (publish/subscribe) — 코드 스캐너가 더 정확. 1차에서는 수동.
- `method_calls` — 마찬가지.
- `asset_requirements` — `prefabs`/`resources`로 충분.
- `editor_scripts` — Editor/SceneBuilder.cs 변경은 어댑터 영역 외.

---

## 13. 확정 사항 (2026-05-07)

1. **ICS yaml 위치**: `{unity_project_root}/_ics/` — `Assets/` 밖 (Unity import 회피). 예: `C:/projects/balloonflow/_ics/`.
   - `_CONTRACTS.yaml`, `_ASSET_MANIFEST.yaml` → 커밋. `audit.jsonl`, `.lock`, `.tmp.*` → gitignore.
2. **여러 Unity 프로젝트 동시 지원**: 단일 프로젝트 가정. 멀티는 2차로 보류.
3. **yaml 스키마 버저닝**: `version: 1` 시작. v2 마이그레이션 시 어댑터에 마이그레이션 함수.
4. **MCP 서버 배포 위치**: **빌드컴 (Machine B, `100.92.43.9`, `C:/projects/balloonflow/`)**. Unity 엔진과 같이 위치. Hermes(Mother)는 SSH/HTTP로 호출.
