/**
 * graph-model.js — 코드/설계 그래프의 노드·엣지 타입 정의와 정규화
 *
 * 왜 필요한가:
 *   기존 BalloonFlow 그래프는 "파일 텍스트에 클래스명이 등장하면 엣지"라 타입이 없다.
 *   그 결과 169노드 중 96개(57%)가 순환 판정이 되어 신호 역할을 못 한다.
 *   code_base.integration 에는 이미 타입이 있는 관계가 적재돼 있으므로
 *   (singleton_access 89 / event_subscribe 51 / event_publish 23 / pool_usage 9)
 *   그것을 그대로 엣지로 승격하기 위한 공통 어휘를 여기서 정의한다.
 *
 * Usage:
 *   const { NODE, EDGE, normalizeSymbol, isNoise, nodeId } = require('./lib/graph-model');
 */
'use strict';

// ---------------------------------------------------------------------------
// 노드 타입
// ---------------------------------------------------------------------------
const NODE = Object.freeze({
  FILE: 'file',           // 소스 파일 1개
  CLASS: 'class',         // 클래스/타입
  METHOD: 'method',       // 메서드 (Class.Method 형태)
  EVENT: 'event',         // 이벤트 이름 (pub/sub 양쪽이 붙는 지점)
  POOL_KEY: 'pool_key',   // ObjectPool 키
  PREFAB: 'prefab',       // 프리팹/리소스 경로
  FIELD: 'field',         // [SerializeField] — 씬 와이어링 대상
  EXTERNAL: 'external',   // Unity 내장·외부 라이브러리 심볼 (해결 불가 참조의 종착지)
  DESIGN: 'design',       // 기획 문서 노드 (design_base)
});

// ---------------------------------------------------------------------------
// 엣지 타입 — "A가 B를 어떻게 참조하는가"
// ---------------------------------------------------------------------------
const EDGE = Object.freeze({
  USES: 'uses',                 // 일반 참조 (타입 미상)
  CALLS: 'calls',               // 싱글톤/정적 메서드 호출 — integration.singleton_access
  PUBLISHES: 'publishes',       // 이벤트 발행 — integration.event_publish
  SUBSCRIBES: 'subscribes',     // 이벤트 구독 — integration.event_subscribe
  POOL_GET: 'pool_get',         // 풀에서 꺼냄 — integration.pool_usage(action=Get)
  POOL_RETURN: 'pool_return',   // 풀로 반납 — integration.pool_usage(action=Return)
  LOADS: 'loads',               // Resources.Load / Addressables
  INSTANTIATES: 'instantiates', // Instantiate 호출
  WIRES: 'wires',               // SerializeField 와이어링
  IMPLEMENTS: 'implements',     // 기획 → 코드 (아직 데이터 없음, 스키마만 예약)
});

/** 방향이 뒤집힌 짝 — 역방향 인덱스를 만들 때 쓴다. */
const INVERSE_LABEL = Object.freeze({
  [EDGE.USES]: 'used_by',
  [EDGE.CALLS]: 'called_by',
  [EDGE.PUBLISHES]: 'published_by',
  [EDGE.SUBSCRIBES]: 'subscribed_by',
  [EDGE.LOADS]: 'loaded_by',
  [EDGE.INSTANTIATES]: 'instantiated_by',
  [EDGE.WIRES]: 'wired_by',
  [EDGE.IMPLEMENTS]: 'implemented_by',
});

// ---------------------------------------------------------------------------
// 정규화 — 실측 데이터에서 나온 노이즈를 거른다
//
// code_base.uses 실제 값 예: ["900","BoardStateManager","CurrencyManager","EventBus",...]
//   → "900" 같은 숫자, "Instance"/"Singleton" 같은 일반 토큰이 섞여 있다.
// requires 고유값 53개 중 실제 노드로 해결되는 건 18개(34%)뿐이고
//   나머지는 MonoBehaviour / Ease / Mask 같은 Unity·라이브러리 심볼이다.
//   이들은 버리지 않고 EXTERNAL 노드로 보낸다 (버리면 "왜 안 이어지지"를 못 본다).
// ---------------------------------------------------------------------------

/** 심볼로 볼 수 없는 값 (숫자, 한 글자, 제네릭 시그니처 조각 등) */
const NOISE_EXACT = new Set([
  'Instance', 'instance', 'Singleton', 'this', 'base', 'value', 'var',
  'true', 'false', 'null', 'new', 'string', 'int', 'float', 'bool', 'void',
]);

/** Unity·표준 라이브러리 심볼 — EXTERNAL 노드로 분류 */
const EXTERNAL_HINTS = [
  'MonoBehaviour', 'ScriptableObject', 'GameObject', 'Transform', 'Component',
  'Coroutine', 'IEnumerator', 'Vector2', 'Vector3', 'Quaternion', 'Color',
  'Mask', 'Image', 'Text', 'Button', 'Canvas', 'RectTransform', 'Sprite',
  'Ease', 'Tween', 'Sequence', 'DOTween',
  'List', 'Dictionary', 'Action', 'Func', 'Task', 'Object',
];
const EXTERNAL_SET = new Set(EXTERNAL_HINTS);

/**
 * 심볼 정규화.
 * @returns {string|null} 정규화된 이름, 노이즈면 null
 */
function normalizeSymbol(raw) {
  if (raw == null) return null;
  let s = String(raw).trim();
  if (!s) return null;

  // 제네릭 시그니처 조각 제거: "MonoBehaviour where T : MonoBehaviour" → "MonoBehaviour"
  const whereAt = s.indexOf(' where ');
  if (whereAt > 0) s = s.slice(0, whereAt).trim();
  // 제네릭 인자 제거: "List<Foo>" → "List"
  s = s.replace(/<.*$/, '').trim();
  // 배열/포인터 표기 제거
  s = s.replace(/[\[\]\*\&]/g, '').trim();
  // 네임스페이스 마지막 조각만: "Game.Core.EventBus" → "EventBus"
  if (s.includes('.') && !s.includes('(')) {
    const parts = s.split('.').filter(Boolean);
    s = parts[parts.length - 1] || s;
  }
  if (!s) return null;
  return s;
}

/** 노드로 삼을 수 없는 값인가 */
function isNoise(raw) {
  const s = normalizeSymbol(raw);
  if (!s) return true;
  if (NOISE_EXACT.has(s)) return true;
  if (/^\d+$/.test(s)) return true;              // "900"
  if (s.length < 2) return true;                  // 한 글자
  if (/^[0-9a-f]{8,}$/i.test(s)) return true;     // 해시형 id ("1a8c00489662")
  return false;
}

/** Unity·외부 라이브러리 심볼인가 */
function isExternal(raw) {
  const s = normalizeSymbol(raw);
  if (!s) return false;
  return EXTERNAL_SET.has(s);
}

/**
 * 이벤트 이름다운가.
 *
 * parser 의 event_publish/subscribe 추출은 `+=` / `?.Invoke` 패턴을 잡는데,
 * C# 에서 그 패턴은 UnityEvent 필드(`onClick`)나 지역 델리게이트(`_completeTimer`)에도 쓰인다.
 * 실측: 필터 없이 만들면 EVENT 노드 126개 중 상당수가 `elapsed`,`totalAttempts` 같은 필드였고
 * "구독만 있고 발행 없음" 90건이 대부분 오탐이었다.
 *
 * 규칙: 대문자로 시작하고 On... 또는 Event/Changed/Completed 류를 포함하는 것만 이벤트로 본다.
 * 나머지는 필드로 보고 그래프에 올리지 않는다.
 */
function isLikelyEvent(raw) {
  const s = normalizeSymbol(raw);
  if (!s) return false;
  if (s.startsWith('_')) return false;              // private 필드
  if (!/^[A-Z]/.test(s)) return false;              // onClick, elapsed …
  return /^On[A-Z]/.test(s) || /Event|Changed|Completed|Started|Finished|Updated/.test(s);
}

/** 노드 id — 타입이 다르면 같은 이름도 다른 노드다 */
function nodeId(type, name) {
  return `${type}:${normalizeSymbol(name) || String(name)}`;
}

/** 엣지 id — 같은 (from,to,type)은 하나로 합치고 weight를 올린다 */
function edgeId(from, to, type) {
  return `${from}|${type}|${to}`;
}

module.exports = {
  NODE,
  EDGE,
  INVERSE_LABEL,
  EXTERNAL_HINTS,
  normalizeSymbol,
  isNoise,
  isExternal,
  isLikelyEvent,
  nodeId,
  edgeId,
};
