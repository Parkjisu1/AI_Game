#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICS Validator (Stage 5.5) — Integration Contract System static checker.

CLAUDE.md defines _CONTRACTS.yaml / _ASSET_MANIFEST.yaml + a "Stage 5.5 Integration
Validation" that, until now, existed only as prose in prompts. This module makes it real:
it parses the contract and mechanically cross-checks it against the actual C# source,
catching integration defects that per-file validation misses.

Evidence basis (research 2026-09):
  - Design by Contract (Meyer 1992): interface errors between components + fault attribution.
  - Consumer-Driven Contracts (Pact/Aalto): contract-level checks catch integration defects
    unit tests miss (caught 23/23 seeded defects).
  - Clover (Stanford SAIV 2024): artifact<->code consistency gate ~87%/100%.
  - VeriCoding (2509.22908): weak/vacuous specs get gamed -> Tier C anti-vacuity checks.
  - MultiFileTest (2502.06556): cross-file (hallucinated symbol / signature mismatch) is
    the dominant LLM codegen failure -> exactly what method_calls / events checks target.

Tiers:
  A (deterministic): events, pool_keys, serialized_fields, method_calls, asset_requirements
  C (anti-vacuity / reverse): code-declared contracts absent from _CONTRACTS.yaml (drift),
     empty/log-only event subscribers (vacuous satisfaction).

Usage:
  python ics_validator.py --repo <unity-project-root> [--contracts path] [--json]
Returns: exit 0 = pass, 2 = contract violations found, 3 = error/unusable.
Read-only. Never modifies source.
"""
from __future__ import annotations
import argparse, json, os, re, sys, glob

try:
    import yaml  # PyYAML
except Exception:
    yaml = None


def _find(repo: str, name: str) -> str | None:
    for p in glob.glob(os.path.join(repo, "**", name), recursive=True):
        if os.path.isfile(p):
            return p
    return None


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


def _cs_files(repo: str) -> dict[str, str]:
    out = {}
    skip = re.compile(r"[\\/](Library|Temp|obj|PackageCache|Packages|Plugins)[\\/]", re.I)
    for p in glob.glob(os.path.join(repo, "**", "*.cs"), recursive=True):
        if skip.search(p):
            continue
        out[p] = _read(p)
    return out


def _basename_has(files: dict[str, str], base: str) -> str | None:
    for p in files:
        if os.path.basename(p) == base or os.path.basename(p) == base + ".cs":
            return p
    return None


def validate(repo: str, contracts_path: str | None) -> dict:
    findings: list[dict] = []

    def add(sev, kind, msg, ref=""):
        findings.append({"severity": sev, "kind": kind, "msg": msg, "ref": ref})

    cpath = contracts_path or _find(repo, "_CONTRACTS.yaml")
    if not cpath:
        return {"status": "no_contract", "findings": [],
                "note": "no _CONTRACTS.yaml found — ICS check skipped (not a failure)"}
    if yaml is None:
        return {"status": "error", "findings": [],
                "note": "PyYAML unavailable"}
    try:
        contract = yaml.safe_load(_read(cpath)) or {}
    except Exception as e:
        return {"status": "error", "findings": [],
                "note": f"contract parse failed: {e}"}

    files = _cs_files(repo)
    allsrc = "\n".join(files.values())

    # ---- Tier A: events (publisher publishes, subscriber subscribes) ----
    for ev in (contract.get("events") or []):
        name = ev.get("name", "?")
        for pub in (ev.get("publishers") or []):
            fp = _basename_has(files, pub)
            if not fp:
                add("error", "event.publisher.missing", f"event {name}: publisher class {pub} file not found")
            elif not re.search(r"(Publish|Raise|Invoke|Dispatch)\s*[<(].*%s" % re.escape(name), files[fp]) \
                    and name not in files[fp]:
                add("error", "event.publisher.nopublish", f"event {name}: {pub} does not reference/publish it")
        for sub in (ev.get("subscribers") or []):
            fp = _basename_has(files, sub)
            if not fp:
                add("error", "event.subscriber.missing", f"event {name}: subscriber class {sub} file not found")
            elif not re.search(r"(Subscribe|AddListener|On%s|\+=)" % re.escape(name), files[fp]) \
                    and name not in files[fp]:
                add("error", "event.subscriber.nosub", f"event {name}: {sub} does not subscribe")

    # ---- Tier A: pool_keys (key present in consumer Get/Return; prefab registered) ----
    manifest = {}
    mpath = _find(repo, "_ASSET_MANIFEST.yaml")
    if mpath:
        try:
            manifest = yaml.safe_load(_read(mpath)) or {}
        except Exception:
            manifest = {}
    manifest_prefabs = {p.get("name") or p.get("pool_key") for p in (manifest.get("prefabs") or [])}
    for pk in (contract.get("pool_keys") or []):
        key = pk.get("key", "?")
        for cons in (pk.get("consumers") or []):
            fp = _basename_has(files, cons)
            if not fp:
                add("error", "pool.consumer.missing", f"pool_key {key}: consumer {cons} not found")
            elif key not in files[fp]:
                add("error", "pool.key.unused", f"pool_key {key}: not referenced in consumer {cons}")

    # ---- Tier A: serialized_fields ([SerializeField] present + wired by builder) ----
    for sf in (contract.get("serialized_fields") or []):
        cls = sf.get("class", "?"); fld = sf.get("field", "?"); wiredby = sf.get("wired_by", "")
        fp = _basename_has(files, cls)
        if not fp:
            add("error", "sf.class.missing", f"serialized_field {cls}.{fld}: class file not found")
        else:
            if not re.search(r"\[SerializeField\][^\n;]*\b%s\b" % re.escape(fld), files[fp]) \
                    and not re.search(r"\b%s\b" % re.escape(fld), files[fp]):
                add("error", "sf.field.missing", f"serialized_field {cls}.{fld}: [SerializeField] not found in {cls}")
        if wiredby:
            wp = _basename_has(files, wiredby)
            if wp and ("WireField" not in files[wp] and fld not in files[wp]):
                add("warn", "sf.notwired", f"serialized_field {cls}.{fld}: {wiredby} has no wiring reference")

    # ---- Tier A: method_calls (caller calls, target defines) ----
    for mc in (contract.get("method_calls") or []):
        caller = (mc.get("caller") or "")
        target = (mc.get("target") or "")
        tgt_cls = target.split(".")[0] if "." in target else ""
        tgt_method = re.split(r"[.(]", target)[1] if "." in target else target
        if tgt_cls:
            fp = _basename_has(files, tgt_cls)
            if not fp:
                add("error", "call.target.missing", f"method_call target {target}: class {tgt_cls} not found")
            elif tgt_method and not re.search(r"\b%s\s*\(" % re.escape(tgt_method), files[fp]):
                add("error", "call.method.missing", f"method_call {target}: method not defined in {tgt_cls}")

    # ---- Tier A: asset_requirements (creator produces the asset) ----
    for ar in (contract.get("asset_requirements") or []):
        created_by = ar.get("created_by", "")
        path = ar.get("path", "?")
        if created_by:
            base = os.path.basename(created_by)
            cp = _basename_has(files, os.path.splitext(base)[0])
            if cp and ("SaveAsPrefabAsset" not in files[cp] and "CreateAsset" not in files[cp]
                       and os.path.basename(path).split(".")[0] not in files[cp]):
                add("warn", "asset.nocreate", f"asset {path}: {created_by} has no creation code")

    # ---- Tier C: reverse/anti-vacuity ----
    declared_events = {e.get("name") for e in (contract.get("events") or [])}
    for m in re.finditer(r"(?:Publish|Raise)\s*<\s*([A-Za-z_]\w*)", allsrc):
        if m.group(1) not in declared_events:
            add("warn", "drift.event.undeclared", f"code publishes {m.group(1)} not in _CONTRACTS.yaml")

    errors = [f for f in findings if f["severity"] == "error"]
    warns = [f for f in findings if f["severity"] == "warn"]
    status = "pass" if not errors else "violations"
    return {
        "status": status,
        "contract": cpath,
        "errors": len(errors),
        "warnings": len(warns),
        "findings": findings,
        "checked": {"events": len(contract.get("events") or []),
                    "pool_keys": len(contract.get("pool_keys") or []),
                    "serialized_fields": len(contract.get("serialized_fields") or []),
                    "method_calls": len(contract.get("method_calls") or []),
                    "cs_files": len(files)},
    }


def main() -> int:
    # 빌드PC(Windows) 콘솔은 CP949 라 note 의 '—' 같은 문자에서 UnicodeEncodeError 로 죽는다.
    # 계약이 없는 skip 경로가 정확히 그 문자를 찍어, 모든 저장소에서 게이트가 조용히 실패했다(2026-09-14).
    for _st in (sys.stdout, sys.stderr):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--contracts", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(a.repo):
        print(json.dumps({"status": "error", "note": "repo not a dir"}))
        return 3
    res = validate(a.repo, a.contracts)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("ICS %s | errors=%s warnings=%s | contract=%s"
              % (res["status"], res.get("errors", 0), res.get("warnings", 0), res.get("contract", "-")))
        for f in res.get("findings", [])[:30]:
            print("  [%s] %s: %s" % (f["severity"], f["kind"], f["msg"]))
    return 0 if res["status"] in ("pass", "no_contract") else (2 if res["status"] == "violations" else 3)


if __name__ == "__main__":
    sys.exit(main())
