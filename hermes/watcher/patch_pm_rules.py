"""agent_team.py 의 PM 분류 규칙을 세분 분과 기준으로 교체 (정규식 패치, 멱등)."""
import re

P = "/home/aimed/.hermes/watcher/agent_team.py"
src = open(P, encoding="utf-8").read()

DEV = """가장 구체적인 분과를 고르세요. 세부가 애매하면 거친 분과(ui/server/ingame/outgame).
[UI] ui_hud(HUD·체력·재화·점수·타이머·오버레이) / ui_popup(팝업·모달·결과·설정·확인·일시정지) / ui_lobby(로비·메인메뉴·타이틀·연출) / ui_shop(상점·구매버튼·가격·IAP UI·광고제거) / ui_inventory(보관함·슬롯·장착) / ui(그 외 일반 UI)
[SERVER] server_auth(인증·로그인·세션·토큰) / server_iap(결제·영수증검증·지급) / server_data(세이브·동기화·마이그레이션) / server_liveops(이벤트·시즌·원격설정·푸시) / server_leaderboard(랭킹·점수제출) / server(그 외 백엔드)
[INGAME] ingame_core(코어메카닉·룰·보드·승패) / ingame_gimmick(기믹·장애물) / ingame_input(입력·터치·조준·발사) / ingame_fx(연출·이펙트·파티클·효과음·BGM) / ingame(그 외 인게임)
[OUTGAME] outgame_progression(성장·해금·튜토리얼·진행도) / outgame_reward(보상·재화·일일보상·시즌패스) / outgame_meta(업적·도감·프로필·스트릭) / outgame(그 외 메타)
- general: 인프라/공용/위 어디에도 안 맞음"""

ART = """가장 구체적인 분과를 고르세요.
- art_ui_icon: UI 아이콘·버튼 그래픽·재화/기능 아이콘
- art_ui_panel: UI 패널·창·바·프레임(9-slice)
- art_bg: 배경·환경·스테이지 비주얼
- art_character: 캐릭터·단일 피사체·일러스트(중앙·전신)
- art_fx: 이펙트·파티클 스프라이트·연출 프레임
- ui/background/illustration/general: 위 세부에 안 맞는 거친 분과 fallback"""

DESIGN = """**생성 분과(격자/이미지 산출)와 문서 분과(기획 문서)를 구분하세요.**
[생성]
- level: **선형 격자 패턴** — chevron/kaleidoscope/rings/대칭/기하 (키워드: 패턴·대칭·기하학·격자·타일)
- motif: **비선형 모티프** — 동물·캐릭터·일러스트·특정 그림 (PixelLab 호출)
[문서 기획]
- content_level: 레벨 디자인 문서(난이도곡선·기믹배치·비트차트·큐 명세)
- content_balance: 밸런스/경제(성장·전투·확률·재화 곡선·공식)
- content_liveops: 라이브옵스(이벤트·시즌·운영·KPI)
- content_bm: BM/수익화(결제·패키지·LTV·광고)
- content_narrative: 내러티브/UX텍스트(시나리오·튜토리얼·팝업 문구·텍스트정합)
- content/general: 위 외 일반 기획"""


def repl(name, body, s):
    pat = re.compile(re.escape(name) + r' = """.*?"""', re.S)
    new = f'{name} = """{body}"""'
    s2, n = pat.subn(new, s)
    print(f"  {name}: {'교체' if n else '미발견(확인필요)'}")
    return s2


src = repl("_DEV_PM_RULES", DEV, src)
src = repl("_ART_PM_RULES", ART, src)
src = repl("_DESIGN_PM_RULES", DESIGN, src)
open(P, "w", encoding="utf-8").write(src)
# 문법 확인
import ast
ast.parse(src)
print("문법 OK · 패치 완료")
