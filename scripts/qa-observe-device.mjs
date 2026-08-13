#!/usr/bin/env node
/**
 * qa-observe-device.mjs — 실기(Android) 관측으로 기능 QA ③등급을 채운다.
 *
 * 왜 이게 필요한가
 *   ①구조·②컴파일이 통과해도 "아이템 사용이 실제로 되는가"는 알 수 없다.
 *   그건 **실제 빌드가 그 기능을 수행한 기록**으로만 답할 수 있다.
 *   이 스크립트는 실기에 붙어 그 기록(=Firebase Analytics 이벤트, 게임 자체 로그)을 받아
 *   카탈로그의 기능 신호와 맞춰 `confidence=direct` 관측으로 올린다.
 *   시뮬레이터(proxy)와 달리 이것만이 화면에서 초록(=된다)이 된다.
 *
 * 사용법 (권장: 사람이 폰에서 실제로 플레이하는 동안 돌린다)
 *   node qa-observe-device.mjs --duration 300            # 5분 관측
 *   node qa-observe-device.mjs --duration 300 --post     # 관측 + ProjectHub 업로드
 *
 * 전제 — 릴리스 빌드에서 FA 이벤트를 보려면 아래가 필요하다(스크립트가 자동으로 건다):
 *   adb shell setprop debug.firebase.analytics.app <package>
 *   ※ log.tag.FA VERBOSE 만으로는 안 나온다(실측). 프로퍼티를 건 뒤 앱을 **재시작**해야 한다.
 *
 * 정직성 규칙
 *   - 이벤트가 안 잡힌 기능은 아무것도 올리지 않는다(미검증으로 남긴다).
 *     "관측 안 됨"을 "안 됨(fail)"으로 올리면 오탐이다 — 그냥 그 기능을 안 했을 수도 있다.
 *   - fail 을 올리는 건 사람이 "했는데 안 됐다"를 확인했을 때뿐이다(--fail <featureId>).
 */
import fs from "fs";
import path from "path";
import { execFileSync } from "child_process";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (n, d = null) => { const i = process.argv.indexOf(`--${n}`); return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : d; };
const has = (n) => process.argv.includes(`--${n}`);

const PROJECT = (arg("project", "balloonflow") || "").toLowerCase();
const PACKAGE = arg("package", "xyz.aimed.balloonloop");
const DURATION = parseInt(arg("duration", "180"), 10);
const ADB = arg("adb", process.env.ADB_PATH || "C:/Users/user/AppData/Local/Android/Sdk/platform-tools/adb.exe");
const DEVICE = arg("device", null);
const API = arg("api", process.env.QA_API || "http://100.77.190.68:3000");
const CATALOG = arg("catalog", path.join(HERE, "..", "qa", "features"));

const adb = (...a) => execFileSync(ADB, [...(DEVICE ? ["-s", DEVICE] : []), ...a],
  { encoding: "utf8", maxBuffer: 64 * 1024 * 1024, timeout: (DURATION + 120) * 1000 });

/**
 * 카탈로그 로드. js-yaml 이 없는 환경(워크스테이션)에서도 돌아야 하므로
 * 이 스크립트가 쓰는 필드(id/name/signals)만 뽑는 최소 파서를 폴백으로 둔다.
 */
async function loadCatalog() {
  const text = fs.readFileSync(path.join(CATALOG, `${PROJECT}.yaml`), "utf8");
  try {
    const { default: yaml } = await import("js-yaml");
    return yaml.load(text);
  } catch { /* 폴백 */ }

  const features = [];
  let cur = null, inSignals = false;
  for (const raw of text.split("\n")) {
    if (/^\s*#/.test(raw) || !raw.trim()) continue;
    const t = raw.trim();
    const indent = raw.match(/^ */)[0].length;
    if (t.startsWith("- id:")) { cur = { id: t.slice(5).trim(), signals: {} }; features.push(cur); inSignals = false; continue; }
    if (!cur) continue;
    if (t === "signals:") { inSignals = true; continue; }
    if (inSignals && indent >= 6) {
      const i = t.indexOf(":");
      if (i > 0) {
        const k = t.slice(0, i).trim(), v = t.slice(i + 1).trim();
        if (k === "analytics") cur.signals.analytics = v.replace(/^\[|\]$/g, "").split(",").map((x) => x.trim()).filter(Boolean);
        else if (k === "logcat") cur.signals.logcat = v.replace(/^"|"$/g, "").replace(/\\\\/g, "\\");
      }
      continue;
    }
    inSignals = false;
    if (t.startsWith("name:")) cur.name = t.slice(5).trim().replace(/^"|"$/g, "");
  }
  return { features };
}

/**
 * 기기 디스크의 미전송 이벤트 큐를 읽어 누적한다.
 *
 * 이 게임의 커스텀 이벤트는 **Firebase 가 아니라** Cloud Function → BigQuery 로 직접 간다
 * (AnalyticsManager.INGEST_URL). 그래서 FA logcat 을 아무리 켜도 `item_use_event` 같은
 * 게임 이벤트는 안 나온다 — 이걸 모르면 관측이 통째로 헛돈다.
 * 대신 AnalyticsManager 는 **전송 전 버퍼를 디스크에 영속화**한다
 * (`Application.persistentDataPath/bq_pending_events.json`, 외부 저장소라 adb 로 읽힌다).
 * 여기에 이벤트명·파라미터·타임스탬프가 그대로 있다 = 코드 수정도 빌드도 없이 얻는 직접 관측.
 *
 * 주의: flush 에 성공하면 파일에서 사라진다. 그래서 세션 중 **주기적으로 읽어 event_id 로 누적**한다.
 */
function pullDiskEvents(acc) {
  try {
    const raw = adb("shell", "cat", `/sdcard/Android/data/${PACKAGE}/files/bq_pending_events.json`);
    const arr = JSON.parse(raw.trim() || "[]");
    for (const e of arr) {
      const id = e?.data?.event_id || `${e?.name}:${e?.data?.event_timestamp}`;
      if (id && !acc.has(id)) acc.set(id, { name: e.name, ts: e?.data?.event_timestamp || "", data: e.data || {} });
    }
  } catch { /* 파일 없음/flush 직후 = 정상 */ }
}

async function main() {
  const cat = await loadCatalog();

  // featureId ← 신호 역인덱스. 하나의 이벤트가 여러 기능을 가리킬 수 있다.
  const byEvent = new Map();
  const logPatterns = [];
  for (const f of cat.features || []) {
    for (const e of f.signals?.analytics || []) {
      if (!byEvent.has(e)) byEvent.set(e, []);
      byEvent.get(e).push(f);
    }
    if (f.signals?.logcat) logPatterns.push({ re: new RegExp(f.signals.logcat), f });
  }

  console.log(`[관측] ${PROJECT} · ${PACKAGE} · ${DURATION}초`);
  console.log(`[관측] 기대 이벤트 ${byEvent.size}종: ${[...byEvent.keys()].join(", ")}`);

  // FA 디버그 로깅 — 릴리스 빌드에서도 이벤트를 logcat 으로 흘리게 한다.
  try {
    adb("shell", "setprop", "debug.firebase.analytics.app", PACKAGE);
    adb("shell", "setprop", "log.tag.FA", "VERBOSE");
    adb("shell", "setprop", "log.tag.FA-SVC", "VERBOSE");
  } catch { console.error("[경고] setprop 실패 — FA 이벤트가 안 잡힐 수 있다"); }

  if (has("relaunch")) {
    // 프로퍼티는 앱 프로세스 시작 시점에 읽힌다 — 이미 떠 있으면 재시작해야 적용된다.
    try { adb("shell", "am", "force-stop", PACKAGE); } catch { /* 무시 */ }
    adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1");
    console.log("[관측] 앱 재시작함");
  }

  adb("logcat", "-c");
  console.log(`[관측] 시작 — 지금 폰에서 검증할 기능을 실제로 플레이하세요 (${DURATION}초)`);
  // 화면이 잠들면 Unity 가 멈춘다 — 실측으로 이것 때문에 "부팅이 정지한 것처럼" 보였다.
  // 설정을 영구 변경(svc power stayon)하지 않고, 관측 중에만 주기적으로 깨운다.
  const CHUNK = 20;
  const diskEvents = new Map(); // event_id → {name, ts, data}
  for (let left = DURATION; left > 0; left -= CHUNK) {
    try { adb("shell", "input", "keyevent", "KEYCODE_WAKEUP"); } catch { /* 무시 */ }
    adb("shell", "sleep", String(Math.min(CHUNK, left)));
    pullDiskEvents(diskEvents);
  }
  pullDiskEvents(diskEvents);
  const raw = adb("logcat", "-d");
  console.log(`[관측] 로그 ${raw.split("\n").length}줄 수집`);

  // 두 경로를 합친다:
  //  (a) FA-SVC logcat — Firebase 자동 이벤트 (`Logging event: origin=auto,name=screen_view(_vs),…`)
  //  (b) 디스크 큐 — 게임 자체 이벤트(BigQuery 직행). 카탈로그 신호는 대부분 여기서 온다.
  const seen = new Map();
  for (const m of raw.matchAll(/\bname=([a-z0-9_]+)/g)) {
    seen.set(m[1], (seen.get(m[1]) || 0) + 1);
  }
  const detailOf = new Map();
  for (const [, e] of diskEvents) {
    seen.set(e.name, (seen.get(e.name) || 0) + 1);
    // 파라미터를 근거 문장에 남긴다 — "이벤트가 떴다"보다 "레벨 89에서 zap 을 썼다"가 훨씬 쓸모 있다.
    const bits = ["level_number", "item_id", "item_category", "currency_type", "amount", "placement", "end_reason"]
      .filter((k) => e.data[k] !== undefined && e.data[k] !== "")
      .map((k) => `${k}=${e.data[k]}`);
    detailOf.set(e.name, `${e.ts.slice(0, 19)}Z${bits.length ? " · " + bits.join(", ") : ""}`);
  }
  if (diskEvents.size) console.log(`[관측] 기기 디스크 큐에서 게임 이벤트 ${diskEvents.size}건 수집`);
  const hitLogs = new Map();
  for (const { re, f } of logPatterns) if (re.test(raw)) hitLogs.set(f.id, f);

  const observedAt = new Date().toISOString();
  const runs = [];
  for (const [ev, n] of seen) {
    for (const f of byEvent.get(ev) || []) {
      const extra = detailOf.get(ev);
      runs.push({ project: PROJECT, featureId: f.id, ok: true, confidence: "direct",
        source: `device:${(DEVICE || "default")}`, observedAt,
        detail: `실기에서 ${ev} 이벤트 ${n}회 관측${extra ? ` (${extra})` : ""} — ${PACKAGE}` });
    }
  }
  for (const [id, f] of hitLogs) {
    if (runs.some((r) => r.featureId === id)) continue;
    runs.push({ project: PROJECT, featureId: id, ok: true, confidence: "direct",
      source: `device:${(DEVICE || "default")}`, observedAt,
      detail: `실기 로그 패턴 관측: ${f.signals.logcat}` });
  }

  console.log("\n=== 관측된 이벤트 ===");
  const known = [...seen.entries()].filter(([e]) => byEvent.has(e));
  if (!known.length) console.log("(카탈로그 신호에 해당하는 이벤트 없음 — 해당 기능을 플레이하지 않았거나 앱이 그 지점까지 못 감)");
  for (const [e, n] of known) console.log(`  ${e} × ${n} → ${(byEvent.get(e) || []).map((f) => f.id).join(", ")}`);

  console.log("\n=== 관측 안 된 기능 (미검증으로 남음 — fail 로 올리지 않는다) ===");
  for (const f of cat.features || []) {
    if (!runs.some((r) => r.featureId === f.id)) console.log(`  ○ ${f.id} — ${f.name}`);
  }

  const outPath = arg("out", null);
  if (outPath) { fs.writeFileSync(outPath, JSON.stringify({ observedAt, runs, events: [...seen] }, null, 1)); console.log(`\n기록: ${outPath}`); }

  if (has("post") && runs.length) {
    const key = process.env.HERMES_INTERNAL_API_KEY || "";
    let ok = 0;
    for (const r of runs) {
      const res = await fetch(`${API}/api/qa/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(key ? { Authorization: `Bearer ${key}` } : {}) },
        body: JSON.stringify(r),
      });
      if (res.ok) ok++; else console.error(`  업로드 실패 ${r.featureId}: HTTP ${res.status}`);
    }
    console.log(`\n업로드 ${ok}/${runs.length}건 → ${API}`);
  } else if (has("post")) {
    console.log("\n올릴 관측이 없습니다.");
  }
}

main().catch((e) => { console.error("관측 실패:", e.message); process.exit(1); });
