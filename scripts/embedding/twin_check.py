# -*- coding: utf-8 -*-
"""code_base OpenAI embedding 쌍둥이 검사 (2026-10-13, 쓰기 없음).

포크 관계 두 프로젝트(예: Buddyflow ↔ ColorSort)에서 같은 fileId 이고 embed_collection.py 의
임베딩 입력 텍스트(build_text_code)가 완전히 같은 문서 쌍의 embedding 코사인을 잰다.
같은 텍스트를 같은 모델로 임베딩했으면 ≈1.0 이어야 하므로, 낮으면 한쪽 벡터가 낡은 것이다.

사용: python scripts/embedding/twin_check.py <projectA> <projectB> [--threshold 0.99]
"""
import os, sys, math, importlib.util, argparse
ap = argparse.ArgumentParser(); ap.add_argument("a"); ap.add_argument("b"); ap.add_argument("--threshold", type=float, default=0.99)
args = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("embed_collection", os.path.join(HERE, "..", "embed_collection.py"))
ec = importlib.util.module_from_spec(spec)
_argv = sys.argv; sys.argv = [sys.argv[0]]
spec.loader.exec_module(ec)   # 모듈 상단은 env 로드·클라이언트 생성만 한다(키 출력 없음)
sys.argv = _argv
db = ec.db


def cos(x, y):
    return sum(p * q for p, q in zip(x, y)) / math.sqrt(sum(p * p for p in x) * sum(q * q for q in y))


A = {d["fileId"]: d for d in db.code_base.find({"project": args.a})}
B = {d["fileId"]: d for d in db.code_base.find({"project": args.b})}
pairs = []
for fid in sorted(set(A) & set(B)):
    a, b = A[fid], B[fid]
    if "embedding" not in a or "embedding" not in b: continue
    if ec.build_text_code(a) != ec.build_text_code(b): continue
    pairs.append((cos(a["embedding"], b["embedding"]), fid, str(a.get("embedded_at", ""))[:10], str(b.get("embedded_at", ""))[:10]))
pairs.sort()
low = [p for p in pairs if p[0] < args.threshold]
print(f"{args.a} vs {args.b}: identical-text pairs={len(pairs)} min={pairs[0][0]:.4f} below {args.threshold}={len(low)}" if pairs else "no identical-text pairs")
for s, fid, ea, eb in low[:10]:
    print(f"  {s:.4f} {fid}  embedded {args.a}:{ea} {args.b}:{eb}")
