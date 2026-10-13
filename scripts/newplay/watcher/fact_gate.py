"""fact_gate.py — 산출물의 **기계로 판정 가능한 주장**을 LLM 없이 검증한다.

왜 필요한가 (2026-08-05 실측):
    검수에서 나온 지적을 성격별로 나눠 보니 대부분이 기계로 10ms 안에 판정 가능한 것이었다.
      - 인용 줄번호 오류 3건 (`PgPaymentToss.tsx:130` 은 빈 줄, 실제 코드는 134)
      - git apply 가 안 되는 잘린 패치 (claude-sonnet-5 는 이걸 approve 했다)
      - "razer 라벨 44개" (실제 42개)
      - "저작권 문자열은 이 한 곳뿐" (실제 11곳 이상)
    그런데 전부 178초짜리 LLM 검수에 맡기고 있었다. 그래서 놓치기도 하고,
    잡더라도 판단에 써야 할 시간을 파일 대조에 쓴다.

이 모듈이 하는 일 / 하지 않는 일:
    한다   — 사실을 **해소**한다. 패치가 붙는지 시도해 보고, 인용한 줄을 실제로 열어 보여준다.
    안 한다 — 좋고 나쁨을 판단하지 않는다. 그건 검수자(LLM)의 몫이다.
    "가서 확인해라" 를 "여기 있다" 로 바꾸는 게 목적이다.

읽는 대상:
    `~/newplay-verify` — 검증 전용 worktree.
    미리보기 빌드가 쓰는 `~/newplay-preview/webstore` 를 그대로 읽으면
    빌드가 `git checkout` + `git clean -fd` 를 도는 동안 트리가 바뀐다. 그래서 분리했다.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

REPO = os.environ.get("NEWPLAY_VERIFY_REPO", os.path.expanduser("~/newplay-verify"))

#: 인용으로 인정할 확장자. 넓히면 `1.0.0:1` 같은 버전 표기가 걸린다.
_EXT = r"(?:ts|tsx|js|jsx|mjs|cjs|json|md|ya?ml|html|css|scss)"

#: `path/to/file.ts:123` 또는 `file.ts:123-145`
_CITE = re.compile(r"(?<![\w/])((?:[\w.\-]+/)*[\w.\-]+\." + _EXT + r"):(\d+)(?:\s*[-~]\s*(\d+))?")

#: 인용 상한. 산출물 하나가 50개를 인용하면 표가 본문을 덮는다.
MAX_CITATIONS = 24


@lru_cache(maxsize=1)
def _index() -> dict[str, list[str]]:
    """basename → 실제 경로 목록. 산출물이 짧은 이름만 쓰는 경우가 많아 필요하다."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                             text=True, timeout=60)
        if out.returncode != 0:
            return {}
        idx: dict[str, list[str]] = {}
        for p in out.stdout.splitlines():
            p = p.strip()
            if not p:
                continue
            idx.setdefault(p, []).append(p)              # 전체 경로로도 찾을 수 있게
            idx.setdefault(p.split("/")[-1], []).append(p)
        return idx
    except Exception as e:  # noqa: BLE001
        log.warning("파일 인덱스 실패: %s: %s", type(e).__name__, e)
        return {}


def _resolve(path: str, context: frozenset[str] = frozenset()) -> tuple[str, str]:
    """인용 경로를 실제 경로로. (상태, 경로) 를 돌려준다.

    context 는 **같은 문서 안에서 이미 완전 경로로 등장한 파일들**이다.
    산출물은 처음엔 `front-end/src/utils/constants.ts:255` 라 쓰고
    그 뒤로는 `constants.ts:262` 로 줄여 쓰는 일이 흔하다(실측: 9건 중 5건).
    문서 자신의 문맥으로 풀면 모호가 대부분 사라진다.
    """
    p = path.strip().lstrip("./")
    if p.startswith("a/") or p.startswith("b/"):        # diff 헤더 접두사
        p = p[2:]
    if "..." in p:                                      # `1782622111005-...ts` 같은 축약
        return "abbreviated", p
    idx = _index()
    if p in idx and p in idx[p]:
        return "ok", p
    # 접미사 일치를 **먼저** 본다.
    # 파일명만으로 찾으면 `public/newplay/index.html` 처럼 디렉토리까지 쓴 정확한 인용이
    # index.html 전부와 매칭돼 모호로 빠진다(실측: 못 푼 인용 4건 중 3건이 이 이유였다).
    # 더 구체적인 단서를 먼저 쓰는 게 맞다.
    cands: list[str] = []
    if "/" in p:
        tail = "/" + p
        cands = sorted({f for v in idx.values() for f in v if f.endswith(tail)})
    if not cands:
        cands = sorted(set(idx.get(p) or idx.get(p.split("/")[-1]) or []))
    if not cands:
        return "no_file", p
    if len(cands) > 1:
        # 1순위: 같은 문서가 완전 경로로 언급한 것
        narrowed = [c for c in cands if c in context]
        # 2순위: 문맥에 나온 파일과 같은 디렉토리
        if not narrowed:
            dirs = {c.rsplit("/", 1)[0] for c in context if "/" in c}
            narrowed = [c for c in cands if c.rsplit("/", 1)[0] in dirs]
        if len(narrowed) == 1:
            return "ok", narrowed[0]
        return "ambiguous", " | ".join(cands[:4])
    return "ok", cands[0]


def _candidates(path: str) -> list[str]:
    """그 인용이 가리킬 수 있는 실제 파일들. 확정 판정 전에 후보 전체를 봐야 할 때 쓴다."""
    p = path.strip().lstrip("./")
    if p.startswith(("a/", "b/")):
        p = p[2:]
    idx = _index()
    if "/" in p:
        tail = "/" + p
        c = sorted({f for v in idx.values() for f in v if f.endswith(tail)})
        if c:
            return c
    return sorted(set(idx.get(p) or idx.get(p.split("/")[-1]) or []))


def _doc_context(text: str) -> frozenset[str]:
    """문서 안에서 완전 경로로 등장해 실재가 확인된 파일들."""
    idx = _index()
    out = set()
    for m in _CITE.finditer(text):
        p = m.group(1).lstrip("./")
        if p.startswith(("a/", "b/")):
            p = p[2:]
        if "/" in p and p in idx and p in idx[p]:
            out.add(p)
    return frozenset(out)


@lru_cache(maxsize=512)
def _lines(path: str) -> list[str]:
    try:
        with open(os.path.join(REPO, path), encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except Exception:  # noqa: BLE001
        return []


def check_citations(text: str) -> list[dict[str, Any]]:
    """인용한 file:line 을 실제로 열어 그 줄에 무엇이 있는지 돌려준다.

    맞다/틀리다를 판정하지 않는다 — 주장과 실제를 나란히 놓아 줄 뿐이다.
    판정에는 "그 줄이 무슨 내용이어야 하는가"가 필요한데 그건 자연어라 기계가 모른다.
    """
    ctx = _doc_context(text)
    seen: set[tuple[str, int]] = set()
    out: list[dict[str, Any]] = []
    for m in _CITE.finditer(text):
        raw_path, s_line = m.group(1), int(m.group(2))
        if (raw_path, s_line) in seen:
            continue
        seen.add((raw_path, s_line))
        status, path = _resolve(raw_path, ctx)
        row: dict[str, Any] = {"cited": f"{raw_path}:{s_line}", "status": status, "path": path}
        if status == "ok":
            ls = _lines(path)
            if not ls:
                row["status"] = "unreadable"
            elif s_line < 1 or s_line > len(ls):
                # 같은 이름의 다른 파일이면 줄이 있을 수 있다.
                # 실측: `index.html:1735` 는 문맥상 newplay/index.html(1,738줄)인데
                # 해소기가 developers/index.html(1,065줄)을 골라 "범위 초과"라 단정했다.
                # **틀린 사실은 없는 사실보다 나쁘다** — 확정할 수 없으면 모호로 둔다.
                alts = [c for c in _candidates(raw_path)
                        if c != path and 0 < s_line <= len(_lines(c))]
                if alts:
                    row["status"] = "ambiguous"
                    row["path"] = " | ".join([path, *alts][:4])
                    row["actual"] = (f"`{path}` 은 {len(ls)}줄뿐이라 이 줄이 없다. "
                                     f"같은 이름의 다른 파일에는 있다 — 전체 경로로 써야 확인할 수 있다")
                else:
                    row["status"] = "out_of_range"
                    row["actual"] = f"(파일은 {len(ls)}줄)"
            else:
                row["actual"] = ls[s_line - 1].strip()[:140] or "(빈 줄)"
        out.append(row)
        if len(out) >= MAX_CITATIONS:
            break
    return out


def _extract_patches(text: str) -> list[str]:
    """산출물에서 패치 블록을 뽑는다.

    파이프라인이 실제로 적용하는 것과 **같은 것**을 검사해야 의미가 있으므로
    hermes_executor 의 추출기를 그대로 쓴다(순환 import 를 피해 함수 안에서 import).
    """
    try:
        from hermes_executor import _extract_patch
        patch, _files = _extract_patch(text)
        return [patch] if patch else []
    except Exception as e:  # noqa: BLE001
        log.warning("패치 추출 실패: %s: %s", type(e).__name__, e)
        return []


def check_patches(text: str) -> list[dict[str, Any]]:
    """패치가 실제로 붙는지 `git apply --check` 로 시도한다.

    두 번 시도하는 이유:
      plain     — 헝크 헤더까지 정확한가
      --recount — 헤더 줄 수만 틀린 건가 (LLM 이 자주 틀린다. 미리보기 빌드도 --recount 를 쓴다)
    plain 실패 + recount 성공 = 고칠 수 있는 흠.  둘 다 실패 = 내용 자체가 안 맞는다(잘림 등).
    """
    rows: list[dict[str, Any]] = []
    patches = _extract_patches(text)

    # 펜스 균형은 **추출 성공 여부와 무관하게** 본다.
    # 추출기는 닫힌 블록만 이어 붙이므로, 블록 하나가 정상이고 뒤엣것이 잘리면
    # "패치 1건 · 정상" 으로 보고되고 잘린 부분은 조용히 사라진다.
    # 실측(2026-08-05 재작업 검증): 백엔드 훅과 테스트 헝크가 그렇게 사라졌는데
    # 산출물은 "둘 다 온전히 포함했다" 고 단언했다. 게이트는 그걸 못 봤다.
    fenced = text.count("```diff")
    closed = len(re.findall(r"```diff\s*\n.*?```", text, re.S))
    if patches and fenced > closed:
        rows.append({
            "index": -1, "bytes": 0, "plain": False, "recount": False,
            "extracted": False, "kind": "truncated",
            "error": [f"diff 블록 {fenced}개 중 {closed}개만 닫혀 있다 — "
                      f"닫히지 않은 {fenced - closed}개는 **통째로 버려졌다**. "
                      "아래 '적용 가능' 판정은 살아남은 블록에 대한 것일 뿐이다"],
        })

    # 패치를 냈다고 하는데 뽑히지 않는 경우 — 이게 가장 위험하다.
    # 추출기는 형식이 어긋나면 조용히 버리므로(닫는 ``` 없음 등) 아무 일도 없던 것처럼 보인다.
    # 실측: 헝크 중간에서 잘린 패치를 claude-sonnet-5 가 approve 했다.
    # 기계는 "붙는다/안 붙는다" 를 확실히 알 수 있는데 문장 읽기로 판정하게 두면 안 된다.
    if not patches:
        claimed = re.search(r"```\s*diff|^diff --git |^--- a/", text, re.M)
        if claimed:
            fenced = text.count("```diff")
            closed = len(re.findall(r"```diff\s*\n.*?```", text, re.S))
            # 두 경우를 가른다. 성격이 다르고, 검수자가 다르게 판단해야 한다.
            #   truncated   — 출력이 깨졌다. 확실한 결함이다.
            #   illustrative— 설명용 diff 만 있고 적용 가능한 패치가 없다.
            #                 요구사항 미이행이긴 하나, 조사성 태스크라면 타당할 수 있어
            #                 하드 실패로 세지 않고 검수자 판단에 맡긴다.
            if fenced > closed:
                kind = "truncated"
                why = f"코드블록이 닫히지 않았다 (```diff {fenced}개 중 닫힌 것 {closed}개) — 출력이 잘렸다"
            elif "diff --git" not in text or "@@" not in text:
                kind = "illustrative"
                missing = "`diff --git` 헤더" if "diff --git" not in text else "`@@` 헝크 헤더"
                why = (f"{missing}가 없어 설명용 diff 로만 보인다 — "
                       "`git apply` 로 적용할 수 있는 패치가 없다")
            else:
                kind = "malformed"
                why = "형식이 어긋나 추출되지 않는다"
            rows.append({"index": 0, "bytes": 0, "plain": False, "recount": False,
                         "extracted": False, "kind": kind, "error": [why]})
        return rows

    for i, patch in enumerate(patches):
        row: dict[str, Any] = {"index": i, "bytes": len(patch)}
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False,
                                         encoding="utf-8") as f:
            f.write(patch if patch.endswith("\n") else patch + "\n")
            pf = f.name
        try:
            for label, extra in (("plain", []), ("recount", ["--recount"])):
                r = subprocess.run(["git", "apply", "--check", *extra, pf],
                                   cwd=REPO, capture_output=True, text=True, timeout=60)
                row[label] = (r.returncode == 0)
                if r.returncode != 0 and "error" not in row:
                    row["error"] = (r.stderr or "").strip().splitlines()[:3]
        except Exception as e:  # noqa: BLE001
            row["plain"] = row["recount"] = False
            row["error"] = [f"{type(e).__name__}: {e}"]
        finally:
            try:
                os.unlink(pf)
            except OSError:
                pass
        rows.append(row)
    return rows


#: 게이트가 재실행해 줄 검색 도구. 다른 건 절대 실행하지 않는다.
_ALLOWED_CMDS = {"grep", "rg", "git"}
#: git 은 서브커맨드가 위험할 수 있어 grep 만 허용한다.
_ALLOWED_GIT_SUB = {"grep"}
#: **파싱된 토큰**으로 존재할 때만 셸 문법이다.
#: 따옴표 안의 `\|` (grep 의 BRE 교체)는 셸이 개입하지 않으므로 안전하다 —
#: 원시 문자열을 검사하면 정상적인 grep 을 전부 거부하게 된다(실측: 5개 명령 전부 거부됐다).
_SHELL_TOKENS = {"|", "||", "&", "&&", ";", ">", ">>", "<", "2>", "$(", "`"}
MAX_SEARCHES = 5


def _vet(cmd: str) -> str:
    """실행해도 되는 검색 명령인지 본다. 거부 사유를 돌려주고, 괜찮으면 빈 문자열.

    무엇이 실제 방어인가:
      셸을 쓰지 않으므로(`shell=False`) 파이프·리다이렉트는 **해석되지 않는다** —
      그냥 grep 의 인자가 될 뿐이라 위험하지 않다. 그래서 원시 문자열에서
      메타문자를 찾는 방식은 방어가 아니라 오탐 생산기였다
      (실측: `grep "a\\|b"` 같은 정상 명령 5개를 전부 거부했다).
      진짜 방어는 셋이다 — 실행 파일 화이트리스트, 작업 디렉토리 고정, 트리 밖 접근 차단.
    """
    import shlex
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return "명령을 해석할 수 없다"
    if not argv:
        return "빈 명령"
    if argv[0] not in _ALLOWED_CMDS:
        return f"허용되지 않은 명령: {argv[0]} (검색 도구만 실행한다)"
    if argv[0] == "git" and (len(argv) < 2 or argv[1] not in _ALLOWED_GIT_SUB):
        return "git 은 `git grep` 만 실행한다"
    # 셸 문법이 **토큰으로** 남아 있으면 여러 명령을 이으려 한 것이다.
    # 우리는 첫 명령만 실행하므로 뒤는 조용히 무시되는데, 그러면 결과가 오해를 부른다.
    bad = [a for a in argv[1:] if a in _SHELL_TOKENS]
    if bad:
        return f"파이프·리다이렉트는 실행되지 않는다 ({bad[0]}) — 명령 하나씩 적을 것"
    # 검증 트리 밖은 읽지 않는다.
    for a in argv[1:]:
        if a.startswith("/") or a.startswith("~"):
            return f"절대 경로는 허용하지 않는다 ({a[:40]}) — 레포 루트 기준 상대 경로로 쓸 것"
        if ".." in a.split("/"):
            return f"상위 경로 참조는 허용하지 않는다 ({a[:40]})"
    return ""


def check_searches(text: str) -> list[dict[str, Any]]:
    """산출물이 근거로 제시한 검색 명령을 **실제로 다시 돌린다**.

    왜 이 방식인가:
        "코드베이스 전체에 이 문자열은 이 한 곳뿐" 같은 전칭 주장이 이 시스템의
        가장 비싼 오류였다(실측: 실제로는 19곳). 그런데 자연어로 쓰인 단정을
        기계가 검증하려면 "무엇을 어디서 찾았다는 건지" 를 알아야 한다.
        그래서 **주장 대신 명령을 요구**한다. 명령은 재현 가능하다.
        부수 효과가 더 크다 — 명령을 적어야 하니 코더가 실제로 찾아보게 된다.

    안전:
        셸을 쓰지 않고(shell=False) argv 로 실행하며, 첫 토큰이 검색 도구가 아니면 거부한다.
        셸 메타문자가 섞이면 실행하지 않는다. 작업 디렉토리는 검증 전용 트리다.
    """
    m = re.search(r"##\s*전수\s*조사\s*\n(.*?)(?:\n##\s|\Z)", text, re.S)
    if not m:
        return []
    rows: list[dict[str, Any]] = []
    for block in re.findall(r"```(?:bash|sh)?\s*\n(.*?)```", m.group(1), re.S):
        for line in block.splitlines():
            cmd = line.strip()
            if not cmd or cmd.startswith("#"):
                continue
            row: dict[str, Any] = {"cmd": cmd[:200]}
            reject = _vet(cmd)
            if reject:
                row["status"], row["note"] = "rejected", reject
            else:
                import shlex
                argv = shlex.split(cmd)
                # 바이너리 파일은 세지 않는다.
                # grep 은 기본적으로 바이너리도 훑어서 `©` 같은 바이트열이 이미지에서 걸린다 —
                # 실측: `grep -rln "…\\|©" front-end/public` 이 34건을 냈는데
                # 그중 15건이 png/webp 였다. 그 숫자로 "산출물이 19라 했는데 34다" 라고
                # 판단하면 **게이트가 없는 불일치를 만들어낸다.** 틀린 사실이 가장 나쁘다.
                # (rg 는 기본이 바이너리 무시라 손대지 않는다)
                if argv[0] == "grep" and not any(a == "-I" for a in argv):
                    argv = [argv[0], "-I", *argv[1:]]
                    row["note"] = "바이너리 파일 제외(`-I`)하고 실행했다"
                try:
                    r = subprocess.run(argv, cwd=REPO, capture_output=True,
                                       text=True, timeout=30)
                    lines = [x for x in r.stdout.splitlines() if x.strip()]
                    row["status"] = "ran"
                    row["hits"] = len(lines)
                    row["sample"] = lines[:6]
                    if r.returncode not in (0, 1):
                        row["note"] = (r.stderr or "").strip()[:160] or row.get("note", "")
                except Exception as e:  # noqa: BLE001
                    row["status"] = "error"
                    row["note"] = f"{type(e).__name__}: {e}"[:160]
            rows.append(row)
            if len(rows) >= MAX_SEARCHES:
                return rows
    return rows


def check_claimed_files(text: str) -> dict[str, Any]:
    """"고침" 이라고 표시한 파일이 실제 패치에 들어 있는지 대조한다.

    왜 (실측 2026-08-05 재작업 검증):
        재작업 산출물이 영향 범위 표에서 backend 파일 2개를 **고침** 으로 표시하고
        "이번 패치에 훅 둘 다 온전히 포함했다" 고 단언했는데,
        첨부된 diff 에는 backend 가 **한 줄도 없었다.**
        패치 자체는 `git apply` 가 되므로 게이트는 "정상" 이라 했다 —
        붙는가와 약속한 것이 들어 있는가는 다른 질문이다.

    이건 순수하게 기계적이다. 표에 쓴 경로와 diff 의 `+++ b/` 목록을 맞춰 보면 끝난다.
    """
    m = re.search(r"##\s*영향\s*범위\s*\n(.*?)(?:\n##\s|\Z)", text, re.S)
    if not m:
        return {}
    claimed: list[str] = []
    for row in m.group(1).splitlines():
        # `**고침**` 만. `**안 고침**` 은 사이에 '안 ' 이 있어 매칭되지 않는다.
        if not re.search(r"\*\*고침\*\*", row):
            continue
        for p in re.findall(r"`([\w./-]+\." + _EXT + r")(?::\d+[\d,\s~-]*)?`", row):
            st, resolved = _resolve(p, _doc_context(text))
            claimed.append(resolved if st == "ok" else p)
    if not claimed:
        return {}

    _patch = _extract_patches(text)
    in_patch: set[str] = set()
    for p in _patch:
        in_patch |= set(re.findall(r"^\+\+\+ b/(.+)$", p, re.M))

    missing = [c for c in dict.fromkeys(claimed)
               if not any(f == c or f.endswith("/" + c.split("/")[-1]) for f in in_patch)]
    return {"claimed": list(dict.fromkeys(claimed)), "in_patch": sorted(in_patch),
            "missing": missing}


def check(text: str) -> dict[str, Any]:
    """산출물 하나에 대한 기계 검증 결과."""
    cites = check_citations(text)
    patches = check_patches(text)
    searches = check_searches(text)
    claims = check_claimed_files(text)
    bad_cites = [c for c in cites if c["status"] != "ok"]
    bad_patches = [p for p in patches if not p.get("recount")]
    # 설명용 diff 만 있는 건 요구사항 미이행이지 "깨진 출력" 은 아니다 — 판단은 검수자 몫.
    hard_patches = [p for p in bad_patches if p.get("kind") != "illustrative"]
    return {
        "citations": cites,
        "patches": patches,
        "searches": searches,
        "claims": claims,
        "bad_citations": len(bad_cites),
        "bad_patches": len(bad_patches),
        # 하드 실패 = 패치가 아예 안 붙거나, 없는 파일을 인용했다.
        # 줄 내용이 다른 건 판단이 필요하므로 여기서 실패로 세지 않는다.
        # "고침" 이라 해놓고 패치에 없는 파일은 하드 실패다 — 약속과 산출물이 어긋난 것이라
        # 판단의 여지가 없다.
        "hard_failures": (len(hard_patches)
                          + len(claims.get("missing") or [])
                          + sum(1 for c in bad_cites
                                if c["status"] in ("no_file", "out_of_range"))),
        "repo_rev": _rev(),
        "repo_date": _rev_date(),
    }


@lru_cache(maxsize=1)
def _rev() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else "?"
    except Exception:  # noqa: BLE001
        return "?"


@lru_cache(maxsize=1)
def _rev_date() -> str:
    """검증 대상 스냅샷의 날짜.

    이 호스트는 GitHub 자격이 없어 fetch 가 안 된다(디플로이 키 미등록).
    즉 레포는 **떠 온 시점의 스냅샷**이고, 그 뒤 main 이 움직였다면
    게이트가 내놓는 '사실' 이 낡을 수 있다. 그래서 날짜를 항상 같이 보여준다 —
    틀린 사실을 사실처럼 내미는 것이 아무것도 안 내미는 것보다 나쁘다.
    """
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=short"], cwd=REPO,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else "?"
    except Exception:  # noqa: BLE001
        return "?"


def as_prompt_block(res: dict[str, Any]) -> str:
    """검수자에게 넘길 블록. 사실만 담고 판정은 하지 않는다."""
    cites = res.get("citations") or []
    patches = res.get("patches") or []
    searches = res.get("searches") or []
    claims = res.get("claims") or {}
    if not cites and not patches and not searches and not claims:
        return ""
    L = [f"## 기계 검증 결과 (레포 `{res.get('repo_rev')}` · {res.get('repo_date')} 스냅샷)",
         "",
         "아래는 추측이 아니라 파일을 실제로 열고 패치를 실제로 적용해 본 결과다.",
         "**이 표와 어긋나는 서술이 산출물에 있으면 그것이 오류다.**",
         f"단, 검증 대상은 {res.get('repo_date')} 시점 스냅샷이다 — "
         "그 이후 원격에서 바뀐 부분은 이 표가 알지 못한다.",
         ""]

    if patches:
        L.append("### 패치 적용")
        for p in patches:
            if p.get("extracted") is False:
                why = "; ".join(p.get("error") or ["원인 불명"])
                if p.get("kind") == "illustrative":
                    L.append(f"- 적용 가능한 패치 없음 — {why}. "
                             "(조사성 태스크라면 타당할 수 있다 — 판단은 검수자 몫이다)")
                else:
                    L.append(f"- **패치가 깨져 있다** — {why}. 이 상태로는 아무 데도 적용되지 않는다.")
                continue
            if p.get("plain"):
                v = "적용 가능"
            elif p.get("recount"):
                v = "적용 가능 (단 헝크 헤더 줄 수가 틀려 `--recount` 필요)"
            else:
                v = "**적용 불가** — " + "; ".join(p.get("error") or ["원인 불명"])
            L.append(f"- 패치 {p['index'] + 1} ({p['bytes']}바이트): {v}")
        L.append("")

    if claims.get("claimed"):
        L.append("### '고침' 이라 표시한 파일 vs 실제 패치에 든 파일")
        miss = claims.get("missing") or []
        if miss:
            L.append("")
            L.append("**아래 파일은 영향 범위 표에서 '고침' 이라 했는데 패치에 없다:**")
            for f in miss:
                L.append(f"- `{f}`")
            L.append("")
            L.append("패치가 `git apply` 되는 것과 약속한 변경이 들어 있는 것은 다른 문제다.")
        else:
            L.append("- '고침' 으로 표시한 파일이 모두 패치에 들어 있다.")
        if claims.get("in_patch"):
            L.append(f"- 패치가 실제로 건드리는 파일: {', '.join('`' + f + '`' for f in claims['in_patch'][:10])}")
        L.append("")

    if searches:
        L.append("### 전수 조사 — 산출물이 제시한 검색을 다시 돌린 결과")
        for s in searches:
            if s.get("status") == "ran":
                note = f"  ({s['note']})" if s.get("note") else ""
                L.append(f"- `{s['cmd']}` → **{s['hits']}건**{note}")
                for x in (s.get("sample") or [])[:6]:
                    L.append(f"    - {x[:160]}")
            else:
                L.append(f"- `{s['cmd']}` → 실행 안 함 ({s.get('note', '')})")
        L.append("")
        L.append("산출물이 '이곳뿐 / 전부 / 없다' 라고 썼는데 위 건수가 그와 다르면 그 단정이 거짓이다.")
        L.append("")

    if cites:
        L.append("### 인용한 줄의 실제 내용")
        L.append("")
        L.append("| 산출물이 인용한 위치 | 그 줄에 실제로 있는 것 |")
        L.append("|---|---|")
        for c in cites:
            st = c["status"]
            if st == "ok":
                actual = str(c.get("actual", "")).replace("|", "\\|")
            elif st == "no_file":
                actual = "**그런 파일이 없다**"
            elif st == "out_of_range":
                actual = f"**줄 번호가 범위를 벗어난다** {c.get('actual','')}"
            elif st == "ambiguous":
                actual = f"경로가 모호하다 — 후보: {c['path']}"
            elif st == "abbreviated":
                actual = "경로를 축약해 써서 확인 불가 — 전체 경로로 다시 쓸 것"
            else:
                actual = "읽을 수 없다"
            L.append(f"| `{c['cited']}` | {actual} |")
        L.append("")
        L.append("표의 '실제 내용'이 산출물의 서술과 다르면 인용이 틀린 것이다.")
    return "\n".join(L)
