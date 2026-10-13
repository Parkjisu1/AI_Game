"""
골든샘플 Lv34 회귀테스트 — gimmick_placement.py
실행: <venv>/python test_golden_lv34.py   (stdlib만 사용)

검증 3종:
  1) 검증기 parity   — 골든 4안의 instances를 내 validate_color_darts에 넣으면
                       골든 JSON의 color_darts/total/violations를 정확히 재현하는가
  2) generator 스모크 — generate_variants(board,"Wooden") 4안 생성, 경계/검증 정상
  3) apply_variant    — 10배수 clean 안 택1 → 병합 후 풍선제거/기믹추가/재검증 정합
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gimmick_placement as gp

HERE = os.path.dirname(os.path.abspath(__file__))
LEVEL = os.path.join(HERE, "testdata", "level_34.json")
GOLDEN = os.path.join(HERE, "testdata", "lv34_v222_4variants_golden.json")

fails = []


def check(cond, msg):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond:
        fails.append(msg)


def norm_cd(cd):
    """color_darts 키를 int로 정규화 (golden은 str 키)."""
    return {int(k): v for k, v in cd.items()}


# 입력 준비
level_json = json.load(open(LEVEL, encoding="utf-8"))
golden = json.load(open(GOLDEN, encoding="utf-8"))
board = gp.level_json_to_board(level_json)
grid, W, H, bg = gp.board_to_grid(board)

print(f"\n보드: {W}×{H}, 풍선 {len(board['balloons'])}개, bg=c{bg}")
print(f"영역 후보: {len(gp.detect_regions(grid, bg))}개 (상위 5)")
for r in gp.detect_regions(grid, bg)[:5]:
    print(f"    c{r['color']} size={r['size']} bbox={r['bbox_w']}×{r['bbox_h']} center={tuple(round(v,1) for v in r['center'])}")

# ── 1) 검증기 parity ────────────────────────────────────────
print("\n=== 1) 검증기 parity (골든 instances → 내 validator) ===")
for gv in golden["variants"]:
    insts = gv["instances"]
    if not insts:
        continue
    mine = gp.validate_color_darts(grid, insts)
    g_cd = norm_cd(gv["validation"]["color_darts"])
    g_total = gv["validation"]["total"]
    g_viol = sorted([list(v) for v in gv["validation"]["violations"]])
    m_viol = sorted([list(v) for v in mine["violations"]])
    ok_cd = mine["color_darts"] == g_cd
    ok_tot = mine["total"] == g_total
    ok_viol = m_viol == g_viol
    check(ok_cd and ok_tot and ok_viol,
          f"{gv['name']}: color_darts/total/violations 일치 "
          f"(cd={'✓' if ok_cd else '✗'} total={'✓' if ok_tot else '✗'} viol={'✓' if ok_viol else '✗'})")
    if not (ok_cd and ok_tot and ok_viol):
        print(f"        mine : cd={mine['color_darts']} total={mine['total']} viol={m_viol}")
        print(f"        golden: cd={g_cd} total={g_total} viol={g_viol}")

# ── 2) generator 스모크 ─────────────────────────────────────
print("\n=== 2) generator 스모크 (generate_variants) ===")
variants = gp.generate_variants(board, "Wooden")
check(len(variants) == 4, f"4안 생성됨 (생성 {len(variants)}개)")
clean = []
for v in variants:
    insts = v["instances"]
    in_bounds = all(
        0 <= i["pos"][0] and i["pos"][0] + i["size"][0] <= W and
        0 <= i["pos"][1] and i["pos"][1] + i["size"][1] <= H
        for i in insts
    )
    val = v["validation"]
    is_clean = bool(val) and not val["violations"]
    if is_clean:
        clean.append(v)
    tag = "10x✓" if is_clean else ("10x✗" if val else "N/A")
    summary = ", ".join(f"{i['size'][0]}×{i['size'][1]}@{tuple(i['pos'])}hp{i['hp']}c{i['color']}" for i in insts[:3])
    more = f" +{len(insts)-3}개" if len(insts) > 3 else ""
    print(f"  {v['name']:<10} n={len(insts):2} [{tag}] {summary}{more}")
    check(in_bounds, f"{v['name']}: 모든 instance 보드 경계 내")
    check(val is not None or not insts, f"{v['name']}: validation 산출됨")
# raw generator의 책임 = "4안 제안 + 검증". 10배수 clean 강제는 별도(부록 E Algorithm L1.1, 다음 추출).
check(sum(1 for v in variants if v["instances"]) >= 3, "유효 instance 보유 안 ≥3개")
print(f"  (정보) 10배수 clean 안: {len(clean)}개 {[v['name'] for v in clean]} "
      f"— clean 보장은 부록 E auto-fix 담당(미추출)")

# ── 3) apply_variant 병합 ───────────────────────────────────
print("\n=== 3) apply_variant (택1 → 병합) ===")
chosen = clean[0] if clean else variants[1]  # clean 우선, 없으면 2안
n_before = len(board["balloons"])
covered = gp._covered_cells(chosen["instances"])
merged = gp.apply_variant(board, chosen, "Wooden")
n_after = len(merged["balloons"])
n_removed = n_before - n_after
# 덮인 셀 중 실제 표준풍선이 있던 셀 수
occupied_covered = sum(1 for c in covered if c in grid)
check(n_removed == occupied_covered,
      f"덮인 셀의 표준풍선 제거: {n_removed}개 제거 == 점유셀 {occupied_covered}")
check(len(merged["gimmicks"]) == len(chosen["instances"]),
      f"기믹 {len(merged['gimmicks'])}개 추가 == instance {len(chosen['instances'])}개")
check(all(g["type"] == "Wooden" and "sizeW" in g and "hp" in g for g in merged["gimmicks"]),
      "기믹 엔트리 스키마 정합 (type/sizeW/sizeH/hp/color)")
# 병합 후 재검증이 generate 단계 검증과 일치
re_val = gp.validate_color_darts(grid, chosen["instances"])
check(merged["validation"] == re_val, "병합 validation == 독립 재검증")
check(board["balloons"] is not merged["balloons"], "원본 board 불변 (새 dict 반환)")
print(f"  선택: {chosen['name']} → 풍선 {n_before}→{n_after} (-{n_removed}), 기믹 {len(merged['gimmicks'])}개, "
      f"10배수 {'✓' if not merged['validation']['violations'] else '✗ '+str(merged['validation']['violations'])}")

# ── 4) auto-fix (부록 E Algorithm L1.1) ─────────────────────
print("\n=== 4) auto-fix (10배수 자동보정) ===")
for v in variants:
    if not v["instances"]:
        continue
    before = v["validation"]["violations"]
    res = gp.auto_fix_variant(grid, v, "Wooden")
    after = res["validation"]["violations"]
    # 기믹색(=instance color) 위반은 모두 해소돼야 함
    gimmick_colors = {i["color"] for i in v["instances"]}
    after_gimmick_viol = [vio for vio in after if vio[0] in gimmick_colors]
    n_adj = len(res["adjustments"])
    n_des = len(res["designer_needed"])
    tag = "CLEAN" if res["clean"] else f"need designer x{n_des}"
    print(f"  {v['name']:<10} 위반 {len(before)}→{len(after)} | auto-adj {n_adj} | {tag}")
    check(len(after_gimmick_viol) == 0,
          f"{v['name']}: 기믹색 위반 자동 해소 (잔여 기믹색 위반 {len(after_gimmick_viol)})")
    check(res["clean"] == (n_des == 0),
          f"{v['name']}: clean ⇔ designer 불필요 일관")
    # 원본 불변
    check(v["validation"]["violations"] == before, f"{v['name']}: 원본 variant 불변")

# 핵심: 단색 영역 막대(2안)는 auto-fix로 clean 도달해야 함 (골든 2안 정합)
v2 = next(v for v in variants if v["name"].startswith("2안"))
res2 = gp.auto_fix_variant(grid, v2, "Wooden")
check(res2["clean"], f"2안(단색 막대) auto-fix 후 10배수 CLEAN (designer={res2['designer_needed']})")
print(f"  2안 최종: {[(i['size'], i['hp']) for i in res2['variant']['instances'][:2]]}... "
      f"color_darts c8={res2['validation']['color_darts'].get(8)} clean={res2['clean']}")

# ── 5) PNG 미리보기 렌더 ────────────────────────────────────
print("\n=== 5) PNG 미리보기 렌더 ===")
import base64 as _b64
for v in variants:
    b64 = gp.render_variant_png(board, v, indexing="bl", flip_y=True)
    raw = _b64.b64decode(b64)
    check(raw[:8] == b"\x89PNG\r\n\x1a\n", f"{v['name']}: 유효 PNG 시그니처")
    check(len(raw) > 200, f"{v['name']}: PNG 비어있지 않음 ({len(raw)}B)")
# 2×2 합본 저장 (골든 PNG와 시각 비교용)
combined_b64 = gp.render_variants_grid_png(board, variants, indexing="bl", flip_y=True)
out_png = os.path.join(HERE, "testdata", "lv34_generated_4variants.png")
with open(out_png, "wb") as f:
    f.write(_b64.b64decode(combined_b64))
check(os.path.getsize(out_png) > 1000, f"2×2 합본 PNG 저장됨 ({os.path.getsize(out_png)}B) → {out_png}")
print(f"  저장: {out_png}")

# ── 6) Hidden Balloon (1×1 대체, darts 중립) ─────────────────
print("\n=== 6) Hidden Balloon ===")
baseline = gp.validate_color_darts(grid, [])
hvars = gp.generate_variants(board, "Hidden")
check(len(hvars) == 4, f"Hidden 4안 생성 ({len(hvars)})")
for v in hvars:
    insts = v["instances"]
    all_1x1 = all(tuple(i["size"]) == (1, 1) and i["hp"] == 1 for i in insts)
    neutral = v["validation"]["color_darts"] == baseline["color_darts"]
    print(f"  {v['name']:<12} n={len(insts):3} 1x1={all_1x1} darts중립={neutral}")
    check(all_1x1, f"{v['name']}: 모두 1×1 hp1")
    check(neutral, f"{v['name']}: color_darts 중립(baseline 동일) → 10배수 보존")
    check(len(insts) >= 3, f"{v['name']}: instance ≥3")
hm = gp.apply_variant(board, hvars[0], "Hidden")
check(all(g["type"] == "Hidden" for g in hm["gimmicks"]), "Hidden 기믹 엔트리 type=Hidden")
check(len(hm["balloons"]) == n_before - len(hvars[0]["instances"]), "Hidden 셀만큼 표준풍선 대체")

# ── 7) Stage3 기믹 (IronWall/Ice/Barricade/TargetBox) ───────
print("\n=== 7) Stage3 기믹 (오버레이) ===")
baseline_cd = gp.validate_color_darts(grid, [])["color_darts"]
DETAIL_KEY = {"IronWall": "walls", "Ice": "pixelIceBlocks", "Barricade": "gates", "TargetBox": "eggBoxes"}
for gt in ["IronWall", "Ice", "Barricade", "TargetBox"]:
    vs = gp.generate_variants(board, gt)
    removes, dmode = gp._gimmick_rules(gt)
    nz = [v for v in vs if v["instances"]]
    print(f"  {gt:<10} 4안 n={[len(v['instances']) for v in vs]} removes={removes} darts={dmode}")
    check(len(vs) == 4, f"{gt}: 4안 생성")
    check(len(nz) >= 2, f"{gt}: 유효 안 ≥2")
    for v in nz:
        inb = all(0 <= i["pos"][0] and i["pos"][0] + i["size"][0] <= W and
                  0 <= i["pos"][1] and i["pos"][1] + i["size"][1] <= H for i in v["instances"])
        check(inb, f"{gt}/{v['name']}: 경계 내")
    if dmode == "none":  # IronWall/Ice = darts 중립
        neutral = all(v["validation"]["color_darts"] == baseline_cd for v in nz)
        check(neutral, f"{gt}: darts 중립(오버레이, baseline 동일)")
    else:  # Barricade/TargetBox = +Count → auto_fix가 기믹색 해소
        fix = gp.auto_fix_variant(grid, nz[0], gt)
        gcols = {i["color"] for i in nz[0]["instances"]}
        rem = [x for x in fix["validation"]["violations"] if x[0] in gcols]
        check(len(rem) == 0, f"{gt}: auto_fix 후 기믹색(Material) 위반 0")
    m = gp.apply_variant(board, nz[0], gt)
    key = DETAIL_KEY[gt]
    check(key in (m.get("boardGimmicks", {}).get("details", {})), f"{gt}: apply → boardGimmicks.details.{key}")
    check(len(m["balloons"]) == n_before, f"{gt}: 오버레이 — 표준풍선 제거 0")

# ── 결과 ────────────────────────────────────────────────────
print("\n" + "=" * 60)
if fails:
    print(f"❌ FAIL {len(fails)}건:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("✅ ALL PASS — generator 순수함수 추출 검증 완료")
