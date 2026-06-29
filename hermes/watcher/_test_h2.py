"""H2 sanity test — agent_team이 harness 통합 후 정상 import / validate."""
from harness import with_retry, with_validation, validate_role_output, ROLE_SCHEMAS
from agent_team import invoke_agent  # noqa

# reviewer 출력 검증
ok = '```json\n{"verdict":"ok","quality_score":85,"notes":"good"}\n```'
vr = validate_role_output("reviewer", ok)
print(f"reviewer ok: {vr.ok}, parsed.verdict={vr.parsed.get('verdict') if vr.parsed else None}")

# bad output (verdict 빠짐)
bad = '```json\n{"quality_score":85}\n```'
vr2 = validate_role_output("reviewer", bad)
print(f"reviewer bad: {vr2.ok}, errors={vr2.errors[:2]}")

# unknown role
vr3 = validate_role_output("translator_xyz_unknown", '{"foo":"bar"}')
print(f"unknown role: {vr3.ok}, has_schema={vr3.has_schema}")

print(f"\n총 {len(ROLE_SCHEMAS)}개 역할 schema 등록")
print(f"등록된 역할: {sorted(ROLE_SCHEMAS.keys())}")
