# -*- coding: utf-8 -*-
"""AIMED — AI 게임 개발 워크플로우 발표자료 (재디자인: Pretendard + 실사 이미지 + AIMED 브랜딩)."""
import os
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ---------- Palette (editorial, restrained) ----------
INK    = RGBColor(0x1B, 0x1C, 0x24)
BRAND  = RGBColor(0x22, 0x24, 0x3A)   # deep indigo (dividers)
ACCENT = RGBColor(0xE8, 0x6A, 0x33)   # warm coral-orange
SKY    = RGBColor(0x2E, 0x9B, 0xD6)
PAPER  = RGBColor(0xFF, 0xFF, 0xFF)
SOFT   = RGBColor(0xF6, 0xF5, 0xF2)   # warm off-white
GRAY   = RGBColor(0x6E, 0x70, 0x79)
MUTE   = RGBColor(0x9A, 0x9C, 0xA5)
LINE   = RGBColor(0xE3, 0xE1, 0xDC)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
CREAM  = RGBColor(0xCE, 0xCF, 0xDA)   # light text on dark
F = "Pretendard"

AST = r"E:\AI\docs\ppt_assets"
def img(name): return os.path.join(AST, name)

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]
def slide(): return prs.slides.add_slide(BLANK)

def rect(s, x, y, w, h, fill, line=None, lw=0.75, shape=MSO_SHAPE.RECTANGLE):
    sp = s.shapes.add_shape(shape, x, y, w, h)
    if fill is None: sp.fill.background()
    else: sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None: sp.line.fill.background()
    else: sp.line.color.rgb = line; sp.line.width = Pt(lw)
    sp.shadow.inherit = False
    return sp

def txt(s, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=True, space=3, line=1.0):
    tb = s.shapes.add_textbox(x, y, w, h); tf = tb.text_frame
    tf.word_wrap = wrap; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Pt(0); tf.margin_top = tf.margin_bottom = Pt(0)
    if runs and isinstance(runs[0], tuple): runs = [runs]
    first = True
    for para in runs:
        p = tf.paragraphs[0] if first else tf.add_paragraph(); first = False
        p.alignment = align; p.space_after = Pt(space); p.space_before = Pt(0)
        try: p.line_spacing = line
        except Exception: pass
        for (t, sz, color, bold, *rest) in para:
            r = p.add_run(); r.text = t
            r.font.size = Pt(sz); r.font.color.rgb = color; r.font.bold = bold
            r.font.name = rest[0] if rest else F
    return tb

def fit_image(s, path, x, y, w, h, align="center"):
    """Place image fully inside (x,y,w,h) preserving aspect (contain)."""
    iw, ih = Image.open(path).size
    bw, bh = float(w), float(h)
    scale = min(bw/iw, bh/ih)
    nw, nh = int(iw*scale), int(ih*scale)
    nx = int(x + (bw-nw)/2); ny = int(y + (bh-nh)/2)
    return s.shapes.add_picture(path, nx, ny, width=Emu(nw), height=Emu(nh))

def phone(s, path, cx, top, ph_h):
    """Draw a phone mockup centered at cx, given phone height; returns (left,width)."""
    iw, ih = Image.open(path).size
    inner_h = ph_h - Inches(0.18)
    inner_w = Emu(int(int(inner_h) * iw/ih))
    frame_w = inner_w + Inches(0.18)
    fx = int(cx - int(frame_w)/2)
    rect(s, Emu(fx), top, frame_w, ph_h, INK, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    s.shapes.add_picture(path, Emu(fx)+Inches(0.09), top+Inches(0.09), width=inner_w, height=inner_h)
    return fx, int(frame_w)

def kicker(s, x, y, text, color=ACCENT):
    txt(s, x, y, Inches(8), Inches(0.3), [[(text.upper(), 11.5, color, True)]])

def page_meta(s, n, dark=False):
    c = CREAM if dark else MUTE
    txt(s, Inches(0.6), Inches(7.07), Inches(6), Inches(0.3), [[("AIMED", 9.5, c, True),("   ·  AI 게임 개발 워크플로우", 9.5, c, False)]])
    txt(s, Inches(12.1), Inches(7.07), Inches(0.7), Inches(0.3), [[(f"{n:02d}", 9.5, c, True)]], align=PP_ALIGN.RIGHT)

PAGE=[0]
def pg(): PAGE[0]+=1; return PAGE[0]

def content_head(s, kick, title, sub=None):
    """Light content slide header: kicker + headline + thin accent rule (no heavy bar)."""
    rect(s, 0, 0, SW, SH, PAPER)
    kicker(s, Inches(0.6), Inches(0.5), kick)
    txt(s, Inches(0.6), Inches(0.78), Inches(12.1), Inches(0.7), [[(title, 27, INK, True)]])
    rect(s, Inches(0.62), Inches(1.5), Inches(0.55), Pt(3.2), ACCENT)
    if sub:
        txt(s, Inches(0.6), Inches(1.62), Inches(12.1), Inches(0.4), [[(sub, 13, GRAY, False)]])

def divider(num, kick, title, sub):
    s = slide(); rect(s, 0, 0, SW, SH, BRAND)
    # big ghost number
    txt(s, Inches(8.3), Inches(0.7), Inches(4.6), Inches(6), [[(f"{num:02d}", 240, RGBColor(0x2E,0x30,0x4C), True)]], align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    rect(s, Inches(0.7), Inches(3.0), Inches(0.9), Pt(4), ACCENT)
    txt(s, Inches(0.7), Inches(2.4), Inches(8), Inches(0.5), [[(kick.upper(), 14, ACCENT, True)]])
    txt(s, Inches(0.7), Inches(3.25), Inches(8.5), Inches(1.4), [[(title, 44, WHITE, True)]])
    txt(s, Inches(0.7), Inches(4.7), Inches(7.8), Inches(1.6), [[(sub, 15.5, CREAM, False)]], line=1.15)
    page_meta(s, pg(), dark=True)
    return s

def mini_table(s, x, y, w, col_w, rows, fs=12, rh=0.46, head_fs=12):
    ncol=len(col_w); nrow=len(rows)
    gt = s.shapes.add_table(nrow, ncol, x, y, w, Inches(rh*nrow)).table
    gt.first_row=False; gt.horz_banding=False
    tot=sum(col_w)
    for i,cw in enumerate(col_w): gt.columns[i].width=Emu(int(int(w)*cw/tot))
    for ri,row in enumerate(rows):
        gt.rows[ri].height=Inches(rh)
        for ci,val in enumerate(row):
            c=gt.cell(ri,ci)
            c.margin_left=Pt(7); c.margin_right=Pt(6); c.margin_top=Pt(2); c.margin_bottom=Pt(2)
            c.vertical_anchor=MSO_ANCHOR.MIDDLE
            if ri==0:
                c.fill.solid(); c.fill.fore_color.rgb=BRAND; fc,bd,size=WHITE,True,head_fs
            else:
                c.fill.solid(); c.fill.fore_color.rgb=PAPER if ri%2 else SOFT; fc,bd,size=INK,False,fs
            tf=c.text_frame; tf.word_wrap=True
            p=tf.paragraphs[0]; p.alignment=PP_ALIGN.LEFT
            r=p.add_run(); r.text=str(val); r.font.size=Pt(size); r.font.color.rgb=fc; r.font.bold=bd; r.font.name=F
    return gt

def bullets(s, x, y, w, items, sz=14, gap=9, lh=1.08):
    tb=s.shapes.add_textbox(x,y,w,Inches(5)); tf=tb.text_frame; tf.word_wrap=True
    tf.margin_left=tf.margin_top=Pt(0)
    first=True
    for it in items:
        bold=False; color=INK; lvl=0
        if isinstance(it,tuple): it,opt=it[0],it[1]; bold=opt.get("bold",False); color=opt.get("color",INK); lvl=opt.get("lvl",0)
        p=tf.paragraphs[0] if first else tf.add_paragraph(); first=False
        p.space_after=Pt(gap); p.space_before=Pt(0)
        try: p.line_spacing=lh
        except: pass
        mark = "— " if lvl else ""
        mc = MUTE if lvl else ACCENT
        if not lvl:
            rb=p.add_run(); rb.text="■  "; rb.font.size=Pt(sz*0.7); rb.font.color.rgb=ACCENT; rb.font.bold=True; rb.font.name=F
        else:
            rb=p.add_run(); rb.text="    – "; rb.font.size=Pt(sz); rb.font.color.rgb=MUTE; rb.font.name=F
        r=p.add_run(); r.text=it; r.font.size=Pt(sz); r.font.color.rgb=color; r.font.bold=bold; r.font.name=F
    return tb

def metric_row(s, y, cards, x0=Inches(0.6), total_w=None):
    n=len(cards); gap=Inches(0.28)
    tw = total_w or (SW - Inches(1.2))
    cw=(tw - gap*(n-1))/n
    for i,(big,small,unit) in enumerate(cards):
        x=x0+i*(cw+gap)
        rect(s,x,y,cw,Inches(1.5),SOFT)
        rect(s,x,y,Inches(0.08),Inches(1.5),ACCENT)
        txt(s,x+Inches(0.22),y+Inches(0.2),cw-Inches(0.3),Inches(0.62),[[(big,32,INK,True),(unit,15,ACCENT,True)]])
        txt(s,x+Inches(0.22),y+Inches(0.92),cw-Inches(0.35),Inches(0.5),[[(small,11.5,GRAY,False)]],line=1.0)

# =================================================================
# 01 COVER
# =================================================================
s = slide(); rect(s,0,0,SW,SH,SOFT)
rect(s,0,0,Inches(7.9),SH,PAPER)
# left text block
txt(s, Inches(0.85), Inches(0.95), Inches(6), Inches(0.6), [[("AIMED", 30, INK, True)],], )
rect(s, Inches(0.88), Inches(1.62), Inches(0.5), Pt(3.4), ACCENT)
txt(s, Inches(0.85), Inches(2.7), Inches(6.7), Inches(2.0),
    [[("AI 게임 개발", 46, INK, True)],[("워크플로우 & 자체 도구", 46, INK, True)]], line=1.02)
txt(s, Inches(0.86), Inches(4.65), Inches(6.4), Inches(1.0),
    [[("기획부터 코드·콘텐츠·테스트·운영까지", 16, GRAY, False)],
     [("AI로 자동화·증강한 사내 시스템 전반", 16, GRAY, False)]], line=1.2, space=4)
txt(s, Inches(0.86), Inches(6.5), Inches(6), Inches(0.5),
    [[("2026-05-26", 12, MUTE, True),("    |    내부 자료", 12, MUTE, False)]])
# right: phone mockup of real gameplay
rect(s, Inches(7.9), 0, Inches(5.43), SH, SOFT)
phone(s, img("shot1.png"), int(Inches(10.6)), Inches(0.95), Inches(5.6))
txt(s, Inches(8.2), Inches(6.72), Inches(4.9), Inches(0.4),
    [[("자사 타이틀 ", 11, GRAY, False),("BalloonLoop", 11, INK, True),(" — AI 워크플로우 산출물", 11, GRAY, False)]], align=PP_ALIGN.CENTER)

# =================================================================
# 02 EXECUTIVE SUMMARY
# =================================================================
s = slide(); content_head(s, "Executive Summary", "한 장 요약")
msgs=[
 ("작동하는 시스템을 만든다","코드 조각이 아니라 파일 간 연결을 계약으로 추적·검증해 통합 실패를 구조적으로 차단"),
 ("환각을 프로세스로 통제","분류 체계 · DB 의무 검색 · 차단형 검증 훅으로 신뢰성을 모델이 아닌 규율로 확보"),
 ("AI가 직접 플레이해 검증","자사 빌드를 사람처럼 자율 플레이하며 밸런스·진행·클리어 가능성을 실측"),
 ("실제 출시 수준까지 제작","기획·레벨·코드·빌드까지 — 자사 퍼즐 게임 BalloonLoop을 출하 수준으로 생산"),
]
y0=Inches(2.1)
for i,(t,d) in enumerate(msgs):
    col=i%2; row=i//2
    x=Inches(0.6)+col*Inches(6.25); y=y0+row*Inches(2.15)
    txt(s,x,y,Inches(0.9),Inches(0.7),[[(f"0{i+1}",30,ACCENT,True)]])
    txt(s,x+Inches(0.95),y+Inches(0.02),Inches(5.0),Inches(0.6),[[(t,17,INK,True)]])
    rect(s,x+Inches(0.97),y+Inches(0.52),Inches(0.4),Pt(2.4),LINE)
    txt(s,x+Inches(0.95),y+Inches(0.68),Inches(5.1),Inches(1.2),[[(d,12.5,GRAY,False)]],line=1.15)
page_meta(s,pg())

# =================================================================
# 03 OVERVIEW — 우리가 만든 시스템
# =================================================================
s = slide(); content_head(s, "Our Systems", "우리가 만든 시스템 한눈에",
                          "독립 도구가 아니라 단일 데이터 중추(MongoDB)로 연결된 하나의 체계")
items=[
 ("GameForge","AI 기획·코드 자동 생성 파이프라인"),
 ("Virtual Player","자율 플레이 테스터 (자사 빌드 검증)"),
 ("PixelForge","레벨 자동 생성 (픽셀아트·추상패턴)"),
 ("Vision","게임 화면 자동 인식"),
 ("ProjectHub","MCP 기반 Unity 제어 + 태스크 보드"),
 ("Hermes","자율 태스크 라우팅 데몬"),
 ("BalloonLoop","AI 워크플로우로 만든 자사 게임"),
 ("AI_WORK_FLOW_TEST","파이프라인이 생성한 게임 프로젝트군"),
]
gap=Inches(0.25); cols=4; cw=(SW-Inches(1.2)-gap*(cols-1))/cols; ch=Inches(1.7)
for i,(n,d) in enumerate(items):
    col=i%4; row=i//4
    x=Inches(0.6)+col*(cw+gap); y=Inches(2.2)+row*(ch+Inches(0.3))
    rect(s,x,y,cw,ch,SOFT)
    txt(s,x+Inches(0.22),y+Inches(0.2),Inches(0.5),Inches(0.4),[[(f"{i+1:02d}",13,ACCENT,True)]])
    txt(s,x+Inches(0.22),y+Inches(0.62),cw-Inches(0.4),Inches(0.5),[[(n,15.5,INK,True)]])
    txt(s,x+Inches(0.22),y+Inches(1.08),cw-Inches(0.4),Inches(0.55),[[(d,10.5,GRAY,False)]],line=1.05)
page_meta(s,pg())

# =================================================================
# 04 SCALE
# =================================================================
s = slide(); content_head(s, "Scale · 2026-05-26 실측", "실가동 운영 규모",
                          "실험이 아니라 누적 가동 중인 운영 시스템 — 텔레메트리가 실사용을 증명")
metric_row(s, Inches(2.2), [
 ("2,465","에이전트 실행 트레이스","건"),
 ("1,319","에이전트 세션","건"),
 ("5,093","자동 생성 레벨","건"),
 ("300","출하 레벨 세트","개"),
])
metric_row(s, Inches(4.1), [
 ("11","역할 분리 AI 에이전트","종"),
 ("912","토큰 사용 기록(비용 추적)","건"),
 ("241","축적된 도메인 설계 원칙","건"),
 ("30","단일 DB 컬렉션","개"),
])
page_meta(s,pg())

# =================================================================
# DIVIDER 01 — 생성
# =================================================================
divider(1, "Creation", "생성", "기획 · 코드 · 콘텐츠를 자동 생성하는 파이프라인 — GameForge / PixelForge / 생성 프로젝트군")

# 05 GameForge — Agent Team
s = slide(); content_head(s, "GameForge", "역할 분리 AI 에이전트 팀 (11종)",
                          "인간 게임 스튜디오의 직무 분화를 모사 — 전략·아키텍처는 상위 모델, 도메인 실행은 경량 모델")
rows=[
 ["에이전트","역할"],
 ["Lead","PM — 태스크 분배·조율·평가, Phase Gate, 계약 검증"],
 ["Designer","3-Layer 기획서 생성 (YAML + 문서 듀얼 출력)"],
 ["Main Coder","Core 아키텍처 + 복잡 시스템 + 계약 문서 단독 작성"],
 ["Sub Coder ×2","일반 노드 병렬 구현 (계약 선행 독해)"],
 ["Validator","코드 5+1.5단계 검증 (통합 검증 포함)"],
 ["Design Validator","기획 검증 · 점수 산출 · 승격 판정"],
 ["Reviewer ×2","기획 품질 + 사업성 QA"],
]
mini_table(s, Inches(0.6), Inches(2.15), Inches(7.1), [2.2,5.6], rows, fs=12.5, rh=0.5)
# right note card
rect(s, Inches(8.05), Inches(2.15), Inches(4.68), Inches(4.0), SOFT)
rect(s, Inches(8.05), Inches(2.15), Inches(0.08), Inches(4.0), ACCENT)
txt(s, Inches(8.3), Inches(2.4), Inches(4.2), Inches(0.5), [[("3-AI 분리 원칙",15,INK,True)]])
bullets(s, Inches(8.3), Inches(3.0), Inches(4.2), [
  "DB 가공 · 기획 · 코드 생성 AI를 분리",
  "각 에이전트는 고유 페르소나 + 금지 규칙 보유",
  "Phase 0 단독 → Phase 1+ 병렬 생성",
  "Lead가 품질 평가 후 다음 단계 게이팅",
], sz=12, gap=10)
page_meta(s,pg())

# 06 GameForge — 신뢰성 (환각방지 + ICS)
s = slide(); content_head(s, "GameForge · 신뢰성", "신뢰성을 모델이 아닌 엔지니어링으로",
                          "생성 AI의 약점(환각·통합 실패)을 시스템 규율로 통제")
txt(s, Inches(0.6), Inches(2.05), Inches(6), Inches(0.4), [[("환각 방지 체계",15,INK,True)]])
bullets(s, Inches(0.6), Inches(2.5), Inches(5.9), [
  "4단 분류(Layer/Genre/Role/Tag) — 검색 키이자 탐지 기준",
  "5-Tier DB 검색을 생성 전 의무화",
  "미검색 직접 생성은 '환각 위험'으로 거부",
  "커밋·저장 시 차단형 검증 훅 자동 실행",
], sz=12.5, gap=10)
txt(s, Inches(6.85), Inches(2.05), Inches(6), Inches(0.4), [[("통합 계약 시스템 (ICS)",15,INK,True)]])
bullets(s, Inches(6.85), Inches(2.5), Inches(5.9), [
  "파일 간 연결(이벤트·풀키·필드·호출)을 계약 문서로 추적",
  "검증기가 계약 ↔ 실제 코드 교차 검증",
  "에러 수정 시 기획 의도 이탈 방지 프로토콜",
  "대규모 병렬 생성물의 통합 실패를 사전 차단",
], sz=12.5, gap=10)
rect(s, Inches(0.6), Inches(5.75), Inches(12.13), Inches(0.95), BRAND)
txt(s, Inches(0.85), Inches(5.92), Inches(11.7), Inches(0.65),
    [[("핵심 차별점  ",13,ACCENT,True),("업계 일반의 '코드 스니펫 생성'과 달리, 40개 파일을 동시 생성해도 ",13,WHITE,False),("작동하는 하나의 시스템",13,WHITE,True),("으로 통합됨을 보증",13,WHITE,False)]],
    anchor=MSO_ANCHOR.MIDDLE)
page_meta(s,pg())

# 07 GameForge — Design Workflow
s = slide(); content_head(s, "GameForge · 기획 자동화", "기획 워크플로우 (Stage 0~8)",
                          "표준 → DB → 생성 → 검증 → 검수 → 축적 → 플레이검증 → 라이브, 그리고 자가 학습")
stages=[("0","설계 표준"),("1","DB 가공"),("2","기획 생성"),("3","통합 검증"),("4","디렉터 검수"),
        ("5","재생성 평가"),("6","DB 축적"),("7","플레이 검증"),("8","라이브 동기화")]
x0=Inches(0.6); cw=Inches(3.95); ch=Inches(0.92); gx=Inches(0.12); gy=Inches(0.18)
for i,(n,t) in enumerate(stages):
    col=i%3; row=i//3
    x=x0+col*(cw+gx); y=Inches(2.25)+row*(ch+gy)
    rect(s,x,y,cw,ch,SOFT)
    rect(s,x,y,Inches(0.72),ch,BRAND if i<7 else ACCENT)
    txt(s,x,y,Inches(0.72),ch,[[(n,24,WHITE,True)]],align=PP_ALIGN.CENTER,anchor=MSO_ANCHOR.MIDDLE)
    txt(s,x+Inches(0.88),y,cw-Inches(1.0),ch,[[(t,14.5,INK,True)]],anchor=MSO_ANCHOR.MIDDLE)
txt(s, Inches(0.6), Inches(5.95), Inches(12), Inches(0.7),
    [[("듀얼 출력: ",12.5,ACCENT,True),("YAML(AI 검증·코드생성·DB) + 문서(사람 검수) 동시 생성   ·   ",12.5,GRAY,False),
      ("자가 학습: ",12.5,ACCENT,True),("재사용 성공이 누적되면 신뢰도 점수로 검증 자산(Expert DB) 자동 승격",12.5,GRAY,False)]],line=1.15)
page_meta(s,pg())

# 08 PixelForge — 레벨 자동 생성 (자체 에이전트, 2종 분류)
s = slide(); rect(s,0,0,SW,SH,PAPER)
kicker(s, Inches(0.6), Inches(0.5), "PixelForge")
txt(s, Inches(0.6), Inches(0.78), Inches(8), Inches(0.7), [[("레벨을 자동으로 만든다",27,INK,True)]])
rect(s, Inches(0.62), Inches(1.5), Inches(0.55), Pt(3.2), ACCENT)
txt(s, Inches(0.6), Inches(1.62), Inches(8.0), Inches(0.45), [[("이미지 한 장 → 1:1 구조가 보증된 플레이 레벨 (자체 개발 생성 에이전트)",13,GRAY,False)]])
bullets(s, Inches(0.6), Inches(2.3), Inches(7.2), [
  "시각 소스를 2종으로 분류 후 유형별 생성 백엔드로 라우팅",
  "분류·변환·품질 게이트·자동 보정 = 자체 개발 에이전트 알고리즘",
  "2단계 변환: 필드 생성 → 큐 생성, 1:1 구조 자동 검산",
  "cowork 패턴 13종 + 공백 탐지 → 단일 클러스터 53%→69%",
  "Field Completer가 draft 자동 완성(품질 0.978) → 누적 5,093 생성",
], sz=12.5, gap=10)
# right: 2-type classification cards
def gencard(x, y, tag, tagcol, tool, desc, exam):
    rect(s, x, y, Inches(4.23), Inches(1.7), SOFT)
    rect(s, x, y, Inches(4.23), Inches(0.5), tagcol)
    txt(s, x+Inches(0.2), y, Inches(3.9), Inches(0.5), [[(tag,14,WHITE,True)]], anchor=MSO_ANCHOR.MIDDLE)
    txt(s, x+Inches(0.2), y+Inches(0.62), Inches(3.9), Inches(0.4), [[("생성 백엔드: ",11,GRAY,False),(tool,14,INK,True)]])
    txt(s, x+Inches(0.2), y+Inches(1.06), Inches(3.9), Inches(0.55), [[(desc,10.5,GRAY,False)],[(exam,10,MUTE,False)]],line=1.05,space=2)
gencard(Inches(8.5), Inches(2.25), "[ 픽셀아트 ]", ACCENT, "PixelLab", "AI 픽셀아트 생성", "사물·캐릭터·아이콘형 도안")
gencard(Inches(8.5), Inches(4.15), "[ 추상 · 패턴 ]", SKY, "Claude", "패턴·도형 레이아웃 생성", "기하·대칭·동심·나선 구성")
txt(s, Inches(8.5), Inches(6.0), Inches(4.23), Inches(0.7),
    [[("알고리즘은 자체 개발, 생성 모델(PixelLab·Claude)은 백엔드로 활용",11,ACCENT,True)]],line=1.15)
page_meta(s,pg())

# 09 AI_WORK_FLOW_TEST — 생성된 프로젝트군 (NEW)
s = slide(); content_head(s, "AI_WORK_FLOW_TEST", "파이프라인이 생성한 실제 게임 프로젝트군",
                          "GameForge가 텍스트 기획서로부터 만들어 낸 다수의 Unity 프로젝트 — '한 게임'이 아니라 '게임 공장'")
projs=[
 ("CarMatching","차량 매칭 퍼즐 — Unity 프로젝트 일체 생성"),
 ("DropCat","캐주얼 드롭 퍼즐"),
 ("MagicSort","정렬 퍼즐"),
 ("ShiftTap","타이밍 탭 캐주얼"),
 ("VeilBreaker","퍼즐/액션"),
 ("Puzzle / Playable","퍼즐 빌드 + HTML5 플레이어블 광고군"),
]
gap=Inches(0.25); cols=3; cw=(SW-Inches(1.2)-gap*(cols-1))/cols; ch=Inches(1.35)
for i,(n,d) in enumerate(projs):
    col=i%3; row=i//3
    x=Inches(0.6)+col*(cw+gap); y=Inches(2.35)+row*(ch+Inches(0.28))
    rect(s,x,y,cw,ch,SOFT)
    rect(s,x,y,Inches(0.08),ch,SKY)
    txt(s,x+Inches(0.25),y+Inches(0.2),cw-Inches(0.4),Inches(0.5),[[(n,15,INK,True)]])
    txt(s,x+Inches(0.25),y+Inches(0.68),cw-Inches(0.45),Inches(0.55),[[(d,11,GRAY,False)]],line=1.05)
txt(s, Inches(0.6), Inches(6.4), Inches(12), Inches(0.5),
    [[("각 프로젝트는 런타임 코드 · 에디터 스크립트 · 데이터 에셋 · 씬 구성까지 AI가 생성 → 사람은 아트·최종 검수에 집중",12,GRAY,False)]])
page_meta(s,pg())

# =================================================================
# DIVIDER 02 — 검증 & 운영
# =================================================================
divider(2, "Verification & Operations", "검증 & 운영",
        "만든 것을 AI가 직접 검증하고, 태스크를 자율적으로 운영한다 — Virtual Player / Vision / ProjectHub / Hermes")

# 10 Virtual Player (own-build testing) + screenshot
s = slide(); rect(s,0,0,SW,SH,PAPER)
kicker(s, Inches(0.6), Inches(0.5), "Virtual Player")
txt(s, Inches(0.6), Inches(0.78), Inches(8.4), Inches(0.7), [[("AI가 사람처럼 게임을 플레이한다",27,INK,True)]])
rect(s, Inches(0.62), Inches(1.5), Inches(0.55), Pt(3.2), ACCENT)
txt(s, Inches(0.6), Inches(1.62), Inches(8.4), Inches(0.45), [[("화면만 보고(비전) 자사 빌드를 자율 플레이 → 밸런스·진행·클리어 가능성 검증",13,GRAY,False)]])
bullets(s, Inches(0.6), Inches(2.45), Inches(8.0), [
  "지각 → 기억 → 결정 → 실행 → 검증의 5계층 파이프라인",
  "결정은 규칙 기반 우선순위 트리 — 재현 가능하고 안전",
  "비전 폴백 다단계로 클라우드 호출 비용 최소화",
  "페르소나 5종(캐주얼·하드코어·고래·신규·복귀)별 시뮬레이션",
  "예측 밸런스 vs 실측 비교 → 기획 피드백 자동 생성",
], sz=13, gap=11)
phone(s, img("shot2.png"), int(Inches(11.1)), Inches(1.7), Inches(5.3))
txt(s, Inches(9.4), Inches(7.05), Inches(3.4), Inches(0.35),
    [[("BlueStacks 자동화로 실제 플레이",10.5,MUTE,False)]], align=PP_ALIGN.CENTER)
page_meta(s,pg())

# 11 Vision (brief) + ProjectHub (combined ops)
s = slide(); content_head(s, "Vision & ProjectHub", "화면 인식 + Unity 직접 제어")
txt(s, Inches(0.6), Inches(2.0), Inches(6), Inches(0.4), [[("Vision — 게임 화면 자동 인식",15,INK,True)]])
bullets(s, Inches(0.6), Inches(2.45), Inches(5.9), [
  "보드·UI·기믹 요소를 실시간 인식 (YOLO 계열)",
  "멀티장르 라벨링 도구로 학습 데이터 구축",
  "기하·픽셀 분석과 결합한 하이브리드 인식",
  "테스트 자동화의 '눈' 역할",
], sz=12.5, gap=10)
txt(s, Inches(6.85), Inches(2.0), Inches(6), Inches(0.4), [[("ProjectHub — MCP 기반 Unity 제어",15,INK,True)]])
bullets(s, Inches(6.85), Inches(2.45), Inches(5.9), [
  "AI가 Unity 에디터(씬·프리팹·필드)를 프로그래밍적으로 제어",
  "핵심 통신 계층 외부 의존성 0 — 공급망 위험 최소화",
  "웹 태스크 보드로 사람과 협업",
  "응답 최적화: 목록 API 6.6MB → 185KB (-97%)",
], sz=12.5, gap=10)
page_meta(s,pg())

# 12 Hermes
s = slide(); content_head(s, "Hermes", "자율 태스크 라우팅 데몬",
                          "사람이 만든 태스크에 반응해 적절한 AI 액션으로 자동 라우팅하는 24/7 운영 레이어")
flow=["태스크 생성","이벤트 감지","컨텍스트 적재","액션 분기","실행","상태 자동 갱신"]
n=len(flow); gap=Inches(0.2); cw=(SW-Inches(1.2)-gap*(n-1))/n
for i,f in enumerate(flow):
    x=Inches(0.6)+i*(cw+gap); y=Inches(2.2)
    rect(s,x,y,cw,Inches(0.95),SOFT)
    txt(s,x,y+Inches(0.12),cw,Inches(0.35),[[(f"{i+1}",16,ACCENT,True)]],align=PP_ALIGN.CENTER)
    txt(s,x,y+Inches(0.48),cw,Inches(0.4),[[(f,11.5,INK,True)]],align=PP_ALIGN.CENTER)
    if i<n-1:
        txt(s,x+cw-Inches(0.02),y+Inches(0.28),Inches(0.25),Inches(0.4),[[("›",18,MUTE,True)]],align=PP_ALIGN.CENTER)
txt(s, Inches(0.6), Inches(3.7), Inches(12), Inches(0.4), [[("실가동 텔레메트리",14,INK,True)]])
metric_row(s, Inches(4.2), [
 ("2,465","실행 트레이스","건"),("1,319","에이전트 세션","건"),
 ("912","토큰 사용 기록","건"),("241","도메인 설계 원칙","건"),
])
txt(s, Inches(0.6), Inches(6.0), Inches(12), Inches(0.5),
    [[("→ 도메인 원칙·프롬프트 패치가 축적되며 스스로 개선되는 운영 시스템",12.5,GRAY,False)]])
page_meta(s,pg())

# =================================================================
# DIVIDER 03 — 결과물
# =================================================================
divider(3, "Result", "BalloonLoop", "이 모든 시스템이 합류해 만들어 낸 출하 수준의 자사 퍼즐 게임")

# 13 BalloonLoop showcase (logo + key art + screenshots)
s = slide(); rect(s,0,0,SW,SH,PAPER)
# left key-art band with logo
rect(s, 0, 0, Inches(4.6), SH, SOFT)
fit_image(s, img("hero.png"), Inches(0.0), Inches(0.0), Inches(4.6), SH)
# logo overlay top-left
fit_image(s, img("logo.png"), Inches(0.45), Inches(0.45), Inches(3.7), Inches(1.5))
# middle text column (5.0 ~ 9.4)
kicker(s, Inches(5.0), Inches(0.65), "Result · BalloonLoop")
txt(s, Inches(5.0), Inches(0.95), Inches(4.5), Inches(0.7), [[("AI 워크플로우로 만든 게임",23,INK,True)]])
rect(s, Inches(5.02), Inches(1.6), Inches(0.55), Pt(3.2), ACCENT)
bullets(s, Inches(5.0), Inches(1.95), Inches(4.45), [
  "장르: 퍼즐 / 큐-정렬 (색 매칭 다트 발사)",
  "플랫폼: Unity · Android · 출하 빌드 완료",
  "기획 → 레벨 → 코드 → 빌드 전 주기 AI 증강",
  "300개 출하 레벨 + 자동 생성 파이프라인",
], sz=12.5, gap=10)
metric_row(s, Inches(4.75), [
 ("300","출하 레벨","개"),("0→1","기획부터 제작","")
], x0=Inches(5.0), total_w=Inches(4.45))
# right: single clean phone (no overlap)
phone(s, img("shot3.png"), int(Inches(11.35)), Inches(1.25), Inches(5.4))
txt(s, Inches(9.95), Inches(6.85), Inches(2.85), Inches(0.35),
    [[("출하 빌드 실제 플레이 화면",10.5,MUTE,False)]], align=PP_ALIGN.CENTER)
page_meta(s,pg())

# 14 RESULTS table
s = slide(); content_head(s, "Results", "정량 성과 종합")
rows=[
 ["시스템","핵심 지표","값"],
 ["GameForge","에이전트 / 명령어 / 검증 훅","11 / 20 / 5"],
 ["Virtual Player","결정 계층 / 페르소나","5단계 / 5종"],
 ["PixelForge","자동 생성 레벨 / 단일클러스터","5,093 / 53→69%"],
 ["ProjectHub","API 슬림화 / 외부 의존성","-97% / 0"],
 ["Hermes","실행 트레이스 / 세션","2,465 / 1,319"],
 ["BalloonLoop","출하 레벨 / 빌드","300 / APK·AAB"],
 ["AI_WORK_FLOW_TEST","AI 생성 게임 프로젝트","6+ 종"],
]
mini_table(s, Inches(0.6), Inches(2.1), Inches(12.13), [2.6,5.0,2.4], rows, fs=13, rh=0.56)
page_meta(s,pg())

# 15 CONCLUSION
s = slide(); rect(s,0,0,SW,SH,BRAND)
rect(s, Inches(0.7), Inches(1.3), Inches(0.9), Pt(4), ACCENT)
txt(s, Inches(0.7), Inches(1.55), Inches(11), Inches(0.9), [[("결론",36,WHITE,True)]])
txt(s, Inches(0.7), Inches(2.7), Inches(11.6), Inches(1.8),
    [[("AIMED의 AI 활용은 '생성 AI를 호출하는' 수준을 넘어,",19,CREAM,False)],
     [("역할 분리된 다중 에이전트가 표준 DB·계약·검증 위에서 협업하는",19,CREAM,False)],
     [("게임 스튜디오형 시스템으로 성숙했습니다.",19,WHITE,True)]], line=1.3, space=6)
rect(s, Inches(0.7), Inches(5.0), Inches(11.93), Inches(1.5), RGBColor(0x2C,0x2E,0x48))
txt(s, Inches(1.0), Inches(5.2), Inches(11.3), Inches(1.1),
    [[("핵심 — ",16,ACCENT,True),("신뢰성을 모델이 아닌 엔지니어링으로 확보했다.",16,WHITE,True)],
     [("분류 체계·계약 시스템·차단형 검증·자율 플레이 테스트가 결합되어, 최신 모델과 만날수록 레버리지가 커지는 검증 가능한 운영 프레임워크.",13,CREAM,False)]],
    line=1.25, space=6)
page_meta(s,pg(),dark=True)

# 16 CLOSING
s = slide(); rect(s,0,0,SW,SH,PAPER)
txt(s, 0, Inches(2.9), SW, Inches(1.0), [[("AIMED",44,INK,True)]], align=PP_ALIGN.CENTER)
rect(s, Inches(6.06), Inches(3.95), Inches(1.2), Pt(3.4), ACCENT)
txt(s, 0, Inches(4.2), SW, Inches(0.5), [[("AI 게임 개발 워크플로우 & 자체 도구",15,GRAY,False)]], align=PP_ALIGN.CENTER)
txt(s, 0, Inches(4.75), SW, Inches(0.4), [[("2026-05-26",11.5,MUTE,False)]], align=PP_ALIGN.CENTER)

out = r"E:\AI\docs\AIMED_AI_Workflow_발표자료_2026-05-26.pptx"
prs.save(out)
print("SAVED:", out, "slides=", len(prs.slides._sldIdLst))
