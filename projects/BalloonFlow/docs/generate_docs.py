"""
BalloonFlow — YAML 기획서 → .docx 문서 변환기
레퍼런스 스타일: Arial, Heading 1/2, List Paragraph, 테이블
"""
import io, sys, os, yaml
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

BASE = r"E:\AI\projects\BalloonFlow\design_workflow"
OUT = r"E:\AI\projects\BalloonFlow\docs"

# ── Helpers ──

def load_yaml(path):
    with open(os.path.join(BASE, path), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def make_doc(title, subtitle=""):
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(10)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '맑은 고딕')

    for level in [1, 2, 3]:
        hs = doc.styles[f'Heading {level}']
        hs.font.name = 'Arial'
        hs.element.rPr.rFonts.set(qn('w:eastAsia'), '맑은 고딕')

    # Title
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(22)
    run.font.name = 'Arial'

    if subtitle:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run2 = p2.add_run(subtitle)
        run2.font.size = Pt(11)
        run2.font.color.rgb = RGBColor(100, 100, 100)

    doc.add_paragraph()  # spacer
    return doc

def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = str(h)
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(9)
        shading = cell._element.get_or_add_tcPr()
        bg = shading.makeelement(qn('w:shd'), {
            qn('w:val'): 'clear',
            qn('w:color'): 'auto',
            qn('w:fill'): '4472C4'
        })
        shading.append(bg)
        for r in cell.paragraphs[0].runs:
            r.font.color.rgb = RGBColor(255, 255, 255)

    # Data rows
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = str(val) if val is not None else ""
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)

    doc.add_paragraph()  # spacer
    return table

def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(str(text), style='List Bullet')
    p.paragraph_format.left_indent = Cm(1.5 + level * 1.0)
    return p

def add_info_block(doc, label, value):
    p = doc.add_paragraph()
    run = p.add_run(f"{label}: ")
    run.bold = True
    run.font.size = Pt(10)
    run2 = p.add_run(str(value))
    run2.font.size = Pt(10)

def save(doc, filename):
    path = os.path.join(OUT, filename)
    doc.save(path)
    print(f"  Created: {filename}")


# ════════════════════════════════════════
# Doc 1: 게임 기획서 (Game Design Document)
# ════════════════════════════════════════
def gen_game_design():
    concept = load_yaml("concept.yaml")
    gd = load_yaml("layer1/game_design.yaml")

    doc = make_doc(
        "Balloon Flow!",
        "Dart × Balloon — Oddly Satisfying Queue Puzzle\n2026. 03. 11 | Game Design Document v1.0"
    )

    # 1. Vision
    doc.add_heading("1. 비전 (Vision)", level=1)
    add_info_block(doc, "한 줄 요약", concept['core_fun']['one_liner'])
    doc.add_paragraph(concept['core_fun']['extended'].strip())

    doc.add_heading("1-1. Design Pillars", level=2)
    for pillar in concept['design_pillars']:
        doc.add_heading(f"Pillar {pillar['priority']}: {pillar['name']}", level=3)
        doc.add_paragraph(pillar['description'].strip())
        if 'metrics' in pillar:
            for m in pillar['metrics']:
                add_bullet(doc, m)

    # 2. Target Audience
    doc.add_heading("2. 타겟 유저", level=1)
    ta = concept['target_audience']
    add_table(doc,
        ["구분", "연령", "성별", "특성"],
        [
            ["Primary", ta['primary']['age'], ta['primary']['gender'], ta['primary']['description']],
            ["Secondary", ta['secondary']['age'], ta['secondary']['gender'], ta['secondary']['description']],
        ])

    # 3. Core Loop
    doc.add_heading("3. 코어 루프", level=1)
    doc.add_heading("Inner Loop (한 판)", level=2)
    doc.add_paragraph(concept['core_loop']['diagram'].strip())
    doc.add_heading("Outer Loop (성장)", level=2)
    doc.add_paragraph(concept['core_loop']['outer_loop'].strip())

    # 4. Systems Overview
    doc.add_heading("4. 시스템 구성 (45개 시스템)", level=1)
    systems = gd['systems']
    rows = []
    for domain_name, info in systems.items():
        sys_list = ", ".join(info['systems'])
        rows.append([domain_name, info['description'], str(len(info['systems'])), sys_list])
    add_table(doc, ["도메인", "설명", "수", "시스템 목록"], rows)

    # 5. Art Direction
    doc.add_heading("5. 아트 디렉션", level=1)
    ad = concept['art_direction']
    add_info_block(doc, "스타일", ad['style'])
    add_info_block(doc, "컬러 팔레트", ad['color_palette'])
    add_info_block(doc, "풍선", ad['balloon_style'])
    add_info_block(doc, "다트", ad['dart_style'])
    add_info_block(doc, "팝 이펙트", ad['pop_effect'])
    add_info_block(doc, "배경", ad['background'])

    # 6. Technical
    doc.add_heading("6. 기술 요구사항", level=1)
    tech = gd['technical']
    add_table(doc,
        ["항목", "값"],
        [
            ["Min Android SDK", tech['min_android_sdk']],
            ["Min iOS", tech['min_ios']],
            ["Target FPS", tech['target_fps']],
            ["Max Draw Calls", tech['max_draw_calls']],
            ["Max Balloon On Screen", tech['max_balloon_on_screen']],
            ["Object Pool", "필수"],
            ["Orientation", tech['screen_orientation']],
        ])

    # 7. References
    doc.add_heading("7. 레퍼런스 게임", level=1)
    refs = concept['references']
    add_table(doc,
        ["게임", "관련성", "차별점"],
        [[r['name'], r['relevance'], r['difference']] for r in refs])

    save(doc, "BalloonFlow_게임기획서.docx")


# ════════════════════════════════════════
# Doc 2: 시스템 설계서 (System Spec)
# ════════════════════════════════════════
def gen_system_spec():
    doc = make_doc(
        "BalloonFlow 시스템 설계서",
        "9개 도메인 × 45개 시스템 상세 명세\n2026. 03. 11 | System Specification v1.0"
    )

    domain_files = [
        ("InGame", "systems/ingame.yaml"),
        ("Content", "systems/content.yaml"),
        ("Balance", "systems/balance.yaml"),
        ("OutGame", "systems/outgame.yaml"),
        ("BM", "systems/bm.yaml"),
        ("UX", "systems/ux.yaml"),
        ("Meta", "systems/meta.yaml"),
        ("Social", "systems/social.yaml"),
    ]

    for domain_name, filepath in domain_files:
        data = load_yaml(filepath)
        tier = data.get('tier', '?')
        doc.add_heading(f"{domain_name} (Tier {tier})", level=1)

        # Parameters table
        params = data.get('parameters', {})
        if isinstance(params, dict):
            rows = []
            for key, val in params.items():
                if isinstance(val, dict):
                    desc = val.get('description', val.get('type', str(val)))
                    if len(str(desc)) > 80:
                        desc = str(desc)[:77] + "..."
                    rows.append([key, desc])
                elif isinstance(val, list):
                    items = ", ".join(str(v) for v in val[:5])
                    if len(val) > 5:
                        items += f" ... (+{len(val)-5})"
                    rows.append([key, items])
                else:
                    rows.append([key, str(val)])
            if rows:
                doc.add_heading("파라미터", level=2)
                add_table(doc, ["파라미터", "값/설명"], rows)

        # Systems list
        systems = data.get('systems', [])
        if systems:
            doc.add_heading("시스템 목록", level=2)
            for s in systems:
                add_bullet(doc, s)

        doc.add_paragraph()  # spacer

    save(doc, "BalloonFlow_시스템설계서.docx")


# ════════════════════════════════════════
# Doc 3: 밸런스 설계서
# ════════════════════════════════════════
def gen_balance():
    dc = load_yaml("balance/difficulty_curve.yaml")
    eco = load_yaml("balance/economy.yaml")

    doc = make_doc(
        "BalloonFlow 밸런스 설계서",
        "난이도 곡선 + 경제 시뮬레이션\n2026. 03. 11 | Balance Design v1.0"
    )

    # Difficulty
    doc.add_heading("1. 난이도 공식 (Difficulty Score)", level=1)
    doc.add_paragraph(dc['difficulty_score']['formula'].strip())

    doc.add_heading("1-1. 가중치", level=2)
    w = dc['difficulty_score']['weights']
    add_table(doc,
        ["변수", "가중치", "설명"],
        [
            ["W_color", w['W_color'], "색상 수 기반"],
            ["W_count", w['W_count'], "풍선 수 기반"],
            ["W_special", w['W_special'], "특수 풍선 비율"],
            ["W_buffer", w['W_buffer'], "다트 여유도 (역비례)"],
            ["W_rail", w['W_rail'], "레일 복잡도"],
        ])

    doc.add_heading("1-2. 난이도 예시값", level=2)
    examples = dc['difficulty_score']['examples']
    add_table(doc,
        ["Level", "Colors", "Balloons", "Special%", "Buffer", "Rail", "Score"],
        [[e['level'], e['num_colors'], e['balloon_count'],
          e['special_ratio'], e['buffer_mult'], e['rail_complexity'], e['score']]
         for e in examples])

    # Sawtooth
    doc.add_heading("2. 톱니 패턴 (Sawtooth Modulation)", level=1)
    doc.add_paragraph(dc['sawtooth']['description'].strip())
    mods = dc['sawtooth']['modifiers']
    add_table(doc,
        ["Position", "0 (쉬움)", "1", "2", "3 (스파이크)", "4 (휴식)"],
        [["Modifier"] + [str(m) for m in mods]])

    # Dart count
    doc.add_heading("3. 다트 수 (Move Limit)", level=1)
    doc.add_paragraph(dc['dart_count']['formula'].strip())
    add_table(doc,
        ["Level", "Balloons", "Optimal", "Purpose", "Buffer", "Darts"],
        [[e['level'], e['balloons'], e['optimal'], e['purpose'], e['buffer'], e['darts']]
         for e in dc['dart_count']['examples']])

    # Balloon speed
    doc.add_heading("4. 풍선 이동 속도", level=1)
    doc.add_paragraph(f"공식: {dc['balloon_speed']['formula']}")
    doc.add_paragraph(f"범위: {dc['balloon_speed']['range'][0]} ~ {dc['balloon_speed']['range'][1]} {dc['balloon_speed']['unit']}")

    # Overflow
    doc.add_heading("5. 오버플로우 한도", level=1)
    doc.add_paragraph(f"공식: {dc['overflow_limit']['formula']}")
    add_table(doc,
        ["Level", "Overflow Limit"],
        [[e['level'], e['overflow']] for e in dc['overflow_limit']['examples']])

    # Star thresholds
    doc.add_heading("6. 스타 점수 기준", level=1)
    doc.add_paragraph(dc['star_thresholds']['formula'].strip())

    # Clear rate
    doc.add_heading("7. 클리어율 예측 모델", level=1)
    doc.add_paragraph(dc['clear_rate_model']['formula'].strip())
    doc.add_paragraph(dc['clear_rate_model']['description'].strip())

    # Economy
    doc.add_heading("8. 코인 경제", level=1)
    doc.add_heading("8-1. 일일 소스", level=2)
    cs = eco['coin_economy']['daily_sources']
    rows = []
    for name, info in cs.items():
        est = info.get('daily_estimate', info.get('avg_daily', ''))
        rows.append([name, str(est)])
    add_table(doc, ["소스", "일일 추정"], rows)
    add_info_block(doc, "일일 총 소스", eco['coin_economy']['daily_total_source'])
    add_info_block(doc, "일일 총 싱크", eco['coin_economy']['daily_total_sink'])
    add_info_block(doc, "순 흐름", eco['coin_economy']['net_flow'])

    doc.add_heading("9. 젬 경제", level=1)
    add_info_block(doc, "일일 무과금 소스", eco['gem_economy']['daily_total_source_free'])
    add_info_block(doc, "일일 싱크", eco['gem_economy']['daily_total_sink'])
    add_info_block(doc, "적자", eco['gem_economy']['deficit'])

    doc.add_heading("10. 하트 경제", level=1)
    he = eco['heart_economy']
    add_info_block(doc, "최대", he['max'])
    add_info_block(doc, "충전 시간", f"{he['regen_minutes']}분/개")
    add_info_block(doc, "일일 자연 충전", he['daily_natural_regen'])
    add_info_block(doc, "일일 소비", he['daily_consumption']['daily_hearts_used'])

    doc.add_heading("11. LTV 예측", level=1)
    ltv = eco['ltv_projection']
    add_table(doc,
        ["지표", "값"],
        [
            ["D1 Retention", ltv['assumptions']['D1_retention']],
            ["D7 Retention", ltv['assumptions']['D7_retention']],
            ["D30 Retention", ltv['assumptions']['D30_retention']],
            ["Payer Rate", ltv['assumptions']['payer_rate']],
            ["ARPPU", f"${ltv['assumptions']['ARPPU']}"],
            ["Ad ARPDAU", f"${ltv['assumptions']['ad_ARPDAU']}"],
            ["LTV (IAP)", ltv['formulas']['LTV_iap']],
            ["LTV (Ad)", ltv['formulas']['LTV_ad']],
            ["LTV (Total)", ltv['formulas']['LTV_total']],
        ])

    save(doc, "BalloonFlow_밸런스설계서.docx")


# ════════════════════════════════════════
# Doc 4: 콘텐츠 설계서
# ════════════════════════════════════════
def gen_content():
    ld = load_yaml("content/level_design.yaml")
    prog = load_yaml("content/progression.yaml")
    content = load_yaml("systems/content.yaml")

    doc = make_doc(
        "BalloonFlow 콘텐츠 설계서",
        "레벨 디자인 + 진행 스케줄 + 챕터 구조\n2026. 03. 11 | Content Design v1.0"
    )

    # Level overview
    doc.add_heading("1. 레벨 개요", level=1)
    p = content['parameters']
    add_info_block(doc, "총 레벨 수", p['total_level_count'])
    add_info_block(doc, "챕터 구조", p['chapter_structure'])
    add_info_block(doc, "평균 플레이 시간", f"{p['level_duration_avg']} 초")
    add_info_block(doc, "튜토리얼 레벨", f"{p['tutorial_level_count']}개")

    # Chapters
    doc.add_heading("2. 챕터 구성", level=1)
    chapters = content.get('chapters', [])
    add_table(doc,
        ["챕터", "이름", "레벨", "테마", "레일 타입"],
        [[c['chapter'], c['name'], f"{c['levels'][0]}~{c['levels'][1]}", c['theme'], c['rail_type']]
         for c in chapters])

    # Color schedule
    doc.add_heading("3. 색상 도입 스케줄", level=1)
    add_table(doc,
        ["레벨 범위", "색상 수", "비고"],
        [[f"{s['level_range'][0]}~{s['level_range'][1]}", s['colors'], s['note']]
         for s in p['color_intro_schedule']])

    # Gimmick schedule
    doc.add_heading("4. 기믹 도입 스케줄", level=1)
    add_table(doc,
        ["레벨", "기믹", "설명"],
        [[g['level'], g['gimmick'], g['description']]
         for g in p['gimmick_intro_schedule']])

    # Level purpose
    doc.add_heading("5. 레벨 목적 분류", level=1)
    pa = ld.get('purpose_assignment', {})
    if pa:
        doc.add_paragraph(pa.get('rule', '').strip())
        dt = pa.get('distribution_target', {})
        add_table(doc,
            ["목적", "비율"],
            [[k, v] for k, v in dt.items()])

    # Tutorial levels
    doc.add_heading("6. 튜토리얼 레벨 (1~5)", level=1)
    tut = ld.get('tutorial_levels', {})
    for lvl_name, info in tut.items():
        doc.add_heading(lvl_name.replace('_', ' ').title(), level=2)
        add_info_block(doc, "풍선", info['balloons'])
        add_info_block(doc, "색상", info['colors'])
        add_info_block(doc, "다트", info['darts'])
        add_info_block(doc, "가이드", info['guide'])
        add_info_block(doc, "목표", info['objective'])

    # Boss level
    doc.add_heading("7. 보스 레벨 구조", level=1)
    boss = ld.get('boss_level', {})
    if boss:
        add_info_block(doc, "빈도", boss['frequency'])
        struct = boss.get('structure', {})
        for phase, desc in struct.items():
            add_bullet(doc, f"{phase}: {desc}")
        add_info_block(doc, "다트 예산", boss['dart_budget'])
        add_info_block(doc, "보상", boss['rewards'])

    # Progression timeline
    doc.add_heading("8. 전체 진행 타임라인", level=1)
    timeline = prog.get('timeline', [])
    rows = []
    for t in timeline:
        unlocks = ", ".join(t.get('unlocks', []))
        boss_mark = " [BOSS]" if t.get('boss') else ""
        rows.append([t['level'], t['event'] + boss_mark, t.get('colors', ''), unlocks])
    add_table(doc, ["Level", "이벤트", "Colors", "해금"], rows)

    # Day progression
    doc.add_heading("9. 일자별 진행 예상", level=1)
    dp = prog.get('day_progression', {}).get('estimates', {})
    if dp:
        rows = []
        for day in ['D1', 'D7', 'D14', 'D30']:
            casual = dp.get('casual', {}).get(day, '')
            core = dp.get('core', {}).get(day, '')
            rows.append([day, casual, core])
        add_table(doc, ["Day", "캐주얼 유저", "코어 유저"], rows)

    # Longevity
    doc.add_heading("10. 콘텐츠 수명", level=1)
    longevity = prog.get('longevity', {})
    add_info_block(doc, "런칭 콘텐츠", longevity.get('launch_content', ''))
    add_info_block(doc, "업데이트 계획", longevity.get('update_plan', ''))
    for plan in longevity.get('post_200_plan', []):
        add_bullet(doc, plan)

    save(doc, "BalloonFlow_콘텐츠설계서.docx")


# ════════════════════════════════════════
# Doc 5: BM/LiveOps 설계서
# ════════════════════════════════════════
def gen_bm_liveops():
    bm = load_yaml("systems/bm.yaml")
    liveops = load_yaml("liveops/operations.yaml")
    outgame = load_yaml("systems/outgame.yaml")

    doc = make_doc(
        "BalloonFlow BM & LiveOps 설계서",
        "수익화 구조 + 라이브 운영 계획\n2026. 03. 11 | BM & LiveOps v1.0"
    )

    # BM overview
    doc.add_heading("1. 수익화 모델", level=1)
    bp = bm['parameters']
    add_info_block(doc, "모델", bp['monetization_model'])
    add_info_block(doc, "광고 프리 기간", f"{bp['ad_free_period']}분")
    add_info_block(doc, "IAP 가격대", f"${bp['iap_price_range'][0]} ~ ${bp['iap_price_range'][1]}")

    # Rewarded ads
    doc.add_heading("2. 보상형 광고", level=1)
    add_table(doc,
        ["위치", "트리거", "보상", "일일 제한"],
        [[a['placement'], a['trigger'], a['reward'], a['daily_cap']]
         for a in bp['rewarded_ad_placements']])

    # Interstitial
    doc.add_heading("3. 전면 광고", level=1)
    inter = bp['interstitial_frequency']
    add_info_block(doc, "기본 빈도", inter['base'])
    add_info_block(doc, "쿨다운", inter['cooldown'])
    doc.add_heading("스킵 조건", level=2)
    for cond in inter['skip_conditions']:
        add_bullet(doc, cond)

    # IAP Packages
    doc.add_heading("4. IAP 패키지", level=1)
    doc.add_heading("4-1. 젬 팩", level=2)
    iap = bm.get('iap_packages', {})
    gem_packs = iap.get('gem_packs', [])
    add_table(doc,
        ["이름", "젬", "가격($)", "보너스"],
        [[g['name'], g['gems'], g['price'], g['bonus']] for g in gem_packs])

    doc.add_heading("4-2. 특별 오퍼", level=2)
    offers = iap.get('special_offers', [])
    add_table(doc,
        ["이름", "가격($)", "트리거", "제한시간"],
        [[o['name'], o['price'], o['trigger'], o['time_limit']] for o in offers])

    doc.add_heading("4-3. 광고 제거", level=2)
    no_ads = iap.get('no_ads', [])
    for na in no_ads:
        add_info_block(doc, na['name'], f"${na['price']} ({na['type']})")

    # Starter pack
    doc.add_heading("5. 스타터팩", level=1)
    sp = bp.get('starter_pack', {})
    add_info_block(doc, "가격", f"${sp.get('price', 'N/A')}")
    add_info_block(doc, "해금 조건", sp.get('unlock_condition', ''))
    add_info_block(doc, "제한 시간", sp.get('time_limit', ''))
    add_info_block(doc, "가치 배율", f"{sp.get('value_ratio', '')}x")
    doc.add_heading("구성품", level=2)
    for item in sp.get('contents', []):
        add_bullet(doc, item)

    # Piggy bank
    doc.add_heading("6. 피기뱅크", level=1)
    pb = bp.get('piggy_bank', {})
    add_table(doc,
        ["항목", "값"],
        [
            ["가격", f"${pb.get('price', '')}"],
            ["충전 주기", f"{pb.get('fill_cycle', '')}판"],
            ["보상 구성", pb.get('reward_composition', '')],
            ["가치 배율", f"{pb.get('value_ratio', '')}x"],
            ["해금 조건", pb.get('unlock_condition', '')],
            ["시각 피드백", pb.get('visual_feedback', '')],
        ])

    # Season pass
    doc.add_heading("7. 시즌패스", level=1)
    ssp = bp.get('season_pass', {})
    add_info_block(doc, "가격", f"${ssp.get('price', '')}/시즌 ({ssp.get('price', '')}주)")
    add_info_block(doc, "무료 트랙", ssp.get('free_track', ''))
    add_info_block(doc, "프리미엄 트랙", ssp.get('premium_track', ''))
    add_info_block(doc, "레벨 수", ssp.get('levels', ''))
    add_info_block(doc, "XP 소스", ssp.get('xp_source', ''))

    # OutGame - Booster
    doc.add_heading("8. 부스터 시스템", level=1)
    op = outgame['parameters']
    for category in ['pre_play', 'in_play', 'continue']:
        boosters = op.get('booster_types', {}).get(category, [])
        if boosters:
            doc.add_heading(f"8-{list(op['booster_types'].keys()).index(category)+1}. {category}", level=2)
            add_table(doc,
                ["ID", "이름", "설명", "비용"],
                [[b['id'], b['name'], b['description'],
                  str(b.get('cost', b.get('escalation', '')))] for b in boosters])

    # Currency
    doc.add_heading("9. 재화 구조", level=1)
    for curr in op.get('currency_types', []):
        add_info_block(doc, f"{curr['name']} ({curr['id']})", curr['description'])

    # LiveOps
    doc.add_heading("10. 라이브 운영 계획", level=1)
    lp = liveops['parameters']
    add_info_block(doc, "시즌 주기", f"{lp['season_cycle']}주")

    doc.add_heading("10-1. 이벤트 캘린더", level=2)
    cal = lp.get('event_calendar', {})
    rows = []
    for freq, events in cal.items():
        for ev in events:
            rows.append([freq, ev['name'], ev['type'], ev.get('duration', ''), ev.get('rewards', '')])
    add_table(doc, ["주기", "이름", "타입", "기간", "보상"], rows)

    doc.add_heading("10-2. 업데이트 주기", level=2)
    uc = lp.get('update_cycle', {})
    add_table(doc,
        ["유형", "주기"],
        [[k, v] for k, v in uc.items()])

    # AB Test
    doc.add_heading("10-3. AB 테스트 계획", level=2)
    abt = lp.get('ab_test_plan', {})
    sl = abt.get('soft_launch', [])
    if sl:
        add_table(doc,
            ["테스트", "변형", "측정 지표", "기간"],
            [[t['test'], str(t['variants']), t['metric'], t['duration']] for t in sl])

    # Daily Quests
    doc.add_heading("11. 일일 퀘스트", level=1)
    dq = liveops.get('daily_quests', {})
    add_info_block(doc, "일일 퀘스트 수", dq.get('count', 3))
    for ex in dq.get('examples', []):
        add_bullet(doc, ex)
    add_info_block(doc, "전부 완료 보너스", dq.get('bonus', ''))

    save(doc, "BalloonFlow_BM_LiveOps설계서.docx")


# ════════════════════════════════════════
# Doc 6: 빌드 오더 (코드 생성용)
# ════════════════════════════════════════
def gen_build_order():
    bo = load_yaml("layer2/build_order.yaml")

    doc = make_doc(
        "BalloonFlow 빌드 오더",
        "Phase 0~3 시스템 빌드 순서 + 의존성 그래프\n2026. 03. 11 | Build Order v1.0"
    )

    for phase_key in ['phase_0', 'phase_1', 'phase_2', 'phase_3']:
        phase = bo[phase_key]
        doc.add_heading(f"{phase_key.replace('_', ' ').title()}: {phase['name']}", level=1)
        doc.add_paragraph(phase['description'])

        systems = phase['systems']
        rows = []
        for s in systems:
            owner = s.get('owner', phase.get('owner', ''))
            reqs = ", ".join(s.get('requires', [])) or "(없음)"
            provs = ", ".join(s.get('provides', []))
            rows.append([s['name'], s.get('layer', ''), s.get('domain', ''),
                        owner, s.get('complexity', ''), reqs])
        add_table(doc,
            ["시스템", "Layer", "Domain", "담당", "복잡도", "의존성"],
            rows)

        add_info_block(doc, "시스템 수", phase['count'])

    # Summary
    doc.add_heading("Summary", level=1)
    summary = bo['summary']
    add_table(doc,
        ["Phase", "Count", "Owner", "Layer"],
        [
            ["Phase 0", summary['phase_0']['count'], summary['phase_0']['owner'], summary['phase_0']['layer']],
            ["Phase 1", summary['phase_1']['count'], summary['phase_1']['owners'], summary['phase_1']['layer']],
            ["Phase 2", summary['phase_2']['count'], summary['phase_2']['owners'], summary['phase_2']['layer']],
            ["Phase 3", summary['phase_3']['count'], summary['phase_3']['owners'], summary['phase_3']['layer']],
            ["Total", summary['total'], "-", "-"],
        ])

    doc.add_heading("Critical Path", level=1)
    for path in bo['critical_path']:
        add_bullet(doc, path)

    save(doc, "BalloonFlow_빌드오더.docx")


# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════
if __name__ == "__main__":
    print("Generating BalloonFlow .docx documents...")
    gen_game_design()
    gen_system_spec()
    gen_balance()
    gen_content()
    gen_bm_liveops()
    gen_build_order()
    print(f"\nDone! All documents saved to: {OUT}")
