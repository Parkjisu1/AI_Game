#!/usr/bin/env python3
"""
feature_gate — 기능 보존 차단 게이트 (Phase C)

기존 qa-feature-check.mjs 는 기능별 3등급(구조/컴파일/실행) 판정을 내지만,
회귀를 발견해도 Slack 경고 + 리뷰 태스크만 만들고 **아무것도 차단하지 않았다**
([[hermes_quality_gap_audit]] LINK 3). 이 모듈은 그 판정을 **차단(block)** 으로 승격한다.

규칙: severity ∈ {blocker, major} 기능의 structure 또는 compile 판정이 'fail' 이면
      → 게이트 실패(passed=False). 코드 수정 파이프라인이 done 대신 review 로 반려.

structure fail = 필수 기능의 진입점 메서드/경로가 그래프에서 사라짐
              = "이식하면 있던 기능이 없어진다" 의 결정론적 탐지점.

양성 대조군(positive_control): 그래프에 결함(진입 메서드 삭제)을 주입하고
      게이트가 정확히 그 기능을 fail 로 잡는지 확인한다. 게이트가 '상수 초록
      예측기'가 아님을 반복 가능한 테스트로 보증한다(감사가 지적한 미코드화 항목).

CLI:
  python feature_gate.py --project balloonflow                 # 게이트 판정
  python feature_gate.py --project balloonflow --positive-control
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.environ.get("QA_FEATURE_CHECKER", os.path.join(HERE, "graph", "qa-feature-check.mjs"))
PUBLIC_DIR = os.environ.get("NEWPLAY_GRAPH_PUBLIC", "/home/aimed/projecthub-web/public")
CATALOG_DIR = os.environ.get("QA_FEATURE_DIR", os.path.join(HERE, "qa", "features"))
BLOCK_SEVERITIES = ("blocker", "major")


class GateError(Exception):
    pass


def run_checker(project: str, public_dir: str = PUBLIC_DIR, catalog_dir: str = CATALOG_DIR) -> dict:
    """qa-feature-check.mjs 실행 → 해당 public_dir 의 <project>-features.json 파싱."""
    cmd = ["node", CHECKER, "--project", project, "--public", public_dir, "--catalog", catalog_dir]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300, check=False)
    fpath = os.path.join(public_dir, f"{project.lower()}-features.json")
    if not os.path.isfile(fpath):
        raise GateError(f"features.json 미생성 — checker 실패:\n{r.stderr[-500:] or r.stdout[-500:]}")
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate(features_doc: dict, block_severities=BLOCK_SEVERITIES) -> dict:
    """features 문서 → 게이트 판정. 차단 대상 severity의 structure/compile fail 을 위반으로."""
    violations = []
    for feat in features_doc.get("features", []):
        if feat.get("severity") not in block_severities:
            continue
        tiers = feat.get("tiers", {})
        for tier in ("structure", "compile"):
            if (tiers.get(tier) or {}).get("verdict") == "fail":
                violations.append({
                    "id": feat.get("id"),
                    "name": feat.get("name"),
                    "severity": feat.get("severity"),
                    "tier": tier,
                    "evidence": (tiers.get(tier) or {}).get("evidence", ""),
                })
    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "checked": len(features_doc.get("features", [])),
        "block_severities": list(block_severities),
    }


def check_gate(project: str) -> dict:
    """프로덕션 그래프 기준 게이트 판정."""
    doc = run_checker(project)
    verdict = evaluate(doc)
    verdict["project"] = project
    return verdict


def _corrupt_graph(graph_path: str, entry: str) -> bool:
    """entry='Class.Method' 의 메서드를 그래프 노드에서 제거(결함 주입). 성공 시 True."""
    cls, _, method = entry.partition(".")
    with open(graph_path, "r", encoding="utf-8") as f:
        g = json.load(f)
    hit = False
    for node in g.get("nodes", []):
        if node.get("cls") == cls or cls in (node.get("classes") or []):
            methods = node.get("methods") or []
            if method in methods:
                node["methods"] = [m for m in methods if m != method]
                hit = True
    if hit:
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(g, f)
    return hit


def positive_control(project: str) -> dict:
    """
    그래프에 결함을 주입하고 게이트가 그 기능을 정확히 fail 로 잡는지 검증.
    프로덕션을 건드리지 않도록 임시 public 디렉터리에서 수행.
    """
    src_graph = os.path.join(PUBLIC_DIR, f"{project.lower()}-graph.json")
    if not os.path.isfile(src_graph):
        raise GateError(f"그래프 없음: {src_graph}")

    # 기준: 결함 없는 상태에서 게이트 통과 확인
    baseline = check_gate(project)

    tmp = tempfile.mkdtemp(prefix="feature_gate_pc_")
    try:
        tmp_graph = os.path.join(tmp, f"{project.lower()}-graph.json")
        shutil.copy(src_graph, tmp_graph)

        # 첫 blocker 기능의 진입점을 골라 결함 주입
        doc = run_checker(project, public_dir=tmp)
        target = next((x for x in doc.get("features", [])
                       if x.get("severity") == "blocker" and x.get("entry")), None)
        if not target:
            raise GateError("blocker 기능(entry 보유) 없음 — 대조군 불가")
        entry = target["entry"]
        if not _corrupt_graph(tmp_graph, entry):
            raise GateError(f"결함 주입 실패 — entry={entry} 노드/메서드 못 찾음")

        # 결함 그래프로 재판정
        doc2 = run_checker(project, public_dir=tmp)
        verdict = evaluate(doc2)
        caught = any(v["id"] == target["id"] and v["tier"] == "structure" for v in verdict["violations"])

        return {
            "control_passed": bool(baseline["passed"] and not verdict["passed"] and caught),
            "baseline_passed": baseline["passed"],
            "injected": {"feature": target["id"], "entry": entry},
            "gate_blocked_after_injection": not verdict["passed"],
            "caught_target": caught,
            "violations_after": [v["id"] for v in verdict["violations"]],
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--positive-control", action="store_true")
    a = ap.parse_args()
    try:
        if a.positive_control:
            res = positive_control(a.project)
        else:
            res = check_gate(a.project)
    except GateError as e:
        print(f"[gate-error] {e}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    # 게이트 실패 시 non-zero (CI/파이프라인 차단용)
    if not a.positive_control and not res.get("passed"):
        sys.exit(1)
    if a.positive_control and not res.get("control_passed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
