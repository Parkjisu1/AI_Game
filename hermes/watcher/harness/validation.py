"""
H2 Validation — pydantic schema 강제 + 잘못된 응답 시 자동 re-prompt.

핵심 컴포넌트:

1. ROLE_SCHEMAS — 역할별 pydantic 모델 (7개 핵심 + 일반 fallback)
2. validate_role_output(role, raw_text) → ValidationResult
3. build_repair_prompt(orig_prompt, bad_output, errors) → 재시도 프롬프트
4. with_validation(call_fn, role, max_repair=1) → wrapper
   - LLM 호출 후 schema 검증
   - 실패 시 1회 더 호출 (에러 정보 prompt에 추가)
   - 그래도 실패면 최선의 응답 반환

H1과의 관계:
  with_retry (H1, 외층 - 네트워크 transient)
    └── with_validation (H2, 내층 - malformed output)
         └── _invoke_claude_code / _invoke_via_litellm

스키마 적용 정책:
  - 정의된 역할: 필드 타입 + enum + range 강제
  - 미정의 역할: validation 스킵 (raw output 그대로)
  - 부분 일치도 허용 — 핵심 필드만 채워있으면 OK
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

try:
    from pydantic import BaseModel, Field, ValidationError, ConfigDict
except ImportError:
    BaseModel = object  # type: ignore
    ValidationError = Exception  # type: ignore

log = logging.getLogger("harness.validation")


# ──────────────────────────────────────────────
# Pydantic schemas (역할별)
# ──────────────────────────────────────────────
class _LooseModel(BaseModel):
    """추가 필드 허용 — LLM이 spec 외 필드 넣어도 무시."""
    model_config = ConfigDict(extra="ignore")


class TranslatorOutput(_LooseModel):
    """translator 에이전트."""
    clarity: str  # "clear" | "needs_input" | "cancel" | "rollback"
    team: Optional[str] = None  # "dev" | "art" | "design" | "chat"
    concept_keywords: list[str] = Field(default_factory=list)
    files_examined: list[str] = Field(default_factory=list)
    current_state: str = ""
    enriched_description: str = ""
    questions: list[str] = Field(default_factory=list)
    question_preamble: str = ""
    cancel_reason: str = ""
    rollback_reason: str = ""


class PMOutput(_LooseModel):
    """art_pm, design_pm — sub_team 결정."""
    sub_team: str  # "ui" | "server" | "ingame" | ... 자유 입력
    reason: str = ""


class ReviewerOutput(_LooseModel):
    """reviewer, art_reviewer, design_level_reviewer 등."""
    verdict: str  # "ok" | "revise" | "regenerate" | "APPROVED" | "REJECTED" | "cannot_review"
    quality_score: Optional[int] = None  # 0-100
    notes: str = ""
    visual_observations: list[str] = Field(default_factory=list)
    issues_found: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    suggested_prompt_adjustments: str = ""
    suggested_spec_adjustments: str = ""


class CodeAgentOutput(_LooseModel):
    """lead, main_coder, sub_coder, optimizer — 코드 작업 결과."""
    files_modified: list[str] = Field(default_factory=list)
    summary: str = ""
    plan_summary: str = ""        # lead용
    sub_tasks: list[Any] = Field(default_factory=list)  # lead용
    optimizations: list[str] = Field(default_factory=list)  # optimizer용
    phase_plan: list[Any] = Field(default_factory=list)  # phased execution


class ValidatorOutput(_LooseModel):
    """validator, optimization_reviewer."""
    passed: Optional[bool] = None
    issues: list[str] = Field(default_factory=list)


class DesignLevelOutput(_LooseModel):
    """design_level_designer — grid spec."""
    width: int
    height: int
    symmetry: str  # "none" | "2-fold-h" | "2-fold-v" | "4-fold" | "diagonal" | "4-fold-rot"
    palette: list[int]
    per_color_count: dict[str, int] = Field(default_factory=dict)
    seed: int = 0
    name: str = ""
    pattern: str = "rings"
    density: float = 1.0
    mask_shape: str = "uniform"
    rationale: str = ""


class ArtPromptOutput(_LooseModel):
    """art_prompter — image prompt spec."""
    gpt_prompt: str
    tags: list[str] = Field(default_factory=list)
    n: int = 1
    size: str = "1024x1024"
    quality: str = "high"
    transparent_background: bool = False


class SeniorReflectorOutput(_LooseModel):
    """senior_reflector — 도메인 원칙 추출."""
    principles: list[dict] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Role → Schema 매핑
# ──────────────────────────────────────────────
ROLE_SCHEMAS: dict[str, type[_LooseModel]] = {
    "translator": TranslatorOutput,
    "art_pm": PMOutput,
    "design_pm": PMOutput,
    # reviewers
    "reviewer": ReviewerOutput,
    "art_reviewer": ReviewerOutput,
    "art_ui_reviewer": ReviewerOutput,
    "art_bg_reviewer": ReviewerOutput,
    "art_illust_reviewer": ReviewerOutput,
    "design_level_reviewer": ReviewerOutput,
    "design_content_reviewer": ReviewerOutput,
    "optimization_reviewer": ReviewerOutput,
    # code agents
    "lead": CodeAgentOutput,
    "main_coder": CodeAgentOutput,
    "sub_coder": CodeAgentOutput,
    "optimizer": CodeAgentOutput,
    # validators
    "validator": ValidatorOutput,
    # designers
    "design_level_designer": DesignLevelOutput,
    # art prompters
    "art_prompter": ArtPromptOutput,
    "art_ui_prompter": ArtPromptOutput,
    "art_bg_prompter": ArtPromptOutput,
    "art_illust_prompter": ArtPromptOutput,
    # reflector
    "senior_reflector": SeniorReflectorOutput,
}


# ──────────────────────────────────────────────
# Validation result
# ──────────────────────────────────────────────
@dataclass
class ValidationResult:
    ok: bool
    parsed: Optional[dict[str, Any]] = None  # validated dict (또는 raw if no schema)
    errors: list[str] = field(default_factory=list)
    schema_name: str = ""

    @property
    def has_schema(self) -> bool:
        return bool(self.schema_name)


# ──────────────────────────────────────────────
# JSON 추출 (기존 _try_parse_json 강화 버전)
# ──────────────────────────────────────────────
def extract_json(text: str) -> Optional[dict[str, Any]]:
    """
    text에서 JSON 객체 추출.
    1. ```json ... ``` 코드 블록 우선
    2. 본문 첫 { ... } 페어
    3. 둘 다 실패면 None
    """
    if not text:
        return None
    # 1. fenced code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    # 2. 첫 { ... } 매칭 (균형 잡힌 brace 찾기)
    text_stripped = text.strip()
    if text_stripped.startswith("{"):
        try:
            return json.loads(text_stripped)
        except (json.JSONDecodeError, ValueError):
            pass
    # 3. 본문에서 첫 { 부터 균형 } 까지
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break
    return None


# ──────────────────────────────────────────────
# 핵심 검증
# ──────────────────────────────────────────────
def validate_role_output(role: str, raw_text: str) -> ValidationResult:
    """
    역할별 schema 검증. 미정의 역할은 무조건 ok=True (raw dict 또는 None).
    """
    schema = ROLE_SCHEMAS.get(role)
    parsed_json = extract_json(raw_text)

    if schema is None:
        # 미정의 역할 — JSON만 있으면 OK, 없어도 OK (text-only 응답)
        return ValidationResult(
            ok=True,
            parsed=parsed_json,
            errors=[],
            schema_name="",
        )

    if parsed_json is None:
        return ValidationResult(
            ok=False,
            parsed=None,
            errors=["응답에 JSON 객체가 없음 (```json``` 블록 또는 raw {} 필요)"],
            schema_name=schema.__name__,
        )

    try:
        model = schema(**parsed_json)
        return ValidationResult(
            ok=True,
            parsed=model.model_dump(),
            errors=[],
            schema_name=schema.__name__,
        )
    except ValidationError as e:
        # pydantic 에러를 사람 읽기 좋게
        err_lines: list[str] = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            msg = err.get("msg", "")
            err_lines.append(f"  - {loc}: {msg}")
        return ValidationResult(
            ok=False,
            parsed=parsed_json,  # raw dict 그대로 — partial recovery 시도
            errors=[f"schema {schema.__name__} 위반:"] + err_lines,
            schema_name=schema.__name__,
        )
    except (TypeError, ValueError) as e:
        return ValidationResult(
            ok=False,
            parsed=parsed_json,
            errors=[f"{type(e).__name__}: {e}"],
            schema_name=schema.__name__,
        )


# ──────────────────────────────────────────────
# Re-prompt builder
# ──────────────────────────────────────────────
def build_repair_prompt(
    original_prompt: str, bad_output: str, errors: list[str],
    schema_hint: str = "",
) -> str:
    """LLM이 잘못된 응답을 고쳐서 재시도하도록 prompt 재구성."""
    err_block = "\n".join(errors[:10])
    snippet = bad_output[:1500] if bad_output else "(empty)"
    repair = (
        f"\n\n---\n\n"
        f"⚠️ **STOP** — 직전 응답이 schema에 맞지 않습니다. 아래 오류 보고 수정한 JSON만 다시 반환.\n\n"
        f"**직전 응답** (앞부분):\n```\n{snippet}\n```\n\n"
        f"**스키마 위반 사항**:\n{err_block}\n\n"
    )
    if schema_hint:
        repair += f"**기대 스키마 (`{schema_hint}`)**: 페르소나의 'Output JSON' 섹션 참고.\n\n"
    repair += (
        "**규칙**:\n"
        "1. JSON 코드 블록 (```json ... ```) 1개만 출력\n"
        "2. 코드 블록 외 텍스트 금지\n"
        "3. 모든 required 필드 반드시 포함\n"
        "4. 필드 타입 정확 (int는 int, str은 str, list는 list)\n"
    )
    return original_prompt + repair


# ──────────────────────────────────────────────
# Decorator
# ──────────────────────────────────────────────
T = TypeVar("T")


def with_validation(
    role: str, *, max_repair: int = 1,
):
    """
    Decorator: LLM 호출 후 schema 검증. 실패 시 1회 repair re-prompt.

    호출 함수의 시그니처:  fn(prompt: str, *args, **kwargs) → (output: str, usage: Optional[dict])

    반환값에 ValidationResult 정보를 부착하지 않고 (output, usage)는 그대로 반환.
    검증 결과는 invoke_agent가 별도로 호출해 사용 (구조화 응답 결과 처리).
    """
    def decorator(fn: Callable[..., tuple[str, Optional[dict]]]):
        def wrapper(prompt: str, *args, **kwargs) -> tuple[str, Optional[dict]]:
            # 1차 호출
            output, usage = fn(prompt, *args, **kwargs)
            if max_repair <= 0:
                return output, usage
            vr = validate_role_output(role, output)
            if vr.ok:
                return output, usage

            # 1차 실패 — schema 정의된 역할이면 repair 시도
            if not vr.has_schema:
                return output, usage  # 미정의 역할은 검증 안 함 → 그대로
            log.warning("[validation:%s] 1차 실패, repair 재시도 — errors=%s",
                        role, vr.errors[:3])

            repair_prompt = build_repair_prompt(
                prompt, output, vr.errors,
                schema_hint=vr.schema_name,
            )
            try:
                repaired_output, repaired_usage = fn(repair_prompt, *args, **kwargs)
            except Exception as e:
                log.warning("[validation:%s] repair call 실패 (%s) — 원본 반환", role, e)
                return output, usage
            vr2 = validate_role_output(role, repaired_output)
            if vr2.ok:
                log.info("[validation:%s] repair 성공", role)
                # usage 합산
                if usage and repaired_usage:
                    merged = {k: usage.get(k, 0) + repaired_usage.get(k, 0)
                              for k in {*usage, *repaired_usage}}
                    return repaired_output, merged
                return repaired_output, repaired_usage or usage
            log.warning("[validation:%s] repair도 실패 — best 반환 (errors=%s)",
                        role, vr2.errors[:3])
            return repaired_output, repaired_usage or usage
        wrapper.__wrapped__ = fn  # type: ignore
        return wrapper
    return decorator


# ──────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # 1. JSON extraction
    print("\n[extract_json]")
    cases = [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('prefix\n```json\n{"foo": "bar"}\n```\nsuffix', {"foo": "bar"}),
        ('blah\n{"x": 2, "y": [1, 2]}\nmore', {"x": 2, "y": [1, 2]}),
        ('not json at all', None),
    ]
    for text, expected in cases:
        actual = extract_json(text)
        ok = "✓" if actual == expected else "✗"
        print(f"  {ok} {text[:40]:40s} → {actual}")

    # 2. Schema validation
    print("\n[validate_role_output: translator]")
    ok_text = '```json\n{"clarity": "clear", "team": "dev", "enriched_description": "fix bug"}\n```'
    vr = validate_role_output("translator", ok_text)
    print(f"  ok=True case: {vr.ok} errors={vr.errors}")
    assert vr.ok

    bad_text = '```json\n{"team": "dev"}\n```'  # missing clarity
    vr = validate_role_output("translator", bad_text)
    print(f"  missing clarity: {vr.ok} errors={vr.errors[:2]}")
    assert not vr.ok

    print("\n[validate_role_output: design_level_designer]")
    designer_ok = '''```json
{"width": 25, "height": 25, "symmetry": "4-fold-rot",
 "palette": [0, 2, 13, 17],
 "per_color_count": {"0": 40, "2": 40, "13": 60, "17": 40},
 "seed": 42, "pattern": "rings"}
```'''
    vr = validate_role_output("design_level_designer", designer_ok)
    print(f"  ok case: {vr.ok}")
    assert vr.ok

    designer_bad = '```json\n{"width": "25"}\n```'  # width should be int, missing fields
    vr = validate_role_output("design_level_designer", designer_bad)
    print(f"  bad case: {vr.ok} errors[0]={vr.errors[0] if vr.errors else None}")
    assert not vr.ok

    # 3. Unknown role
    print("\n[validate_role_output: unknown role]")
    vr = validate_role_output("some_role_not_defined", '{"foo": "bar"}')
    print(f"  unknown role: ok={vr.ok} (no schema)")
    assert vr.ok and not vr.has_schema

    # 4. with_validation decorator
    print("\n[with_validation]")
    call_count = {"n": 0}

    def mock_call(prompt, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # 1차: malformed
            return ('{"wrong": "field"}', {"input_tokens": 10, "output_tokens": 5})
        # 2차 (repair): correct
        return ('{"clarity": "clear", "team": "dev"}', {"input_tokens": 20, "output_tokens": 8})

    wrapped = with_validation("translator", max_repair=1)(mock_call)
    out, usage = wrapped("hello")
    vr = validate_role_output("translator", out)
    print(f"  attempts={call_count['n']} final_ok={vr.ok} usage={usage}")
    assert call_count["n"] == 2
    assert vr.ok

    # 5. Repair prompt
    print("\n[build_repair_prompt]")
    rp = build_repair_prompt(
        "Please return JSON.",
        '{"wrong": "field"}',
        ["clarity field missing"],
        schema_hint="TranslatorOutput",
    )
    assert "STOP" in rp and "schema" in rp.lower()
    print(f"  repair prompt built ({len(rp)} chars)")

    print("\n✅ all H2 self-tests passed")
