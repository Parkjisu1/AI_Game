"""build_similar_tasks_block을 good-result(best_score>=80)만 참조하도록 패치. 멱등."""
P = "/home/aimed/.hermes/watcher/hermes_atlas_retrieval.py"
src = open(P, encoding="utf-8").read()

old = '''    rows = _vector_search("pixelforge_tasks", qvec, k + 4)
    rows = [r for r in rows if str(r.get("_id")) != exclude_id and r.get("_score", 0) >= TASK_SIM_FLOOR][:k]'''
new = '''    rows = _vector_search("pixelforge_tasks", qvec, k + 12)  # good 필터 보정 위해 넓게
    # 결과가 좋았던 작업만 참조 (best_score = reviewer max). 검증된 우수 사례만 RAG 주입.
    GOOD = 80.0
    rows = [r for r in rows
            if str(r.get("_id")) != exclude_id
            and r.get("_score", 0) >= TASK_SIM_FLOOR
            and float(r.get("best_score") or 0) >= GOOD][:k]'''

if new.split("\\n")[0] in src or "best_score" in src:
    print("이미 패치됨(스킵)")
elif old in src:
    src = src.replace(old, new, 1)
    open(P, "w", encoding="utf-8").write(src)
    import ast
    ast.parse(src)
    print("패치 완료 · 문법 OK")
else:
    print("앵커 미발견(확인필요)")
