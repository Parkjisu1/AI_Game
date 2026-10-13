"""Bounded market/design/art/UA cross-review; never queries live business data."""
import hashlib
import html
import importlib.util
import json
import pathlib
from html.parser import HTMLParser

spec=importlib.util.spec_from_file_location('base_report',pathlib.Path(__file__).with_name('eval-report.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
ROOT=base.ROOT;REPO=ROOT.parent.parent
p,table,section,esc=base.p,base.table,base.section,base.esc

SOURCES=[
('Riot: Prototype','https://www.riotgames.com/en/r-and-d-office/prototype-building-a-games-substance','타깃 정의·대표 경험·플레이테스트와 초기 기획 판단을 연결한다. Riot의 사례 기반 방법론이며 모든 장르 성공의 인과 법칙은 아니다.'),
('Riot: VALORANT art and clarity','https://www.riotgames.com/en/news/valorant-shaders-and-gameplay-clarity','아트·성능·경쟁적 가독성을 함께 설계하고 게임마다 우선순위가 다름을 설명한다. 특정 FPS의 목표 수치를 다른 게임에 적용하지 않는다.'),
('Supercell: History','https://supercell.com/en/about-us/','Gunshine의 초기 관심에도 장기 지루함·진입 장벽·플랫폼 불일치가 문제였다는 회사 회고. 단일 사례이며 초기 관심이 장기 적합성의 충분조건이 아님을 보여주는 참고다.'),
('Google Ads: Conversion Lift metrics','https://support.google.com/google-ads/answer/14102450?hl=en','귀속 전환과 대조군 비교를 통한 증분 전환을 구분한다. 광고에 귀속된 전환 전부를 광고가 새로 만든 결과로 볼 수 없다.'),
('Google Ads: Lift eligibility','https://support.google.com/google-ads/answer/12005564?hl=en','계정·캠페인 등 이용 자격이 제한된다. 언어 페이지 간 조건 표현에도 차이가 있어 실제 집행 시 계정에서 재확인한다. 작은 팀 모두가 이용 가능하다고 가정하지 않는다.'),
('Apple: Product page optimization','https://developer.apple.com/help/app-store-connect/create-product-page-optimization-tests/overview-of-product-page-optimization/','아이콘·스크린샷·미리보기 변형의 무작위 노출 시험. Ready for Distribution 상태가 필요하며 custom product page에는 이 시험을 사용할 수 없다. 미출시 컨셉 탐색의 만능 도구가 아니다.'),
('Apple: AdAttributionKit','https://ads.apple.com/app-store/help/attribution/0093-adattributionkit-to-measure-performance','군중 익명성에 따른 상세 제한과 지연을 설명한다. 모든 유저를 소재별 후속 수익에 결정적으로 연결할 수 있다고 가정하지 않는다.'),
('Firebase: A/B concepts','https://firebase.google.com/docs/ab-testing/ab-concepts','주요/보조 지표와 충분한 데이터·기간, 실험군 데이터를 통한 결과 대조를 설명한다. 일반 Remote Config의 권장 기간이 모든 게임의 장기 효과 검증 기간은 아니다.'),
('Firebase: Remote Config experiments','https://firebase.google.com/docs/ab-testing/abtest-config','매출 목적의 변경에도 유지·안정성 등 다른 지표를 같이 관찰하는 예를 제공한다. 단일 지표 최적화가 제품 전체 개선을 보장하지 않는다.'),
('Steam: UTM Analytics','https://partner.steamgames.com/doc/marketing/utm_analytics','전체/신뢰/로그인 추적 방문을 구분하고 구매·위시리스트·활성화를 클릭 후 72시간 창으로 귀속한다. 관측 누락과 창을 고려해야 한다.'),
('Steam: Visibility','https://partner.steamgames.com/doc/marketing/visibility','일부 예외 외 위시리스트와 스토어 유입량 자체는 알고리즘 노출 요인이 아니라고 설명한다. 위시리스트의 관심 측정·알림 가치는 별개다.')]
def refs(*indices):
 return '<p class="refs">원문 근거: '+', '.join(f'<a href="{SOURCES[i][1]}">{esc(SOURCES[i][0])}</a>' for i in indices)+'. 적용 방법과 의사결정 규칙은 작성자의 제안이다.</p>'

EVIDENCE=[
('output/asset-library-v2/SCHEMA.json',31,44,'아트 메타데이터 범위'),
('output/asset-library-v2/SCHEMA.json',65,65,'기획 본문 미수집'),
('proposal/workflow/AI_workflow_기획_v2.0.md',1024,1048,'시장 성과와 기획 품질 분리; KPI는 스키마 예시'),
('proposal/workflow/AI_workflow_기획_v2.0.md',1072,1087,'실패/원인 불명 데이터 처리'),
('tools/asset-studio/README.md',7,15,'기술 검사와 최종 승인 구분'),
('tools/asset-studio/STYLE_ITERATIONS.ko.md',33,39,'아트/동작/엔진 검수 한계'),
('analytics/로그요청서_초안.md',33,42,'campaign_id 미반영 명시'),
('analytics/로그요청서_초안.md',126,130,'반영 체크리스트'),
('analytics/CLAUDE.md',29,36,'실데이터 추출의 미정 항목'),
('design_standard/puzzle/schema/rawdata-schema.sql',209,225,'게임 내 광고 시청 로그'),
('.claude/agents/reviewer-business.md',85,100,'고정 배수/운영/콘텐츠 기준'),
('.claude/agents/reviewer-business.md',169,177,'B 이상 GO 분기'),
('.claude/agents/reviewer-business.md',291,297,'B는 CONDITIONAL인 다른 분기')]

STAGES=[
('M0 시장·제품 가설','제품/퍼블리싱 책임','누구의 어떤 욕구를 어떤 장르·플랫폼·가격·유입 경로로 충족할지 정의. 직접 경쟁·대체재·실패/중단 사례·지역·시기·제작 역량·런웨이를 함께 조사.','인기작 복제나 추정 시장 규모를 확정 수요로 쓰지 않음. 성공 정의·회수기간·최대 손실·다음 투자 결정을 먼저 정함.'),
('M1 기획·아트·제품 약속','기획·아트·마케팅 공동','컨셉 카드, 핵심 루프/장기 목표, 아트 바이블, 실제 화면, 스토어·소재의 약속을 같은 패키지로 만듦. 내러티브·애니메이션·VFX·사운드·UI도 포함.','광고가 암시하는 경험과 실제 게임에서 전달할 경험의 대응표. 유지할 창작 기둥과 바꿀 표현을 구분.'),
('M2 작은 탐색','UX/리서치·디렉션','타깃 스크리너, 컨셉 이해·선택, 아트 선호, 광고/스토어 샘플을 저비용으로 비교. 친숙한 직원·기존 팬만 모집하지 않음.','탐색 결과와 표본 출처·한계를 기록. 좋아 보인다는 진술을 구매/유지/LTV로 변환하지 않음.'),
('M2.5 계측 준비','분석·개발·UA·재무','데이터 접근 규칙·로그 정의·실험 배정/노출·비용 원장·정산 출처·공통 집계 단위·중복/결측/통화/시간대 확인.','실제 성과 수치를 낼 수 있는 질문과 계산 불가 질문을 명시. 미확인 운영 스키마를 로컬 초안과 동일시하지 않음.'),
('M3 경험과 제작 검증','기획·개발·아트·QA','대표 플레이 구간에서 약속 전달·학습·선택·피드백·반복·저장과 실제 아트/사운드를 연결. 콘텐츠 한 단위를 요구부터 엔진 통합·플레이 검수까지 추적.','대표 구간 동작/가독성/타깃 행동, 승인 납품까지의 투입·대기·수정시간. 전체 출시 준비와는 별도.'),
('M4 유입×경험 교차 시험','UA·제품·분석','소재 시험은 노출/배정부터의 전체 성과와 설치자 조건부 지표를 분리. 제품 시험은 적격 유입에서 제품 노출 전에 배정하고 배정군을 유지.','무작위 배정·표본·관측창·최소 의미 효과·중단 규칙을 사전 기록. 매체 자동 배분을 무작위 실험으로 부르지 않음.'),
('M5 코호트·경제성','분석·재무·제품','성숙 코호트의 유지/환불/IAA·IAP/정산·변동비/UA 비용과 만족·안정성을 함께 확인. 관측과 예측을 분리.','기술 출시 가능·타깃 경험 적합·사업 지속을 따로 판정. 채택/기각/판단 불가를 모두 허용.'),
('M6 출시·확장','제품·퍼블리싱·운영','제품 유형에 맞는 출시/가격/공개 범위·플랫폼 일정 확정. 예산 확대 시 한계 유입비용과 추가 기여, 콘텐츠·CS·서버 능력을 확인.','과거 평균 CPI·LTV를 그대로 확대하지 않음. 충분한 표본/자격이 있을 때만 증분 실험; 아니면 인과 한계 명시.'),
('M7 운영·시장 대응','운영·제품·UA 공동','계측 이상부터 확인하고 유입 믹스·소재 피로·경쟁·계절·제품 변경·소셜 밀도·콘텐츠 소진을 나눔. 설명을 가설로 기록한 뒤 변경/재검증.','긴급 대응과 인과 확인을 구분. 모델이 만든 원인 설명을 확인 없이 자료실의 성공/실패 법칙으로 저장하지 않음.')]

REVIEW_DISPOSITIONS={
'astra':[
'반영: 순수입→UA 전/후 기여→고정비 회수→현금흐름을 분리. 실제 정산·원가 데이터는 미확보.',
'반영: 소재 시험의 배정 기준 전체 성과와 설치자 조건부 성과 분리, 제품 시험 배정/노출/제외 사전 기록. 실제 무작위 시험은 미실행.',
'반영: 지표별 계산 가능한 집계 단위를 먼저 선언. 소재별 결과 식별 불가 시 계산 불가 유지. 캠페인 집계가 곧 인과 증거는 아님.',
'반영: 최소 의미 효과·구분력·예산·중단 및 판단 불가 조건을 계약에 추가. 숫자는 타깃 데이터 없이 발명하지 않음.',
'반영: 창작 기둥/변경 가능한 표현/결정 책임을 구분. 발견성 실패만으로 핵심 경험을 폐기하지 않음.',
'반영: 대표 구간과 출시 준비 구분, 앞선 기술 보고서 연결. 실제 기기·정책·제품 출시 검사는 미실행.',
'반영: 기획→아트→코드→임포트→QA까지 콘텐츠 한 단위의 투입/대기/재작업 추적 제안. 실제 생산성 미측정.',
'반영: F2P·프리미엄·소셜·작은 팀 적용표 추가. 가장 큰 불확실성 하나부터 선택.',
'반영: 탐색 설명/확인된 설명 분리, 독립 기간·대조 확인. 긴급 패치는 대응 사실만 기록.'
],
'opus':[
'부분 실행: 가상 산식 7개에 분모0·통화혼합·지연환불·역전 없는 대조 등 추가해 12개 점검. 전체 시장 방법론의 실증으로 세지 않음.',
'반영: M2.5와 계산 불가 사유 목록·지표 정의 초안 추가. 실 warehouse 스키마는 미확인.',
'수정 수용: 제공자가 지원하는 단위에서만 비교. 모든 채널에서 소재별 하단 지표가 불가능하다는 일반화는 채택하지 않음. 별도 캠페인도 청중/경매 교란이 남음.',
'수정 수용: 표본·기간·다중비교·희소결제/상위 결제자 민감도 기록. 부트스트랩 등 불확실성 계산 단위는 배정 단위와 의존성에 맞춰 선택; 항상 코호트 단위로 고정하지 않음.',
'반영: estimated/reported/settled, as_of, 환율·환불·순액 기준 및 IAA/IAP 분리. 실제 계약 요율은 미확인으로 둠.',
'반영: 제품 유형별 분기, 프리미엄의 가격/출시일/데모 공개/인증 일정 등 되돌리기 어려운 결정 분리.',
'반영: 소셜 밀도·매칭 대기·실력 차·봇/빈자리·그룹 간섭 보호지표 추가. 작은 테스트의 일반화 제한.',
'반영: 제작 역량/일정/런웨이/기술 위험과 지역·플랫폼 적용 항목을 초기 계약에 포함.',
'수정 수용: 창작 기둥 변경은 근거·결정 책임·잃는 타깃 기록. 미구현 훅은 제품에 구현하거나 소재에서 제외/수정; 아직 가설이면 개발 중 컨셉으로 구분.',
'반영: 최소 가설 카드·대표 구간·작은 지표표·결정 기록만 먼저. 자료 플랫폼 전체 신설은 제안하지 않음.',
'반영: 모집 기준·표본 출처·행동 과제·개발 중 표시·해당 매체 정책·동의/보존 범위 추가. 실제 참가자 연구는 미실행.',
'보고: 고정 기준의 근거 미확인과 GO/B 불일치를 원문 대조. 템플릿이나 공용 분석 규칙은 수정하지 않음.'
]}

def make_contracts():
    contract={'status':'DRAFT_NOT_AUTHORIZED_FOR_LIVE_SPEND','evidence_type':'proposal','product':None,'business_model':None,'audience':None,'country_platform':None,'decision_owner':None,'next_decision':None,'creative_pillars':[],
      'largest_uncertainty':'Choose one: audience promise, core experience, art readability/preference, production throughput, monetization, acquisition economics',
      'hypothesis':None,'competing_explanations':[],'promise_to_gameplay_mapping':[],
      'design':{'assignment_unit':None,'eligible_population':None,'assignment_before_product_exposure':None,'exposure_log':None,'primary_metric':None,'guardrails':[],'minimum_meaningful_effect':None,'sample_duration_budget':None,'stopping_rule':None,'analysis_population':None,'exclusions_before_results':[],'multiple_comparison_plan':None,'confirmatory_sample':None},
      'data':{'rules_view':None,'log_spec':None,'source_tables':None,'cost_source':None,'available_attribution_grain':None,'metric_definition_version':None,'privacy_and_retention_basis':None},
      'decisions':['adopt','reject','inconclusive'],'execution':'No live advertising, recruitment, warehouse query or product changes executed. Population and budget must be set for any such action.'}
    (ROOT/'market-experiment-contract.json').write_text(json.dumps(contract,indent=2),encoding='utf8')
    registry={'status':'PROPOSED_NOT_TEAM_RULES','official_rules_loaded':False,'timezone':None,'currency_and_fx_policy':None,'retention_definition':None,'attribution_window':None,'revenue_basis':None,
      'metrics':[
      {'id':'cpi','numerator':'eligible matched acquisition spend','denominator':'attributed installs or first_opens as explicitly defined','grain':'supported cohort/campaign/window','invalid':'denominator <= 0 => undefined; no arbitrary unknown allocation'},
      {'id':'dN_retention','numerator':'unique eligible mature users satisfying chosen return definition','denominator':'eligible users whose N-day observation is complete','grain':'assignment/cohort with population definition','invalid':'all immature or missing => unobserved, not zero'},
      {'id':'observed_dN_roas','numerator':'matched cohort revenue through N, declared gross/net and status','denominator':'matched acquisition cost','grain':'only identifiable common grain','invalid':'incompatible currencies, cohorts, windows or statuses cannot be silently pooled'},
      {'id':'contribution_before_ua','numerator':'settlement-consistent net receipts minus variable service costs not already deducted','denominator':None,'grain':'matching product/cohort/window/as_of','invalid':'estimated receipts must remain labeled estimated'},
      {'id':'contribution_after_ua','numerator':'contribution_before_ua minus acquisition spend','denominator':None,'grain':'matching cohort or explicit product P&L','invalid':'not net company profit; fixed creation/operations cost still separate'},
      {'id':'incremental_cpa','numerator':'eligible experimental acquisition spend','denominator':'positive causal incremental conversions under identified design','grain':'randomization/interference unit','invalid':'unidentified/nonpositive lift => no meaningful positive iCPA'},
      {'id':'content_throughput','numerator':'accepted engine-integrated playable content units','denominator':'elapsed interval; separately labor hours','grain':'content type/complexity','invalid':'generated candidates are not accepted output'}],
      'revenue_record_fields':['product','cohort_or_calendar_basis','window','as_of','currency','fx_policy','revenue_stream_IAA_or_IAP','revenue_status_estimated_reported_settled','gross_or_net','deductions_already_applied','refund_reference','data_source'],
      'connection_layers':['internal concept/design/art/creative/build version map','permitted first-party assignment/exposure/events','platform-provided attributed aggregates','media cost and settlement ledgers'],
      'rule':'Join only supported matching grains; aggregate before joining to avoid multiplication. This draft does not modify analytics/CLAUDE.md or warehouse rules.'}
    (ROOT/'market-metric-definitions.json').write_text(json.dumps(registry,indent=2),encoding='utf8')

def main():
    make_contracts()
    evidence=[]
    for path,start,end,claim in EVIDENCE:
        file=REPO/path;raw=file.read_bytes();lines=raw.decode('utf-8-sig').splitlines()
        assert end<=len(lines)
        evidence.append({'path':path,'line_start':start,'line_end':end,'claim':claim,'sha256':hashlib.sha256(raw).hexdigest(),'excerpt':'\n'.join(f'{i+1}: {lines[i]}' for i in range(start-1,end))})
    sql=(REPO/'design_standard/puzzle/schema/rawdata-schema.sql').read_text(encoding='utf8')
    assert 'campaign_id' not in sql and 'creative_id' not in sql
    evidence.append({'path':'design_standard/puzzle/schema/rawdata-schema.sql','claim':'Full local text contains neither campaign_id nor creative_id. No claim about production warehouse.','search':{'campaign_id':False,'creative_id':False}})
    images=[]
    for name in ['wind-ronin-front.png','v29-front.png','v29-three-quarter.png','v29-JointTest.png']:
        path=REPO/'tools/projecthub-web/public/asset-studio'/name
        images.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'reviewed':'static image inspected; not model runtime or audience preference test'})
    (ROOT/'market-local-evidence.json').write_text(json.dumps({'document_evidence':evidence,'image_evidence':images,'production_data_queried':False},ensure_ascii=False,indent=2),encoding='utf8')
    metrics=base.read(ROOT/'market-metric-checks.json')
    reviews={m:base.read(ROOT/f'runs/market-review-{m}/answer.txt') for m in ['astra','opus']}
    parts=['<header><p class="eyebrow">2026-10-05 · 앞선 코드 검증을 기획·아트·시장 대응으로 확장</p><h1>만들 수 있는 게임에서<br>시장에서 지속 가능한 게임으로</h1><p class="lead">다음 검증 단위는 “제품 가설 + 실제 플레이 + 핵심 아트 + 유입 약속 + 관측 결과”다. 기획·아트·UA의 개별 완성도 점수를 더해 성공을 판정하지 않는다.</p><p>이번 결과: 로컬 문서 대조, 아트 한 샘플의 이미지 4장 관찰, 공식 1차 자료 11개 대조, Astra/Opus 독립 비평 21개, 가상 산식 12개 점검. 실제 유저·광고·코호트 시장 실증은 없다.</p><p><a href="report.html">앞선 기술/코드 검증 보고서</a></p></header>']
    parts.append(section('판정과 범위',p('앞선 코드 생성 비교는 기획 품질·아트 적합성·UA 효율·사업 성공을 입증하지 않는다. 기술 완성, 타깃이 원하는 경험, 전달/발견성, 수익과 비용의 지속 가능성은 연결되지만 서로 다른 증거가 필요하다. 시장 적합성은 한 번의 합격증이 아니라 제품·유입·경쟁 조건이 달라질 때 다시 확인해야 하는 가설이다.')+table(['이번에 확인한 것','확인하지 않은 것'],[
 ('기획/아트/분석/사업평가 문서 간 일치와 공백','실제 타깃 게임의 수요·유지·LTV·ROAS·수익성'),
 ('아트 한 캐릭터의 원화/정면/사선/동작 정지 렌더','전체 아트 자산·리그 실행·엔진 성능·타깃 선호'),
 ('공식 문서의 귀속·시험·노출·제작 사례','특정 시장의 최신 장르 벤치마크나 성공률'),
 ('가상 숫자의 산식/경계/역전 사례 12개','회사 데이터에 대한 추출·인과 효과·매체 정산'),
 ('두 모델의 독립 비평과 21개 지적 처리','두 모델 의견 일치에 의한 사실 인증')])+p('여기서 “전수”는 아래 작업 영역·단계·반대론·지적 목록 안에서 빠짐없이 대조했다는 뜻이다. 모든 게임·지역·시장 실패를 망라하거나 성공을 보장했다는 뜻이 아니다. 특정 게임/국가/플랫폼/예산이 없으므로 임의의 업계 합격선을 넣지 않았다.')))
    parts.append(section('로컬 자료에서 확인한 공백과 충돌',table(['발견','근거','의미'],[
 ('기획 품질과 시장 성과를 분리하는 원칙은 이미 있음','proposal/workflow/AI_workflow_기획_v2.0.md:1024,1031,1072','보존해야 할 원칙. 예시 KPI를 실측으로 읽거나 시장 성과 등급을 원인으로 읽으면 안 됨.'),
 ('임베딩 자료실의 기획 본문 수집은 확인되지 않음','output/asset-library-v2/SCHEMA.json:65','기획·과거 의사결정까지 RAG가 제공한다고 주장할 수 없음.'),
 ('아트 기술 통과와 최종 승인은 다름','tools/asset-studio/README.md:7 / STYLE_ITERATIONS.ko.md:37,39','생성/패키징 성공을 엔진 납품·디렉션·시장성 통과로 승격하지 않음.'),
 ('로컬 UA 연결 키 미반영','analytics/로그요청서_초안.md:40,129 / rawdata-schema.sql 전체 검색','공용 SQL에 campaign_id/creative_id 없음. 실제 운영 스키마도 같다는 뜻은 아님.'),
 ('게임 내 광고 로그 ≠ 유입 비용 원장','design_standard/puzzle/schema/rawdata-schema.sql:209','rewarded/interstitial 시청 기록만으로 소재별 광고비·설치 귀속을 계산할 수 없음.'),
 ('실제 추출 전제 미정','analytics/CLAUDE.md:31-36','게임 프로젝트·규칙 view·로그 명세·staging을 추측하지 않음. 이번 실제 warehouse 조회 없음.'),
 ('보편 근거 없는 사업 합격선',' .claude/agents/reviewer-business.md:91,95,99,100','1.5배 LTV/CPI, 2년 운영, 1.2배 콘텐츠 능력, 월50레벨을 모든 게임에 강제할 근거 미확인.'),
 ('사업 판정 문구 내부 충돌',' .claude/agents/reviewer-business.md:175 vs :293-294','동일 Gate 통과와 B 평가에서 앞은 GO, 뒤는 CONDITIONAL. 자동 출시 판정에 그대로 쓰면 안 됨.')])+p('사업 평가 템플릿은 이번에 실행 지침으로 호출한 것이 아니라 검토 대상으로 읽었다. 최신 사용자 요청인 근거 대조를 우선했으며, 공용 규칙과 템플릿 원문은 수정하지 않았다. analytics README에 적힌 과거 PC 설치 상태를 오늘의 상태라고 단정하지 않았다.')+'<p><a href="market-local-evidence.json">파일:행·원문 발췌·SHA-256·이미지 기록</a></p>'))
    parts.append(section('성공 정의와 제품 가설을 먼저 통일한다',p('공동 가설 카드에는 ① 타깃의 상황/욕구 ② 핵심 감정과 플레이 ③ 대체재와 차별점 ④ 아트·스토어·광고의 약속 ⑤ 실제 첫 경험과 장기 가치 ⑥ 가격/과금/광고 수용 이유 ⑦ 제작·유입·운영 비용과 회수기간 ⑧ 반증/중단 조건을 적는다. 성공을 대형 매출 하나로 고정하지 않고 팀의 목표·규모·회수 조건과 연결한다.')+p('창작 기둥—예를 들어 느린 탐험, 공정한 경쟁, 편안한 퍼즐—과 변경 가능한 표현—첫 화면, 설명, 소재 편집—을 구분한다. UA 지표가 창작 기둥 변경을 제안하면 제품 책임자가 근거, 예상 행동 변화, 잃는 타깃, 기각 조건을 기록한다. 단기 반응을 위해 모든 제품이 같은 모습으로 수렴하도록 만들지 않는다.')+refs(0,2)))
    parts.append('<section><h2>서로 연결해서 확인할 흐름</h2><div class="flow">시장/타깃 가설 → 기획·아트·실제 플레이 ↔ 소재·스토어의 약속<br>↓<br>발견·유입 → 첫 경험 → 반복/만족 → 수익·비용·회수<br>↓<br>계측 대조 → 경쟁 설명 → 제품/표현/유입 수정 → 재확인</div><p>화살표는 설계할 정보 연결이며 이미 동작하는 분석 시스템이라는 뜻이 아니다. 기능 제작과 유입 표현을 함께 검증하되 효과를 분리할 수 있도록 실험을 설계한다.</p></section>')
    parts.append(section('실제 실행 절차와 담당',table(['단계','담당','산출물/행동','통과 근거 또는 반론'],STAGES)+refs(0,3,5,7,8)))
    parts.append(section('기획을 어떻게 검증할 것인가',table(['기획 주장','교차 확인','반대 증거/오판 방지'],[
 ('타깃이 이 욕구를 갖는다','타깃 기준을 사전 정의하고 현재 대체재/불만/실제 선택을 확인','직원·기존 팬의 긍정 응답, 인기작의 특징만으로 수요를 확정하지 않음'),
 ('핵심 루프가 재미있다','실제 플레이에서 선택 이해·학습·행동·실패 복구·자발적 반복과 설명을 함께 관찰','문서 정합·AI 플레이 성공·설문 호감이 재미의 충분조건은 아님'),
 ('장기 목표/콘텐츠가 유지시킨다','해당 제품의 충분한 경험 구간, 콘텐츠 소진, 진행 동기, 유입별 이탈을 관찰','D1만으로 장기 유지 판정 금지; 소셜 게임은 매칭 밀도/동료 경험도 확인'),
 ('경제와 수익 구조가 지속 가능하다','불변식/악용 시뮬레이션 + 실제 제안/광고 경험에 대한 행동과 보호지표','AI 시뮬레이션을 인간 지불 의향으로 간주하지 않음; 매출 증가가 만족 하락을 숨길 수 있음'),
 ('후속 업데이트가 문제를 해결한다','변경 전 예상 행동·주요지표·경쟁 설명을 기록하고 별도 확인','하락 후 반등을 곧바로 패치 효과로 단정하지 않음')])+p('기획·아트·코드·콘텐츠 한 단위가 실제 납품되기까지의 병목도 기획 실현성에 포함한다. 복잡한 경제/서사/캐릭터 수를 늘릴 때 승인 생산량과 수정 비용이 감당 가능한지 확인한다.')))
    art='<div class="artgrid">'
    for name,label in [('wind-ronin-front.png','목표 원화'),('v29-three-quarter.png','v29 사선 렌더'),('v29-JointTest.png','v29 동작 정지 렌더')]:
      art+=f'<figure><img src="../../tools/projecthub-web/public/asset-studio/{name}" alt="{label}"><figcaption>{label}</figcaption></figure>'
    art+='</div>'
    parts.append(section('아트: 원화·플레이·유입·납품을 따로 평가한다',table(['축','실제 검사','혼동하면 안 되는 것'],[
 ('디렉션/브랜드','실루엣·색/명암·재질·캐릭터·UI·VFX·애니메이션·사운드의 일관성과 금지 사례','원화 한 장의 아름다움 ≠ 전체 제품의 일관성'),
 ('게임 내 기능','작은 화면/움직임/저사양/대비에서 정보·적/아군·상호작용을 읽는지','고해상도 정면 유사도 ≠ 실제 가독성'),
 ('타깃 매력','제시 순서/명칭 영향을 줄인 비교와 선택 이유, 실제 플레이 후 반응','모델의 미적 점수 ≠ 타깃 선호'),
 ('유입/기대 전달','소재·스토어를 보고 예상한 경험과 실제 게임의 일치','높은 CTR ≠ 적합한 유저/유지/기여'),
 ('생산/운영','원화→모델/리그/애니메이션→엔진 통합→플레이 검수까지 승인 납품량·재작업·대기·권리/출처','생성 후보 수 ≠ 생산 능력; 종류/난도별로 측정')])+art+p('직접 관찰한 범위: 위 원화와 v29 정면·사선·동작 PNG 총4장, 캐릭터1개. 색·의상 구성은 대응하지만 3D 렌더의 손가락 윤곽은 원화보다 덩어리져 보이며 세부 표현이 다르다. 촬영/배경/장비 차이가 있어 픽셀 점수나 품질 백분율은 계산하지 않았다. 이 관찰은 문서의 손 형태 후속 수정 필요와 부합한다.')+p('이 샘플로 전체 아트 자료실 품질, 목표 플레이어 취향, 게임 카메라에서의 가독성, 움직이는 리그/충돌, 실제 엔진 성능을 판정하지 않았다. 시각 자료는 저장된 렌더이며 이번에 3D 파이프라인을 재실행하지 않았다. 애니메이션·오디오·내러티브 전체 검수도 미실시다.')+refs(1)))
    parts.append(section('UA와 제품 효과를 분리하는 실험',p('소재 A와 B가 서로 다른 사람을 설치시켰다면 설치자끼리 D7을 비교한 결과는 소재 표현과 유입 선택 효과가 섞인다. 제품이 설치 후 어떻게 작동했는지를 볼 수는 있지만 소재의 순수 인과 효과로 읽을 수 없다. 소재 실험은 배정/노출부터의 전체 성과와 설치자 조건부 성과를 나눠 보고, 제품 실험은 적격 유입에서 제품 노출 전에 배정한다.')+table(['시험 질문','설계 원칙','최소 보고'],[
 ('어떤 표현이 적합한 타깃을 데려오는가','같은 제품·기간·모집 조건에서 소재 비교. 플랫폼 자동 최적화 배분이면 관찰 비교로 명시','노출/배정 수→방문→설치/구매의 전체 결과 + 설치자 조건부 행동, 비용, 귀속 한계'),
 ('게임 변경이 경험/수익을 개선하는가','제품 노출 이전의 적격 집단에서 배정, 배정과 실제 노출 로그 분리, 제외 기준 사전 고정','배정군 기준 주 분석, 노출/탈락·충돌·유지·수익 보호지표. 참여/생존자만 골라 비교하지 않음'),
 ('광고가 새 결과를 만들었는가','자격·규모가 되면 식별 가능한 holdout/지역 설계. 네트워크/지역 간 간섭 확인','귀속 수치와 증분 추정 분리, 불확실성·식별 가정·기간 명시'),
 ('정말 확장 가능한가','예산/청중 범위를 늘릴 때 추가 비용과 결과를 관찰','평균과 한계 성과, 소재 피로·빈도·지역/유입 믹스, 회수 위험')])+p('표본·기간·경제적으로 의미 있는 차이·주요지표·중단 규칙을 결과 전에 고정한다. 성숙 코호트라는 이유만으로 표본이 충분한 것은 아니다. 희소 결제는 결제자 비율과 결제자당 수익, 상위 결제자 민감도와 불확실성을 함께 본다. 상위 결제자를 사후 삭제해 주 분석을 바꾸지 않고 별도 민감도 결과로 표시한다. 다수 후보 탐색의 승자는 별도 확인 표본에서 검증한다.')+p('매출이 일정 시점에 좋거나 나쁘다고 매일 시험을 자르면 선택 편향이 생길 수 있다. 고정 관측 계획 또는 사전에 정한 순차 방법을 쓴다. 결론은 채택/기각/판단 불가 중 하나이며, 표본 부족을 실패로 둔갑시키지 않는다. 작은 팀은 다요인 실험보다 다음 결정을 바꾸는 가장 큰 불확실성 한 가지에 집중한다.')+refs(3,4,7,8)))
    parts.append(section('성과 산식과 계측 경계',p('동일한 수익/비용 정의와 관측 범위에서 순수입 = 정산 기준 수입에서 아직 반영되지 않은 환불·세금·수수료 등을 반영한 값으로 정의한다. 실제 보고서가 이미 net이면 같은 비용을 다시 빼지 않는다. UA 전 기여 = 순수입 − 아직 차감하지 않은 변동 서비스비. UA 후 기여 = UA 전 기여 − 유입 비용. 여기서 제작비·고정 운영비 회수와 회사 전체 손익, 현금 입출금 시점은 별도로 연결한다. 모든 지표에 적용되는 단일 수수료율은 넣지 않는다.')+p('관측 Dn ROAS = 같은 코호트/관측창의 정의된 수익 합 ÷ 대응 유입비 합. 단순 평균 ROAS나 서로 다른 통화·귀속창·성숙도의 합산을 피한다. IAP와 IAA를 분리하고 합계도 표시한다. 수익 상태 estimated/reported/settled와 as_of, 환불 반영 시점을 보존한다. D30 관측값을 lifetime이라고 부르지 않고 예측 LTV는 오차/가정/시나리오를 붙인다.')+p('인과 해석에는 추가 조건이 필요하다. 관측 귀속 ROAS와 회사 전체 사업 성과, 증분 효과를 다른 칸에 둔다. 집계 날짜가 비용 발생일인지 설치일인지 매출 발생일인지 다르면 키 이름이 같아도 직접 조인하지 않는다. 비용 원장을 유저별 로그에 붙여 합하면 비용이 반복 집계될 수 있다.')+p('내부 concept/design/art/creative/build 관계표는 자산 버전을 연결한다. 허용된 first-party 이벤트, 매체가 제공한 집계 귀속, 유입비/정산은 각자 지원되는 수준으로 보존한다. 어떤 제공자는 소재별 하단 지표를 제공할 수 있고 어떤 조건에서는 불가능하다. 계산 가능한 최소 단위를 먼저 확인하며 unknown을 억지로 개인/소재에 배분하지 않는다.')+refs(3,6,9)))
    parts.append(section('가상 산식 12개를 실행한 결과',p('아래 숫자는 모두 만든 예시다. 특정 게임·매체·소재의 성과나 업계 기준이 아니다. 실행 전 코드에 기대 관계/값을 넣어 계산했고 12개 점검을 통과했다. 산식과 반례를 확인한 결과이며 시장 실험의 재현이나 방법론 전체 검증이 아니다.')+table(['예시','계산 결과','판단'],[
 ('같은 광고비1,000: A 설치1,000 / B 설치500','CPI A1 / B2; D7 복귀50/150 → 복귀자당 비용20/6.67','낮은 CPI A가 후속 품질/비용에서 질 수 있음'),
 ('위 가상 코호트의 D30 UA 전 기여600/1,200','UA 후 기여 A−400 / B+200','D30 관측 예시이며 lifetime·회사 순이익은 아님'),
 ('비용100/900, 대응 수익100/90','단순 평균 ROAS55%, 합계 기준19%','분모 가중이 중요'),
 ('D7 성숙100명 복귀40, 미성숙100명','성숙 분모40%, 미성숙 포함 오류20%','아직 관측 안 된 유저를 실패로 세지 않음'),
 ('지역별 A가 앞서도 유입 믹스가 다름','전체 A18% / B77%; 같은50:50 믹스 A50% / B45%','표준화는 믹스 설명이며 단독 인과 증명은 아님'),
 ('동일 규모 가상 무작위군 200 vs160 전환, 비용200','점추정 증분40 → iCPA5; 귀속120이면 CPA1.67','귀속과 증분은 다름. 이 예시에 실제 실험/신뢰구간 없음'),
 ('gross100, 환불10, 명시 수수료27, net63, 변동비8','gross에서 계산해도 net에서 계산해도 UA 전 기여55','이미 net인 수입에 중복 공제 금지'),
 ('캠페인 비용100을 유저3행에 조인','잘못된 합300, 올바른 비용100','집계 단위/중복 점검'),
 ('분모0·전원 미성숙·비양수 증분','지표 undefined','0성과나 유효한 양수 획득 단가로 표시하지 않음'),
 ('USD와 KRW 혼합','환율 정책 없는 합산 거부; 동일통화 대조는 통과','실제 환율을 발명하지 않음'),
 ('원 코호트 수입100, 뒤늦은 환불20','동일 창 정정값80과 최초 as_of값100 둘 다 보존','시점/정정 기준을 맞춰 비교'),
 ('역전이 없는 대조 예시','동일 비용이면 평균과 합계 ROAS 일치; 낮은 CPI가 후속 성과도 우수한 예시 통과','저CPI 자체가 나쁘거나 단순 평균이 항상 틀린 것은 아님')])+'<p><a href="market-metric-checks.json">모든 입력·출력·한계</a> · <a href="../../tools/asset-library/market-metric-check.py">실행 코드</a></p>'))
    parts.append(section('제품 유형별로 생략·강조할 것',table(['유형','성공/핵심 증거','그대로 강제하지 않을 것'],[
 ('모바일 F2P','초기 경험→유지→IAA/IAP·순기여·회수, 유입 확장과 콘텐츠/운영 능력','임의 CPI/D1/LTV 배수·월 콘텐츠 개수'),
 ('프리미엄 PC/콘솔','완결된 경험, 데모/발견성·구매·환불·순판매·제작비 회수, 가격·발매 시기·플랫폼 일정','모든 게임의 장기 D30 유지·2년 LiveOps·상시 유료 UA'),
 ('소셜/경쟁/협동','모집 밀도·매칭 대기/실력차·봇/빈자리·그룹 경험·권한·운영비','개별 유저만 독립이라고 가정한 작은 실험, 빈 서버 성과의 전체 시장 일반화'),
 ('작은 팀/틈새','가설 카드+대표 경험+소수 표현+작은 지표표+결정 기록. 다음 결정을 바꿀 불확실성 하나','전용 데이터/에이전트 플랫폼·다수 국가/소재/요인을 한 번에 구축'),
 ('혼합 모델','관련 경로 조합, 각 수익원/플랫폼/타깃별 정의','합산 평균으로 서로 다른 경제 구조의 손실을 숨김')])+p('UA는 유료 설치 광고만이 아니다. 스토어·데모·커뮤니티·크리에이터/방송·PR·추천도 제품에 맞는 발견 경로다. 자연 유입에도 콘텐츠·관계·운영 비용은 있다. Steam 위시리스트는 관심/알림에 유용하지만 자동 노출이나 매출 보증으로 쓰지 않는다. 스토어 시험과 매체 측정 기능은 각 플랫폼의 실제 자격/정책/창을 확인한 뒤 적용한다.')+refs(5,9,10)))
    parts.append(section('반대론을 받아들인 결정 규칙',table(['반대론','인정할 부분','실무 대응'],[
 ('시장 데이터가 창의성을 죽인다','짧은 시험이 느린 탐험·틈새 취향·새 장르를 조기 탈락시킬 수 있음','창작 기둥/충분 경험/탐색 예산을 보존하고 표현 실패와 경험 실패 분리'),
 ('기획·아트·UA를 갖추면 성공한다','필요 역량을 갖춰도 경쟁·시점·실행·확장 불확실성은 남음','특정 제품/버전/유입 조건에서 조건부 투자 판단; 성공 보장/확률 발명 금지'),
 ('CPI 낮은 훅에 게임을 맞추면 된다','주목을 끄는 표현과 실제 타깃 경험이 다를 수 있음','기대 전달·유입 후 행동·기여 확인. 미구현 약속은 구현/수정/제외 결정'),
 ('AI 기획·아트 평가로 충분하다','후보 생성/정합 검토는 가능하나 실제 타깃 취향을 대체했다는 증거 없음','모델 점수는 참고, 행동·디렉션·권리·엔진 납품 별도'),
 ('리텐션 좋으면 BM은 나중에 붙인다','가격/광고/보상 변경이 경험을 바꿀 수 있음','이른 수익 가설 확인과 만족/유지 보호지표; 단기 매출 극대화 강요는 아님'),
 ('실험을 많이 하면 정답에 도달한다','표본 분산·다중비교·조기 중단·승자 과대평가가 생김','주요질문/표본/중단 사전 확정, 별도 확인, 판단 불가 허용'),
 ('절차/원장 비용이 제작을 잡아먹는다','현재 방식보다 좋은 결정을 더 싸게 낸다는 실증은 아직 없음','필드마다 바꾸는 결정을 적고 필요 없는 수집/플랫폼은 미룸'),
 ('과거 성공게임의 자료가 정답이다','생존자 편향·시대·국가·채널·원인 혼동 위험','실패/조건/날짜/반례 포함. 시장 등급·원인 가설은 원문/실증과 분리'),
 ('UA는 출시 직전에 시작하면 된다','제품이 없을 때 매출 효과를 확인할 수 없는 것도 사실','초기에는 약속/발견성 탐색, 제품/계측 준비 뒤 실제 확장 판단'),
 ('데이터 연결을 정교하게 하면 판단도 정확해진다','귀속이 제한되고 표본이 작으면 정밀해 보이는 잡음일 수 있음','식별 불가/결측/불확실성을 그대로 보이고 증거가 결정에 주는 가치부터 검증')])+p('가장 강한 반론은 이 통합 절차도 아직 검증되지 않은 가설이라는 점이다. 빠른 프로토타입과 책임 있는 디렉션보다 더 좋은 투자 판단을 만드는지 확인해야 한다. 적용 후 “어떤 결정을 바꿨고, 얼마의 검증 비용을 썼으며, 이후 결과가 어땠는가”를 기록한다.')))
    parts.append(section('임베딩의 다음 역할과 최소 다음 작업',p('추천 순서: ① 타깃/제품 가설과 결정 책임 ② 약속을 전달하는 실제 플레이·아트·소재/스토어 패키지 ③ 필요한 계측 정의와 접근 전제 ④ 타깃 시험/지원되는 단위의 성과 연결 ⑤ 실패가 확인된 지점의 자료 검색 개선. 예쁜 자산/성공작 문서를 더 모으는 것만으로 시장 대응 능력이 생기지는 않는다.')+p('원문 기획·수정 이유·아트 바이블·소재 버전/약속·실험 조건·관측 성과·실패/판단 불가를 연결해 저장한다. 원문/이미지/영상 저장소, 숫자·비용·실험 원장, 버전 관계, 의미 검색을 구분한다. 숫자의 합계·코호트 계산은 정의된 집계로 수행하고 RAG는 근거를 찾아 설명하는 데 쓴다. 모든 데이터를 먼저 새 플랫폼으로 옮길 필요는 없다.')+p('최소 실제 제품 시험은 “한 타깃·한 제품 약속·그 약속을 보여주는 소재/스토어 샘플·짧은 플레이 구간”을 묶어, 기대한 경험과 실제 행동/평가가 맞는지 확인하는 것이다. 이는 시장 수요나 LTV 시험이 아니라 약속/경험의 초기 검증이다. 다음으로 가장 큰 미확인 항목 하나만 정량 시험한다. 유료 예산·모집·공개는 이번에 실행하지 않았다.')+'<p><a href="market-experiment-contract.json">다음 실험 계약 초안</a> · <a href="market-metric-definitions.json">지표/원장 정의 초안</a></p>'+p('실데이터 추출의 남은 입력: 게임 프로젝트 ID, 팀 규칙 view, 실제 로그 요청서, staging/원천 테이블, UA 비용/귀속/정산 출처, 대상 기간·지역·플랫폼·질문. analytics/CLAUDE.md:36의 “이 표에 <미정>이 하나라도 남아 있으면, 추출을 시도하지 말고 무엇이 없어서 못 하는지 먼저 말할 것”에 따라 실제 warehouse 조회를 하지 않았다. 이 지침은 문서 조사·가상 검산·초안 작성을 막지 않으므로 해당 작업은 완료했다.')))
    review_body=p('Astra와 Opus는 같은 초안을 서로의 답 없이 검토했다. 출처 원문과 실제 제품을 직접 검증한 모델 평가는 아니며, 본 작업자가 원문·로컬 파일·산식을 대조했다. 비평의 타당성도 판단해 아래처럼 채택/수정/미검증 상태를 구분했다.')
    disposition_records=[]
    for model,review in reviews.items():
        assert len(review['issues'])==len(REVIEW_DISPOSITIONS[model])
        rows=[]
        for issue,disposition in zip(review['issues'],REVIEW_DISPOSITIONS[model]):
            rows.append([issue['id'],issue['severity'],issue['claim'],disposition])
            disposition_records.append({'model':model,**issue,'disposition':disposition})
        review_body+='<h3>'+model+'</h3>'+table(['ID','심각도','검토 주장','처리/남은 증거'],rows)+f'<p><a href="runs/market-review-{model}/answer.txt">원문 비평</a> · <a href="runs/market-review-{model}/run.json">실제 호출 기록</a></p>'
    parts.append(section('독립 비평 21개 전체 처리',review_body))
    source_body=p('공식 제작사 사례와 플랫폼 문서를 직접 읽었다. 사례는 보편 성공법칙이 아니고 플랫폼 문서는 타깃 제품에 대한 매출 증거가 아니다. 최신 CPI/LTV 숫자나 표본 없는 업계 합격선을 인용하지 않았다.')
    for title,url,claim in SOURCES:source_body+=p(claim)+f'<p class="refs"><a href="{url}">{esc(title)}</a></p>'
    parts.append(section('공개 1차 근거 11개',source_body))
    parts.append(section('검증 명령과 완료 범위','<pre>'+esc("# E:\\AI, PowerShell\n$py = 'C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe'\n& $py tools/asset-library/market-metric-check.py\n# Synthetic metric counterexamples: 12 / 12 PASS; real market data: NONE\n& $py tools/asset-library/market-report.py\n# Market report: 21 critique issues; 12 synthetic checks; local links valid\n\nrg -n 'campaign_id|creative_id' design_standard/puzzle/schema/rawdata-schema.sql\n# No matches (local file only).\n# Model review exact commands are stored in runs/market-review-*/command.json")+'</pre>'+p('기존 코드 비교 결과는 그대로 보존했다. 변경 산출물은 추가 보고서·가상 검산·실험/지표 초안 및 로컬 근거 기록이다. 게임·아트 원본·공용 분석 규칙·광고 계정·운영 데이터·예산을 수정하지 않았다. 실제 시장 성공 판단과 사람 시험은 남아 있으며 이를 수행했다고 표시하지 않는다.')))
    css='body{margin:0;background:#f3f5f7;color:#183041;font:15px/1.8 system-ui,"Malgun Gothic",sans-serif}main{max-width:1200px;margin:auto;padding:30px 24px}header,section{background:white;border:1px solid #dce4eb;padding:25px 30px;margin-bottom:22px;border-radius:12px}h1{font-size:34px;line-height:1.4}h2{font-size:23px;color:#17566b}.lead{font-size:20px;font-weight:600}.eyebrow,.refs{font-size:13px;color:#536a7c}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #d9e3ea;padding:12px;text-align:left;vertical-align:top}th{background:#eef4f7}a{color:#15607e}pre{white-space:pre-wrap;background:#edf3f7;padding:16px;font-size:13px}p{overflow-wrap:anywhere}.flow{text-align:center;background:#e9f4f4;padding:22px;font-size:19px;line-height:2}.artgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.artgrid img{width:100%;display:block;background:#d9dfe3}.artgrid figure{margin:0}.artgrid figcaption{font-size:13px}@media(max-width:700px){main{padding:12px}header,section{padding:18px}.artgrid{grid-template-columns:1fr}}@media print{body{background:white}section,header{border:0;padding:12px 0}tr{break-inside:avoid}}'
    doc='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>기획·아트·UA·시장 대응 교차 검증</title><style>'+css+'</style></head><body><main>'+''.join(parts)+'</main></body></html>'
    (ROOT/'market-report.html').write_text(doc,encoding='utf8')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.values=[]
        def handle_starttag(self,tag,attrs):self.values.extend(v for k,v in attrs if tag in ('a','img') and k in ('href','src'))
    parser=Links();parser.feed(doc)
    local=[x for x in parser.values if not x.startswith(('https://','http://','#'))]
    missing=[x for x in local if not (ROOT/x).is_file()]
    assert not missing,missing
    result={'date':'2026-10-05','critique_issues':len(disposition_records),'synthetic_checks':metrics['passed'],'local_links_valid':len(local),'sources':SOURCES,'dispositions':disposition_records,'real_market_data':False,'art_scope':'one character, four static images','scope':'bounded document/evidence/math review, not validated product success'}
    (ROOT/'market-review-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(f'Market report: {len(disposition_records)} critique issues; {metrics["passed"]} synthetic checks; {len(local)} local links valid')

if __name__=='__main__':main()
