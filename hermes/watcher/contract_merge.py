# -*- coding: utf-8 -*-
"""기획서(.md)의 ```yaml 블록을 추출해 _CONTRACTS.yaml 로 병합한다.

명세 01 §9.3 이 "아래 블록을 그대로 _CONTRACTS.yaml 의 각 최상위 키 아래에 append 한다 (Lead가 병합)"
라고 지시하는 그 병합 단계. 설계돼 있었으나 아무도 실행하지 않아 5개 저장소 모두 계약 파일이 0개였다.

사용: python contract_merge.py <docs_dir> <out.yaml> [--project NAME]
"""
import io, os, re, sys, json

CONTRACT_KEYS = ("events", "pool_keys", "serialized_fields", "method_calls", "asset_requirements")


def extract_yaml_blocks(md_text: str):
    """```yaml ... ``` 블록만 뽑는다. 계약 키를 하나라도 포함한 블록만 대상."""
    out = []
    for m in re.finditer(r"```yaml\s*\n(.*?)```", md_text, re.S):
        body = m.group(1)
        if any(re.search(rf"^\s*{k}\s*:", body, re.M) for k in CONTRACT_KEYS):
            out.append(body)
    return out


def parse_block(block: str):
    """최상위 계약 키별로 '- ' 항목 덩어리를 원문 그대로 모은다.

    PyYAML 없이 동작해야 한다(Mother venv 의존 최소화). 계약 블록은 구조가 단순해
    들여쓰기 기준 분할로 충분하며, 원문을 보존하는 편이 주석·서식 손실이 없다.
    """
    buckets = {k: [] for k in CONTRACT_KEYS}
    cur = None
    item = []
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            if cur and item:
                item.append(line)
            continue
        top = re.match(r"^([a-z_]+)\s*:\s*$", line)
        if top and top.group(1) in CONTRACT_KEYS:
            if cur and item:
                buckets[cur].append("\n".join(item).rstrip())
                item = []
            cur = top.group(1)
            continue
        if re.match(r"^[a-zA-Z_]", line):        # 다른 최상위 키 → 계약 구간 종료
            if cur and item:
                buckets[cur].append("\n".join(item).rstrip())
                item = []
            cur = None
            continue
        if cur is None:
            continue
        if re.match(r"^\s{0,4}- ", line):         # 새 항목 시작
            if item:
                buckets[cur].append("\n".join(item).rstrip())
            item = [line]
        elif item:
            item.append(line)
    if cur and item:
        buckets[cur].append("\n".join(item).rstrip())
    return buckets


def item_id(text: str):
    """중복 판정 키 — name / class+field / caller+target / key / path 중 있는 것."""
    def g(p):
        m = re.search(p, text, re.M)
        return m.group(1).strip() if m else ""
    for pat in (r"^\s*-?\s*name:\s*(.+)$", r"^\s*-?\s*key:\s*(.+)$", r"^\s*-?\s*path:\s*(.+)$"):
        v = g(pat)
        if v:
            return v
    cls, fld = g(r"^\s*-?\s*class:\s*(.+)$"), g(r"^\s*field:\s*(.+)$")
    if cls:
        return f"{cls}.{fld}"
    cal, tgt = g(r"^\s*-?\s*caller:\s*(.+)$"), g(r"^\s*target:\s*(.+)$")
    if cal:
        return f"{cal}->{tgt}"
    return text[:60]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    docs_dir, out_path = sys.argv[1], sys.argv[2]
    project = "Unknown"
    if "--project" in sys.argv:
        project = sys.argv[sys.argv.index("--project") + 1]

    merged = {k: [] for k in CONTRACT_KEYS}
    seen = {k: set() for k in CONTRACT_KEYS}
    dupes, per_doc = [], []

    for fn in sorted(os.listdir(docs_dir)):
        if not fn.endswith(".md"):
            continue
        text = io.open(os.path.join(docs_dir, fn), encoding="utf-8").read()
        n_doc = 0
        for block in extract_yaml_blocks(text):
            for key, items in parse_block(block).items():
                for it in items:
                    iid = item_id(it)
                    if iid in seen[key]:
                        dupes.append(f"{key}/{iid} ({fn})")
                        continue
                    seen[key].add(iid)
                    merged[key].append((it, fn))
                    n_doc += 1
        if n_doc:
            per_doc.append((fn, n_doc))

    lines = [
        f'project: "{project}"',
        "version: 1",
        "# 자동 생성 — 기획서의 YAML 계약 블록을 병합한 것. 원본 문서를 고치고 이 스크립트를 다시 돌린다.",
        "# 명세 01 §9.3 'Lead가 병합' 단계의 기계 구현.",
        "",
    ]
    total = 0
    for key in CONTRACT_KEYS:
        lines.append(f"{key}:")
        if not merged[key]:
            lines.append("  []")
        for it, src in merged[key]:
            lines.append(f"  # ← {src}")
            for ln in it.split("\n"):
                lines.append(("  " + ln) if ln.strip() else "")
            total += 1
        lines.append("")

    io.open(out_path, "w", encoding="utf-8").write("\n".join(lines))

    print(f"=== _CONTRACTS.yaml 생성: {out_path}")
    print(f"    총 계약 항목 {total}개")
    for k in CONTRACT_KEYS:
        print(f"      {k:22} {len(merged[k])}")
    print(f"    기여 문서: " + ", ".join(f"{f}({n})" for f, n in per_doc))
    if dupes:
        print(f"    중복 제거 {len(dupes)}건: " + ", ".join(dupes[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
