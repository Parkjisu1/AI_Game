"""art + design(content) 파이프라인에 validator 게이트 삽입 (reviewer 직전, advisory·비차단). 멱등."""
P = "/home/aimed/.hermes/watcher/hermes_executor.py"
src = open(P, encoding="utf-8").read()

# ── 1) ART validator (이미지 규격 게이트) ──
art_anchor = "    reviewer_prompt = ART_REVIEWER_TEMPLATE.format(\n        title=title,"
art_block = '''    # ── Step 2.5: art_validator (규격 게이트 — reviewer 전 2-게이트) [granular_v1]
    _art_val_role = resolve_role("art", art_sub_team, "validator")
    if _art_val_role not in {"validator", "art_reviewer", "reviewer"}:
        _av_prompt = (
            f"아트 산출물 규격 검증(품질평가 아닌 정합검증). 태스크: {title}\\n"
            f"image_prompt: {image_prompt}\\n이미지: {first_image_path or '(경로없음)'}\\n"
            "①요청 사이즈/비율 ②투명배경(요청시) ③9-slice 규칙(해당시 균일내부/테두리장식) "
            "④팔레트/색수 ⑤피사체 잘림/씬화 여부 를 각 OK/WARN/FAIL로. "
            "JSON으로 {verdict: ok|revise|fail, quality_score: 0-100, notes: str}."
        )
        _av_prev = getattr(env, "image_path", None)
        env.image_path = first_image_path or None
        try:
            _avr = invoke_agent(_art_val_role, _av_prompt, env)
        finally:
            env.image_path = _av_prev
        if _avr.success:
            _avs = _avr.structured or {}
            _avv = (_avs.get("verdict") or "ok").lower()
            try:
                _avsc = int(_avs.get("quality_score")) if _avs.get("quality_score") is not None else 70
            except (TypeError, ValueError):
                _avsc = 70
            _comment(f"\\U0001F50D **{_art_val_role}** 규격검증: `{_avv}` — {(_avs.get('notes') or '')[:180]}")
            _record_quality_score(task_id=task_id, team="art", sub_team=art_sub_team,
                                  role=_art_val_role, score=_avsc, verdict=_avv,
                                  summary=(_avs.get('notes') or '')[:300])

'''

# ── 2) DESIGN(content) validator (문서 정합 게이트) ──
des_anchor = "    # ── Step 3: Reviewer — 4축 평가\n"
des_block = '''    # ── Step 2.5: design validator (스키마/계약/밸런스 정합 게이트) [granular_v1]
    _des_sub = (task.get("sub_team") or "content")
    _des_val_role = resolve_role("design", _des_sub, "validator")
    if _des_val_role not in {"validator", "reviewer"}:
        _dv_env = ExecutionEnv(mode="local", cwd=str(Path.home()), timeout_sec=120,
                               task_id=task_id, task_title=title, team="design", sub_team=_des_sub)
        _dv_prompt = (
            f"기획 문서 정합 검증(품질평가 아닌 스키마/계약/밸런스 검증). 태스크: {title}\\n"
            f"=== 문서 ===\\n{md_text[:6000]}\\n=== 끝 ===\\n"
            "①필수 섹션/스키마 ②수치 근거(공식/DB) ③계약/교차참조 일관성 ④밸런스 명백한 오류 "
            "를 각 OK/WARN/FAIL로. JSON {verdict: ok|revise|fail, quality_score: 0-100, notes: str}."
        )
        _dvr = invoke_agent(_des_val_role, _dv_prompt, _dv_env)
        if _dvr.success:
            _dvs = _dvr.structured or {}
            _dvv = (_dvs.get("verdict") or "ok").lower()
            try:
                _dvsc = int(_dvs.get("quality_score")) if _dvs.get("quality_score") is not None else 70
            except (TypeError, ValueError):
                _dvsc = 70
            _comment(f"\\U0001F50D **{_des_val_role}** 정합검증: `{_dvv}` — {(_dvs.get('notes') or '')[:180]}")
            _record_quality_score(task_id=task_id, team="design", sub_team=_des_sub,
                                  role=_des_val_role, score=_dvsc, verdict=_dvv,
                                  summary=(_dvs.get('notes') or '')[:300])

'''


def insert(anchor, block, s, name):
    if block.strip().splitlines()[0] in s:
        print(f"  {name}: 이미 삽입됨(스킵)")
        return s
    if anchor not in s:
        print(f"  {name}: 앵커 미발견(확인필요)")
        return s
    print(f"  {name}: 삽입")
    return s.replace(anchor, block + anchor, 1)


src = insert(art_anchor, art_block, src, "art_validator")
src = insert(des_anchor, des_block, src, "design_validator")
open(P, "w", encoding="utf-8").write(src)
import ast
ast.parse(src)
print("문법 OK · 패치 완료")
