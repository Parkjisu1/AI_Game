"""Render the measured pilot and the bounded production-method review as HTML."""
import html
import json
import pathlib
import re

ROOT=pathlib.Path('E:/AI/output/embedding-eval-20261005')
def read(path):
    text=path.read_text(encoding='utf8').strip()
    return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text))
def esc(value):return html.escape(str(value))
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def p(text):return '<p>'+esc(text)+'</p>'
def section(title,body):return '<section><h2>'+esc(title)+'</h2>'+body+'</section>'
SOURCES=[
('S1','OpenAI · Evaluation best practices','https://developers.openai.com/api/docs/guides/evaluation-best-practices','업무별 평가·기준선·사람 판단과의 교정을 권장. 이 보고서의 61개 테스트나 전체 게임 절차의 효과를 인증하지 않는다.'),
('S2','Anthropic · Demystifying evals for AI agents','https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents','실행 결과 평가, 반복 시험과 격리, 코드·모델·사람 판정의 조합을 설명. 공급자 방법론이다.'),
('S3','Anthropic · Effective harnesses for long-running agents','https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents','작은 기능 단위·진행 기록·종단 간 검증의 필요를 사례로 설명. 모든 게임 장기 제작에 대한 인과 실험은 아니다.'),
('S4','METR · Early-2025 developer productivity RCT','https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/','숙련 개발자 16명·246개 작업에서 당시 도구 사용 시 19% 더 오래 걸린 연구. 당시 성숙한 오픈소스 저장소 조건으로 제한한다.'),
('S5','METR · 2026-02-24 follow-up','https://metr.org/blog/2026-02-24-uplift-update/','후속 측정의 선택 편향·시간 측정 문제를 설명. 2025 수치를 현재 Astra/Opus 생산성으로 대입할 수 없다.'),
('S6','SlopCodeBench · arXiv 2603.24755','https://arxiv.org/abs/2603.24755','반복 요구 변경에서 코드 품질을 평가하는 연구. 단기 테스트 통과와 유지보수성 구분의 배경이며 이 게임 자료실의 효과를 측정하지 않았다.'),
('S7','Anthropic · Infrastructure noise','https://www.anthropic.com/engineering/infrastructure-noise','실행 자원·하네스 차이가 평가에 영향을 줄 수 있음을 설명. 이번 시간 차이를 순수 모델 효과로 해석하지 않는 근거다.'),
('S8','Unity · Profiling on target devices','https://docs.unity3d.com/6000.0/Documentation/Manual/profiling-target-device.html','실제 대상 플랫폼·기기에서 프로파일링하는 방법. Editor 결과만으로 실기기 성능을 대신하지 않는다.'),
('S9','Unity · Run builds','https://docs.unity.com/en-us/build-automation/run-builds','대상 플랫폼 빌드 자동화 방법. 자동 빌드 성공이 플레이 품질이나 출시 인증은 아니다.'),
('S10','Android · Technical quality','https://developer.android.com/quality/technical','안정성·성능·리소스 사용의 기술 품질 지침. 모든 장르에 동일한 FPS나 메모리 수치를 강제하는 근거로 쓰지 않는다.'),
('S11','Unity · Server authority','https://docs.unity.com/en-us/cloud-code/server-authority','중요 상태와 검증을 서버 권한으로 관리하는 접근. 모든 부정행위 방지나 오프라인 게임의 서버 도입을 뜻하지 않는다.'),
('S12','Xbox Accessibility Guidelines','https://learn.microsoft.com/en-us/xbox/accessibility/guidelines','게임 접근성 모범사례. 법률 준수나 플랫폼 인증 체크리스트 전체를 대신하지 않는다.'),
('S13','Steam · Playtest','https://partner.steamgames.com/doc/features/playtest','실제 플레이어 테스트를 운영하는 수단. 테스트 참여나 호평만으로 시장 성공을 보장하지 않는다.'),
('S14','Steam · Release process','https://partner.steamgames.com/doc/store/releasing','스토어·빌드 검토 및 출시 절차. 다른 플랫폼·지역의 요구는 별도 확인해야 한다.')]
def refs(*ids):
    return '<p class="refs">근거: '+', '.join('<a href="'+s[2]+'">'+esc(s[1])+'</a>' for s in SOURCES if s[0] in ids)+'. 아래 단계 구성과 우선순위는 이 자료 및 로컬 관찰에 대한 작성자의 제안이다.</p>'

GATES=[
('G0 제품 계약','제품 책임자','핵심 경험·타깃 플레이어·플랫폼/입력·최소 기기·콘텐츠/동시성 상한·수익 방식·예산·기한·제외 범위를 정한다. 기술 출시 가능성, 경험 적합성, 사업 투자 지속을 별도 판정한다.','관찰 가능한 인수 기준, 지원 범위, 출시 차단 결함, 재미/수요 가설의 반증 조건, 중단 기준. 미정인 필수 기준이 있으면 다음 단계의 완료 판정을 하지 않는다.'),
('G1 재현 가능한 기반','엔진/빌드 담당','엔진·패키지·SDK 버전과 소스/에셋/meta/GUID를 고정하고 깨끗한 체크아웃에서 빌드한다. 현재 저장소와 자료실 스냅샷의 차이를 표시한다.','버전 manifest, 재현 빌드 로그, 에셋 출처/사용권 목록, 기존 프로젝트 기준선. 자동 빌드 성공은 기반 증거다.'),
('G2 핵심 위험 시제품','기술·기획 담당','가장 불확실한 기술과 재미 가설을 먼저 시험한다. 퍼즐은 해/막힘, 온라인은 지연/권한, 큰 월드는 스트리밍 등 실제 실패 가능성부터 다룬다.','실험 조건·성공/실패·비용·중단 이유. 버릴 수 있는 시제품을 제품 아키텍처 완성으로 세지 않는다.'),
('G3 대표 플레이 구간','통합·아트·플레이테스트 담당','시작→핵심 플레이→승패→보상→저장→종료/재실행을 연결한다. 대표 아트/UI/오디오를 최종 품질에 가깝게 제작하고 대상 기기의 Player 빌드에서 플레이한다.','동작 영상/로그, 프로파일, 저장 복구 결과, 타깃 플레이어 관찰. 한 자산의 제작 시간을 전체 콘텐츠 생산성으로 일반화하지 않는다.'),
('G4 기능별 작업 계약','기능 소유자','요구사항 ID, 수정 범위, API/이벤트/데이터, 씬·프리팹 연결, 수명주기·취소·재시도, 성능 예산, 회귀 사례를 작은 작업 패키지로 전달한다.','입출력·실패 조건·인수 테스트·변경 영향·출처·롤백 경로를 버전 관리. 필요한 근거가 없으면 추측한 API를 제품에 확정하지 않는다.'),
('G5 구현·독립 검증·통합','구현 담당 + 검증 책임','컴파일·단위/속성/상태전이→엔진 통합→Player→실기기 순서에서 변경에 필요한 검사를 선택한다. 생성자가 인수 기준을 임의로 바꾸지 못하게 한다.','검사 결과와 계약 ID 대응, 실패 재현, 리뷰/수정 이력. Unity의 EditMode/PlayMode는 이 저장소용 예시이며 다른 엔진은 대응 도구를 쓴다.'),
('G6 콘텐츠·규모 확장','콘텐츠/성능 담당','레벨·캐릭터·퀘스트·경제·아트를 확장하며 실제 수량·동시성·세이브 크기를 증가시킨다. 후속 요구 변경을 넣어 구조의 수정 비용을 관찰한다.','콘텐츠 스키마/참조 검사, 병목 추세, 제작·수정 시간, 경제/저장 회귀. 두세 기능 성공은 충분조건이 아니라 초기 관찰이다.'),
('G7 출시 후보 판정','QA·제품·전문 검토 책임','지원 기기/OS/GPU/입력/언어 매트릭스, 긴 플레이, 프레임타임·메모리·발열·로딩, 강제종료/저장복구, 업데이트, 해당 SDK/보안/접근성/스토어 항목을 검증한다.','사전 기준에 대한 통과/실패/미검사, 치명 결함, 잔여 위험과 승인 기록. 미검사는 통과가 아니다. 코드·콘텐츠·설정·스키마·서비스 버전을 함께 식별한다.'),
('G8 출시·운영·복구','출시/운영 책임','제품에 맞는 테스트 채널과 단계적 확대를 선택한다. 경보→담당자→복구를 연결하고 이전 버전 데이터와 혼합 서비스 버전의 호환을 시험한다.','출시한 묶음과 검증한 묶음의 일치, 실제 복원 리허설, 복구 후 정합성, 이후 회귀. 바이너리 롤백만으로 데이터 변경이 되돌아간다고 가정하지 않는다.')]

GENRES=[
('퍼즐·매치·보드','해 존재·막힘·난수 seed·힌트·특수기믹 조합·난도 분포','솔버의 성공이 사람에게 재미있음을 증명하지 않음'),
('방치·경제·수집 RPG','오프라인 시간·시간 변경·큰 수·경제 순환·중복 보상·저장 마이그레이션','수치 시뮬레이션만으로 실제 유저 경제를 예측할 수 없음'),
('액션·레이싱·플랫포머','입력 지연·충돌·애니메이션 이벤트·프레임률 독립·카메라·재시작','동작 정답과 조작감/멀미는 별도'),
('턴제·전략·시뮬레이션','결정성·경로탐색 최악값·많은 개체·AI 교착·장시간 누적 오차','짧은 한 판 통과로 긴 캠페인/규모를 대표할 수 없음'),
('경쟁·협동 네트워크','권한·악의적 입력·손실/재정렬/중복·재접속·동기화·매칭·부하','서버 권한으로 모든 부정행위가 해결되지 않음'),
('오픈월드·대형 3D','스트리밍·LOD·텍스처/메모리·셰이더·긴 이동 hitch·월드 저장·패치 크기','작은 씬에서의 프레임률로 전체 월드를 판정할 수 없음'),
('내러티브·어드벤처','분기 도달성·퀘스트 상태 모순·복구·현지화/더빙·서사 일관성','분기 도달만으로 서사 품질을 판정할 수 없음'),
('음악·리듬·VR','오디오/영상/입력 동기·기기 지연·트래킹·안전영역·멀미·접근성','일반 마우스 자동화나 화면 인식만으로 대체 불가'),
('HTML5 playable·광고','호스트 생명주기·용량/네트워크·오디오 정책·터치/비율·클릭 이동','브라우저 단독 실행과 실제 광고 호스트 실행은 다름')]

OBJECTIONS=[
('O1 최신 모델이면 RAG가 필요 없다','일반 기능에서는 맞을 수 있다. 이번 제한 실험도 품질 차이를 찾지 못했다.','프로젝트 고유 수정에서 동일 원문 접근을 주고 직접 검색과 RAG를 비교한다.'),
('O2 기존 코드 재사용은 안전하다','기존 계약과 새 계약이 다를 수 있다. EventBus 예외 전파가 실제 예다.','원문/버전 대조와 새 계약 회귀 검사. 원래 프로젝트의 결함으로 자동 분류하지 않는다.'),
('O3 테스트 통과면 완벽하다','판정 기준 누락·과적합·실기기/UX 문제는 남는다.','별도 최종 평가, 변이 검사, 상태/통합/기기/사람 관찰. 검사 수를 독립 업무 수로 세지 않는다.'),
('O4 두 모델이 동의하면 참이다','같은 잘못된 전제와 자료를 공유할 수 있다.','서로 답을 보지 않는 비평은 문제 발견용으로 쓰고 원문·실행·사람 판단으로 확정한다.'),
('O5 범용 아키텍처부터 만들어야 한다','사용 사례 없는 추상화 비용이 장르 차이보다 커질 수 있다.','대표 구간과 후속 변경에서 실제 중복/변경 비용을 관찰한 뒤 공통화한다.'),
('O6 자료를 모두 더 임베딩하면 좋아진다','구버전·중복·맥락 누락·갱신 비용도 늘어난다.','실패 질의와 관련 정답 근거를 먼저 라벨링하고 실패 원인별로 개선한다.'),
('O7 생성이 빨라지면 개발비도 줄어든다','리뷰·수정·통합·콘텐츠·실패 비용이 빠져 있다.','배정된 전체 업무의 완료율·결함·사람 시간·총비용을 함께 기록한다.'),
('O8 작은 실험을 모든 장르/규모에 적용할 수 있다','긴 작업과 대형 의존성은 다른 실패를 만든다.','후속 변경·다른 장르·부하를 별도 층으로 시험한다.'),
('O9 절차가 너무 무겁다','유효한 반론이다. 현재 프로세스보다 경제적이라는 증거는 없다.','같은 인수 기준을 유지한 채 짧은 계약+기존 CI+플레이테스트 방식과 추가 절차의 비용을 비교한다.'),
('O10 재미와 아트도 AI 점수로 자동 승인 가능하다','타깃 경험·디렉션·권리·시장성은 코드 정답과 다르다.','책임자 판단과 타깃 플레이어 관찰을 분리하고 기준/모집 편향을 기록한다.'),
('O11 에이전트를 늘리면 일정이 선형 단축된다','충돌·리뷰 대기·통합·서비스 자원이 병목이 될 수 있다.','의존성이 분리된 작업에서만 병렬화를 실험하고 대기·병합·재작업 시간도 측정한다.'),
('O12 출시하면 완료다','데이터/콘텐츠/서비스 업데이트가 새로운 위험을 만든다.','검증 묶음 식별, 버전 호환, 복구 리허설과 운영 회귀를 반복한다.')]

DISPOSITIONS={
'astra':[
'반영: G0~G8은 전부 제품 단위 미검증 제안으로 표시. 제품·버전별 증거 목록 추가.',
'반영: 출시 차단, N/A, 결측/timeout, 기준 변경의 기록 규칙 추가. 실제 제품 임계값은 미정.',
'부분 검증: 동일 원문 집합의 source/source_rag 비교 실행. 선정 근거 제공군은 진단군으로 수정; 미실행.',
'반영: 3개 명세·2반복과 천장 효과를 명시. 일반화/동등성 판정 안 함.',
'부분 반영: 명령/모델/사용량/시간/도구 로그 보관. Astra 서버 해석 모델 필드와 서비스 부하는 관측 불가.',
'부분 검증: 사전 고정 6파일 해시 유지, 첫 생성만 채점, 결함 3개 탐지. 사람의 독립 테스트 설계 검토는 미실시.',
'반영: snapshot/current 구분, 미수집 기획과 맥락 명시. 전체 의존성/권리 메타데이터는 후속.',
'반영: 엔진 독립 목적과 Unity 예시 분리, 장르 외 시스템 경계 위험 도출 추가.',
'반영: 코드·콘텐츠·설정·스키마·서비스 묶음, 복원 정합성 요구. 실제 복구 실험은 미실행.',
'반영: 기술/경험/사업 판정 분리, 책임자·모집·콘텐츠 종류별 측정 추가. 사람 검증은 미실시.',
'반영: 실패 포함 전체 배정 업무 완료율과 총비용 동시 보고. 유지비/사람 시간/운영 비용은 미측정.',
'반영: 관찰/출처/추론/제안 구분, 14개 1차 자료 원문 대조 범위 표시.'
],
'opus':[
'부분 검증: 일반 기능 생성에 더해 프로젝트 사실 조회 추가. 실제 프로젝트 기능 수정/통합 이득은 여전히 미검증.',
'부분 반영: 모델+CLI+도구 구성별 보고. 작은 표본과 시간 혼잡 명시, 정확한 인과 효과/유의성 주장 안 함.',
'부분 검증: 보류 파일을 도구에 노출하지 않고 원문 corpus만 제공, 호출 로그 확인. 적대적 OS 격리 보안감사 아님.',
'미실행: 완전한 검색 정답 라벨·recall@k·구버전 비율은 다음 실험에 필요. 벡터 건강 검사로 대체하지 않음.',
'검증 및 정정: 원문 EventBus 예외 후 0회/실행 중 unsubscribe 후 1회 호출 재현. 새 계약 불일치이며 원래 코드의 결함 단정은 기각.',
'반영: 단계별 제품 증거 없음, 절차 제안 상태로 명시.',
'반영: 규모별 최소 증거/역할/N/A 규칙 추가. 실제 인력·비용은 제품 미정으로 미산정.',
'미실행: 블라인드 사람 리뷰·수정 시간·투자 임계값은 다음 비교의 사전 계약 대상.',
'반영: 날짜/모델/도구 범위 한정, 모델·검색 변경 시 축소 회귀 평가 제안.',
'부분 반영: 읽기 전용/명시 프로젝트/참고자료 표시. 지시 주입 공격 실험·권리/공급자 데이터 조건 감사는 미실시.',
'확인: 현재 retrieve.py 경로는 의미 유사도·프로젝트·eligible를 사용; CLAUDE의 expert 점수를 검색 확률로 쓰지 않음.',
'반영: 코드/아트 인덱스와 기획 본문 미수집 구분. 이번 성능 평가는 코드만 사용.',
'반영: 플랫폼/지역별 인증·개인정보·텔레메트리 검토 책임 추가. 대상 미정이므로 적법성 판정하지 않음.',
'반영: 데이터 소실/진행 불가/거래 오류 등 출시 차단 분류 제안. 실제 게임 계약으로 확정 필요.',
'확인/한정: 1차 자료 원문 및 적용 범위 대조. 연구를 현재 모델 또는 게임 전체 성공으로 확대하지 않음.',
'반영: 요구/검색/구현/환경/판정/콘텐츠/통합 실패 코드와 시간 예산 사용. 임의 재시도 횟수를 보편 규칙으로 쓰지 않음.'
]}

def main():
 s=read(ROOT/'summary.json');parts=[]
 parts.append('<header><p class="eyebrow">2026-10-05 · E:\\AI · 실측 + 반대 검토</p><h1>임베딩과 Astra·Opus를 이용한<br>게임 제작 방법론 교차 검증</h1><p class="lead">다음 우선순위는 시장·타깃 가설과 기획·아트·유입 약속을 실제 플레이 구간에 연결해 검증하는 일이다. 자료실은 유지하되 전면 고도화는 업무별 추가 이득을 확인한 뒤 결정한다.</p><p><a href="market-report.html">후속 확장: 기획·아트·UA·시장 대응 교차 검증</a> — 아래 코드 실험으로 시장 성과를 입증할 수 없다.</p><p>판정: 모델 연결과 제한된 코드/조회 실험은 완료. 게임 전체 제작 절차는 제품 단위에서 아직 검증되지 않은 제안. 모든 규모·장르의 완벽한 게임을 보장할 근거는 없다.</p></header>')
 parts.append(section('무엇을 전수 확인했는가',p('이번 “전수”의 범위는 아래 9단계·9장르군·3규모·12반대론과 두 모델의 28개 지적이다. 알려지지 않은 모든 장르·실패·법규까지 망라했다는 뜻은 아니다. 특정 출시 게임·타깃 기기·예산이 정해지지 않아 제품 합격 판정을 내리지 않는다. 사용자 요청은 신규 구현 전체를 AI가 수행하는 비교로 우선 해석했고, 기존 소스 조사 해석을 보완하는 동일 원문 검색 비교도 별도로 실행했다.')+table(['영역','현재 상태','근거/한계'],[
 ('최신 임베딩','스냅샷 무결성·조회 확인','code 96,670 / art 38,901 인덱스. 과거 소스 112/114 복구, 미복구 2건은 현행 조회 제외. 기획은 Drive 본문 미수집.'),
 ('Astra/Opus 자료실 연결','실제 호출 성공','양쪽 모델이 MCP search_code/get_code_unit 실행. 원문/chunk SHA-256, 현재 파일 일치 여부 확인.'),
 ('일반 코드 생성','8회 실행·24개 구현','독립 기능 명세는 3개이며 488회 검사는 독립 업무 488개가 아니다.'),
 ('프로젝트 사실 조회','4회 실행','같은 NextPR 원문 집합에서 직접 검색 vs 직접 검색+RAG. 통합 기능 수정은 아니다.'),
 ('방법론 반대 검토','Astra 12 + Opus 16개','동일 초안을 서로의 답 없이 검토. 두 모델은 출처 원문을 직접 검증하지 않았고 작성자가 대조했다.'),
 ('게임 제작 G0~G8','전부 제품 단위 미검증 제안','Unity Player/실기기/콘텐츠 완성/플레이어/출시·운영 실행 증거 없음.')])+ '<p><a href="../asset-library-v2/data/continuation-check-20261005.json">임베딩 후속 점검</a> · <a href="../../tools/asset-library/mcp-readonly.py">읽기 전용 연결 코드</a> · <a href="mcp-validation.json">연결 경계 검사 15개</a></p>'))
 rows=[]
 for g in s['primary_groups']:
  rows.append([g['model'], '스타일+명세' if g['condition']=='baseline' else '동일 조건+자료실',str(g['compile_passed'])+'/2',str(g['passed'])+'/'+str(g['total']),f"{g['mean_seconds']:.2f}초",f"{g['mean_input_tokens_including_cache']:,.0f}",f"{g['mean_output_tokens']:,.0f}"])
 parts.append(section('실측 1 · 스타일+명세 vs 임베딩 참고 코드 생성',p('TypedEventBus·ReferencePool·RewardLedger 세 기능을 같은 요청에 제공했다. 모델별·조건별 2회, 수정 피드백 없는 첫 응답만 평가했다. RAG 조건은 자료실 조회가 필수였다. 두 조건 모두 C#9 스타일/계약은 같고, C# .NET 10 환경에서 고정된 비공개 검사 61개로 채점했다. 원문 DB 선검색 규칙의 기준선 예외는 사용자 비교 요청에 따라 명시했으며 실험 설계자는 DB를 먼저 검색했다.')+table(['구성','조건','컴파일','검사 통과','평균 CLI 시간','평균 입력 토큰¹','평균 출력'],rows)+p('관찰: 이번 검사의 정확도 차이는 0%p. 평균 시간은 Astra 약 39.7%, Opus 약 32.1% 증가했다. 두 반복과 쉬운 공통 기능에서 모두 만점이므로 일반 능력의 동등성이나 RAG 무용성을 증명하지 않는다. 시간은 생성+검색+대기+구동+형식 출력의 합이며 개발 총시간이나 게임 FPS가 아니다.')+p('¹ 캐시 포함 제공자 카운터. Astra는 여러 턴의 누적 입력, Opus는 입력+캐시 생성+캐시 읽기를 합쳤다. 서로 다른 제공자끼리 절대 수치를 직접 비교하지 않는다. Opus 평균 표시 비용은 기준선 $0.1372, RAG $0.3325이나 구독 실행의 정가 추정치이며 청구액이 아니다. Astra 금액은 미측정.')+p('시간 한계: 후보 실행은 순차였지만 첫 Opus 비교 일부와 별도 문서 검토 호출이 겹쳤다. 캐시·시간대·서비스 부하도 통제하지 못했다. 따라서 위 비율은 관찰값이지 임베딩의 확정 지연 효과가 아니다. 동일 high effort를 사용했지만 제공자별 내부 사고 예산까지 같다고 보장하지 않는다.')+ '<p><a href="task.txt">공통 명세/스타일</a> · <a href="evaluator/Program.cs">고정 검사</a> · <a href="experiment.json">설계/가정</a> · <a href="summary.json">전체 원자료 집계</a></p>'+refs('S1','S2','S7')))
 rows=[]
 for x in s['source_lookup_trials']:
  rows.append([x['model_requested'],x['condition'],str(x['grade']['passed'])+'/9',f"{x['seconds']:.2f}초",x['mcp_calls'],x['grade']['semantic_calls']])
 parts.append(section('실측 2 · 동일 원문 직접 검색 vs 직접 검색+RAG',p('두 조건 모두 같은 해시 검증 원문에서 파일 목록·문자열 검색·원문 읽기가 가능하다. RAG 조건에만 의미 검색을 추가했다. NextPR의 재화 키/기본값/보상, 영수증 처리 순서, 풀 반환/정리 순서, 이벤트 예외/해제 동작 4문항·9사실을 사전 고정했다. 각 조건 1회인 탐색 실험이다.')+table(['구성','조건','사실 정답','CLI 시간','도구 호출','의미 검색'],rows)+p('모두 9/9, 모든 인용 경로·SHA-256·행 범위가 맞았고 원문 내용을 대조했다. 클래스명으로 한정한 메서드 표기와 단순 메서드명은 같은 답으로 정규화했다. 기본 재화 1,000은 코드 기본값이며 prefab/Inspector의 실효값까지 확인한 것은 아니다. 컴포넌트 이름을 알려준 문제이므로 직접 검색이 유리할 수 있고, 숨은 여러 파일의 관계를 발견하는 업무를 대표하지 않는다.')+ '<p><a href="source-task.txt">조회 명세</a> · <a href="evaluator/source-expected.json">고정 정답</a> · <a href="source-citation-excerpts.json">원문 인용 대조</a></p>'))
 parts.append(section('교차 검증에서 찾은 실제 함정',p('Opus의 한 참고 코드 설명은 기존 EventBus에 snapshot 동작이 없다고 서술했다. 원문 코드를 별도 복사해 Unity Debug만 대체한 C# 실행에서, 실행 중 구독 해제 뒤에도 기존 호출의 다음 콜백이 1회 수행됨을 확인했다. multicast delegate의 기존 참조가 유지된다. 이 설명은 틀렸으며 생성된 새 코드가 61개 검사를 통과한 사실과 구분한다.')+p('같은 원문에서는 첫 콜백 예외 뒤 나머지 콜백이 0회 실행됐다. 새 과제는 예외를 개별 격리하도록 요구하므로 그대로 복사하면 계약 위반이다. 그러나 NextPR 계열 원문은 중단 동작을 의도된 성능 선택으로 설명하므로 원래 프로젝트의 버그라고 단정하지 않는다. 자료실은 출처를 제공할 뿐 새 계약 적합성을 인증하지 않는다.')+p('RAG 자연어 풀 검색 일부는 초기 재시도 상수·상점 보상 같은 무관 후보를 반환했다. ObjectPool 용어로 질의를 바꾸면서 관련 코드를 찾았다. 이를 전체 검색 정확도 수치로 만들지는 않았다. 질의별 정답 라벨과 recall@k는 아직 없다.')+p('검사기의 기본 탐지력을 확인하려고 성공 후보의 복사본에 예외 후 중단, 값 동등성으로 풀 소유권 판정, 영수증 기록 생략의 결함을 하나씩 넣었다. 3개 모두 컴파일됐고 고정 검사에서 적발됐다. 이것은 세 가지 표적 검사이며 포괄적 mutation score나 테스트 완전성 증명은 아니다.')+'<p><a href="reference-probe/result.json">원문 동작 재현</a> · <a href="reference-probe/Program.cs">재현 코드</a> · <a href="oracle-validation.json">결함 주입 검사</a></p>'))
 parts.append(section('제작 절차 · 단계마다 무엇을 남겨야 하는가',p('다음은 실행 가능한 절차 제안이며 아직 특정 게임에서 통과한 단계가 아니다. 장르마다 같은 아키텍처를 강제하지 않는다. 공통으로 유지하는 것은 요구사항→위험→검사→실행 결과→잔여 위험→책임자의 추적 관계다.')+table(['단계','책임 역할','실행','완료 증거/판정'],GATES)+refs('S3','S8','S9','S10','S13','S14')))
 parts.append(section('AI에게 작업을 넘기는 실제 운영 방식',p('작업 하나를 사람에게 설명 가능한 크기로 자른다. Astra 또는 Opus가 구현하고 다른 구성이 반례를 찾게 할 수 있지만, 특정 모델을 영구적으로 우월한 설계자/검토자로 지정할 근거는 이번 실험에 없다. 비평자는 처음에는 구현자의 해설을 받지 않고 계약과 diff/원문을 보고 판단한다. 실행 검사는 두 모델의 의견과 별도로 돌린다.')+p('작업 상태는 계약 확정→근거 확보→구현→검사→통합→인수로 기록한다. 각 상태에는 입력 버전, 산출물, 통과 조건, 실패 원인과 사용 시간을 둔다. 종료/재시작 때 자연어 기억에만 의존하지 않고 이 기록에서 이어간다. 배포 권한이나 실제 데이터 변경은 구현 에이전트의 코드 생성 권한과 구분한다.')+table(['작업 패키지 항목','실제 작성 예시/규칙'],[
 ('요구사항/허용 범위','“보상 거래 ID를 재수신해도 지급은 한 번”처럼 관찰 가능한 동작. 수정 가능 코드·씬·데이터를 명시.'),
 ('현재 상태/근거','커밋 또는 파일 SHA, 엔진/패키지, 현재 API와 데이터 스키마, 출처 ID/행. 기획이나 저장소의 미확인 내용은 unknown.'),
 ('실패/수명주기','취소, 장면 전환, 재접속, 중복 응답, 강제 종료, 앱 백그라운드, 초기화 순서 중 해당 항목을 지정.'),
 ('개발 검사/최종 검사','개발 피드백용과 최종 평가를 분리. 공개한 보류 사례는 이후 회귀군으로 옮기며 계속 비공개 평가라고 부르지 않음.'),
 ('반환 산출물','diff, 씬/prefab 변경, 출처와 재사용 변경점, 실행한 명령/로그, 못 돌린 검사, 잔여 위험.'),
 ('실패 분류','REQ 요구 모호 / RET 근거 검색 / CODE 구현 / ENV 환경 / ORACLE 판정 / CONTENT 콘텐츠 / INTEGRATION 연결. 같은 실패 무한 재시도 대신 분류·예산 소진 시 진단.'),
 ('판정 변경','검사가 틀렸다면 근거와 버전 변경을 남기고 모든 비교 조건을 재평가. 통과시키기 위해 해당 후보만 기준을 낮추지 않음.')])+p('의미 검색→원문 대조→현재 저장소/의존성 확인→계약에 맞게 구현→실행 검증의 순서로 사용한다. 이미 정확한 경로/심볼을 아는 작은 프로젝트는 파일/심볼 검색부터 시작해도 된다. 해시 일치는 자료가 수집 당시와 같다는 뜻이며 정확한 로직·합법적 재사용·현재 프로젝트 호환을 보장하지 않는다.')+refs('S1','S2','S3')))
 parts.append(section('장르와 시스템 경계별 검증',table(['장르군','추가 검사','반대론/한계'],GENRES)+p('복합 장르는 해당 항목의 합집합에서 시작한다. 이 목록만으로 완전하다고 판정하지 말고 실제 데이터 흐름의 경계—입력→게임 상태→저장→SDK→네트워크→외부 서비스—마다 손실·중복·지연·취소·권한·버전 충돌을 검토한다. 보안 요구는 결제/경쟁/사용자 제작 콘텐츠 등 노출에 비례해 설계한다.')+refs('S10','S11','S12')))
 parts.append(section('규모별 최소 증거와 절차 비용',table(['규모','압축 가능한 것','남겨야 할 최소 증거'],[
 ('작은 싱글 게임','역할을 한 사람이 겸하고 계약·위험·검사표를 한 파일로 합친다. 서버 없는 게임의 CCU/온콜은 N/A 가능.','제품 계약, 재현 빌드, 핵심 루프/저장·복구, 대표 기기 성능, 사람 플레이, 배포/업데이트 복구 범위.'),
 ('중형 콘텐츠 게임','형식적인 회의와 중복 문서보다 자동 콘텐츠 검사·CI를 우선한다.','위 최소 증거 + 소유권/의존성, 콘텐츠 수량·종류별 검증, 저장 마이그레이션, 지원 기기 회귀, 제작·수정 시간.'),
 ('대형 또는 라이브 게임','에이전트 수를 공정 수로 계산하지 않는다. 외부 서비스 없는 영역은 제외 근거를 기록한다.','위 증거 + 서비스/클라이언트/콘텐츠 버전 호환, 부하/장애, 복원 정합성, 운영 비용·경보 담당·복구 리허설.')])+p('N/A는 책임 역할, 사유, 재검토 조건을 남긴다. 실제 인원·예상 비용은 제품 범위가 정해진 뒤 산정한다. 초기에 측정할 것은 문서 분량이 아니라 승인 대기·리뷰·수정·CI·콘텐츠 작업 시간이다. 첫 적용에서 비용 대비 효과가 작은 절차는 합치거나 자동화하되 인수 기준은 유지한다.')))
 parts.append(section('출시 판정과 빠지기 쉬운 영역',p('제안하는 기본 판정은 PASS(필수 증거 충족), FAIL(기준 위반), UNTESTED(증거 없음), N/A(근거 있는 비해당)이다. 필수 UNTESTED가 남으면 출시 완료로 부르지 않는다. 재현 가능한 세이브 소실·핵심 진행 불가·거래 중복/소실은 기본 출시 차단 후보로 정하고 실제 영향/복구 가능성에 따라 제품 계약에서 심각도를 확정한다. 허용 가능한 사소한 결함은 책임자·영향·수정 계획을 기록한다.')+table(['영역','책임과 증거','이번 확인 상태'],[
 ('재미/시장성','제품 책임자: 모집 대상·과제·관찰 편향·반증 조건, 수요/비용 가설','미검증'),
 ('아트·애니메이션·오디오','디렉션 책임자: 스타일 일관성·가독성·수명주기·제작/수정 시간·자산 권리','아트 인덱스 존재 확인; 제작 품질 미평가'),
 ('씬·프리팹·데이터','엔진/콘텐츠 담당: GUID·참조·초기화·씬 전환·스키마·실효 Inspector 값','프로젝트 코드 사실만 조회; 런타임 연결 미검증'),
 ('성능/지원 환경','성능 담당: 대표/최저 기기·긴 플레이·p95/p99·메모리/열/로딩','미측정'),
 ('저장/거래/네트워크','기능/서비스 담당: 불변식·중복/재시도·강제종료·버전 호환·복원','합성 C# 계약 검사만 완료'),
 ('보안/자료 경계','보안/운영 담당: 권한·비밀·신뢰 경계·지시 주입·악의적 입력','읽기 전용 범위 검사만 완료; 공격 감사 미실시'),
 ('접근성/현지화','UX/접근성 담당: 입력 대안·가독성·자막/음성·언어·실제 이용자','미검증'),
 ('사용권/개인정보/SDK/지역','해당 책임자·전문 검토자: 플랫폼·지역·데이터 흐름·동의/사용권·SDK 요구','대상 미정. 법률/인증 적합성 판정 안 함'),
 ('빌드·출시·업데이트','빌드/출시 담당: 검증 묶음과 배포 묶음 해시, 스토어 항목, 마이그레이션','게임 빌드/출시 미실행'),
 ('운영·CS·텔레메트리','운영 책임자: 경보 검증·복구 시간·정합성·문의 경로·데이터 최소화','미검증')])+refs('S8','S10','S12','S14')))
 parts.append(section('반대론과 이를 판별할 방법',table(['반대 주장','인정해야 할 부분','결정할 실험/조건'],OBJECTIONS)+p('가장 강한 반론: 기존 저장소 검색+짧은 계약+기존 CI+플레이테스트만으로 비슷한 품질을 더 싸게 얻을 수 있다. 이번 결과로 이 반론을 기각할 수 없다. 따라서 전체 제작 체계의 효과와 임베딩의 추가 효과는 서로 다른 질문으로 측정한다.')+refs('S4','S5','S6')))
 parts.append(section('다음 실행 · 대표 구간과 실제 변경 비교',p('우선 작업은 자료실 전면 재구축이 아니라 실제 제품 한 개의 대표 플레이 구간이다. NextPR은 원문 조회에 사용한 프로젝트일 뿐 다음 출시 제품으로 사용자가 확정한 것은 아니다. 아래는 다음 작업 계약안이며 이번에 게임 코드를 수정하거나 배포하지 않았다.')+table(['순서','구체적 작업','완료 판정'],[
 ('1 제품/기준 고정','대표 게임·대상 기기·핵심 루프·예산을 선택하고 G0를 작성. 기존 빌드를 기준선으로 보관.','실행 가능한 인수 기준과 출시 차단 조건; 임의의 “프로덕션 수준” 점수 사용 안 함.'),
 ('2 비교 업무 사전 선정','실제 프로젝트 고유 수정, 씬/prefab 연결, 저장/데이터 변경, 일반 기능, 후속 요구 변경을 포함한 목록을 결과 전에 고정.','업무별 원문 집합/버전·정답 근거·검사·시간 예산·제외/timeout 처리 기록.'),
 ('3 공정한 비교','주 비교는 동일 원문 직접 검색 vs 동일 원문+RAG. 스타일 전용은 일반 신규 기능에 한정. 사람이 선정한 근거는 별도 진단군.','각 모델 구성별 같은 시작 상태·반복·순서 무작위 배정. 모델 간 우열보다 같은 모델 내 조건 차이 우선.'),
 ('4 실제 구현과 통합','각 조건이 고유 API/이벤트/데이터/씬에 맞춰 구현하고 Player에서 대표 구간을 실행. 공통 후속 요구 변경도 적용.','통합/회귀 통과, 출처 적합성, 구버전 복제, 리뷰 수정 시간, 콘텐츠·실기기 결과.'),
 ('5 사람/비용 측정','가능하면 조건을 가린 검토자와 타깃 플레이어를 사용. 실패·중단·대기·근거 선정·수정·CI 비용까지 기록.','전체 배정 업무의 완료율, 치명/일반 결함, 사람 시간, 경과 시간, 변동비/고정비를 함께 보고.'),
 ('6 투자 결정','품질 저하 없이 의미 있는 사람 시간/비용 감소 또는 직접 검색이 놓친 필수 근거 발견이 반복될 때 해당 층에 투자.','투자에 필요한 최소 차이와 허용 불확실성은 실행 전에 비용 구조에 맞춰 정한다. 이번 2반복으로 확정하지 않음.')])+p('예비 비교의 업무 수는 유의성을 보장하는 마법의 숫자가 없다. 업무 유형별 변동을 관찰한 뒤 실무적으로 의미 있는 차이를 검출할 수 있도록 본 평가 크기를 정한다. 표본 부족이면 “차이 미확인”으로 남긴다. 생성 완료 사례만 고르지 않고 실패를 포함한 동일 배정 집합을 비교한다.')+p('경제성은 (자료실/평가/교육 고정비 + 전체 배정 업무의 모델·검색·리뷰·수정·CI 비용)를 완료율/품질과 함께 본다. 아직 발생하지 않은 운영 장애 비용은 0으로 두지 않고 미측정으로 표기한다. 예상 재사용 횟수에 따른 손익 민감도를 계산한 뒤 확장 여부를 결정한다.')))
 parts.append(section('자료실을 개선한다면 이 순서',table(['우선순위','개선 방향','필요한 증거'],[
 ('지금 유지','원문 SHA·스냅샷/현재 구분·프로젝트 범위·읽기 전용 접근','이번 MCP 연결/경계 검증 완료. 전역 CLI 설정에는 자동 등록하지 않고 실험별 설정으로 사용.'),
 ('실패에서 시작','실제 질의·관련/금지 근거 라벨·직접 검색 기준선','현재 recall@k/구버전율 없음. 전체 벡터 수만 늘리기 전에 질의별 오류 유형 수집.'),
 ('정확한 검색과 의미 검색 결합','심볼/경로→의미 후보→원문·상위 클래스/의존성 확인','현재 무관 후보 사례 있음. 결합 검색의 추가 이득은 미검증.'),
 ('맥락/신선도','엔진/패키지·프로젝트 버전·호출 관계·prefab/GUID·실행 기록·미수집 표기','해시 무결성과 동작/호환성/사용권을 서로 다른 필드로 보존.'),
 ('효과 확인 뒤 확대','기획 본문·아트 선택·다른 프로젝트로 확장','각 영역의 실제 업무 평가를 별도로 통과. 코드 시험을 아트/기획 효용으로 간주하지 않음.')])+p('현재 CLAUDE의 expert 경험 점수는 확률로 보정된 값이 아니다. retrieve.py가 이 점수를 검색 신뢰 확률로 사용한다는 근거도 없었다. 의미 유사도·조회 우선순위·실행 검증·출시 판정은 따로 저장하고 판단한다. 모델/검색/자료 버전이 바뀌면 고정된 작은 회귀 업무부터 다시 실행한다.')))
 review_html=p('두 검토자는 같은 결과 미반영 초안을 독립적으로 읽었다. 아래는 28개 지적 전부와 처리 상태다. “문서에 반영”과 “실제로 검증”을 구분했다. 남은 제품 실험을 완료했다고 처리하지 않는다.')
 for model in ['astra','opus']:
  review=read(ROOT/f'runs/review-{model}/answer.txt')
  assert len(review['issues'])==len(DISPOSITIONS[model])
  rows=[[i['id'],i['severity'],i['claim'],d] for i,d in zip(review['issues'],DISPOSITIONS[model])]
  review_html+='<h3>'+model+'</h3>'+table(['지적','심각도','검토 대상 주장','처리/남은 증거'],rows)+f'<p><a href="runs/review-{model}/answer.txt">반대 검토 원문</a></p>'
 parts.append(section('독립 비평 28개 · 처리 내역',review_html))
 source_html=p('아래 14개 1차 자료를 읽고 관련 주장과 적용 범위를 대조했다. 원문의 직접 지침·관찰과 이 보고서의 단계 구성/투자 판단은 구분된다. 제조사 지침·다른 업무 연구의 존재가 이 스튜디오의 전체 생산성 향상을 입증하지 않는다.')
 for ident,title,url,claim in SOURCES:source_html+=f'<p id="{ident}"><strong>{ident}</strong> {esc(claim)} <a href="{url}">{esc(title)}</a></p>'
 parts.append(section('출처와 적용 범위',source_html))
 logs=[]
 for trial in s['primary_trials']:
  name=trial['name'];logs.append(f'<li>{esc(name)}: <a href="runs/{name}/command.json">명령</a> · <a href="runs/{name}/run.json">사용량/시간</a> · <a href="runs/{name}/compile-test.log">컴파일/검사 출력</a> · <a href="runs/{name}/answer.txt">응답</a></li>')
 parts.append(section('재현 명령·기록·범위',p('관측 환경: Windows 11, Python 3.13, .NET SDK 10.0.101, Codex CLI 0.160.0, Claude Code 2.1.280. Astra 명령은 gpt-6-astra를 지정했으나 서버가 해석한 모델 필드는 CLI 출력에 없었다. Opus 주 실험은 opus 별칭을 사용했고 전부 claude-opus-5-5로 보고됐다. 이후 조회는 구체 ID로 고정했다. 생성 제한은 주 실험 900초, 조회 480초; 첫 응답만 채점하고 비공개 테스트 피드백은 주지 않았다.')+'<pre>'+esc("# E:\\AI, PowerShell\n$py = 'C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe'\n& $py tools/asset-library/test-mcp-readonly.py\n# MCP contract/provenance: 15 checks PASS\n& $py tools/asset-library/eval-summarize.py\n# Frozen inputs: PASS 6; code groups 122/122 each; lookup groups 9/9 each\n& $py tools/asset-library/eval-oracle-check.py\n# Seeded defects detected: 3 / 3\n& $py tools/asset-library/eval-report.py\n# Generated report.html\n\n# Per candidate compiler check (example):\n& 'C:/Program Files/dotnet/dotnet.exe' run --project output/embedding-eval-20261005/runs/astra-baseline-1/compiled/Candidate.csproj -c Release --nologo\n# total=61, passed=61, failed=0\n\n# Full model trials: inspect eval-batch.py / eval-source-batch.py and command.json.\n# Use NEW run names on repeat; rerunning invokes provider services/subscription usage.")+'</pre><ul>'+''.join(logs)+'</ul>'+p('이번 변경은 자료실 연결/평가 도구와 별도 output 산출물이다. 실제 게임 원문, 운영 벡터/카탈로그, 전역 모델 설정을 이 실험으로 바꾸지 않았다. 실제 게임 구현·기기 테스트·사람 평가·배포는 이번 방법론 조사 범위에 포함해 실행한 것으로 주장하지 않는다. 연결용 SSH/뷰어는 로컬 후속 점검에서 구동했고 자료실은 실험 MCP 설정으로 연결했다.')+'<p><a href="../../tools/asset-library/eval-runner.py">실행기</a> · <a href="../../tools/asset-library/eval-batch.py">생성 비교</a> · <a href="../../tools/asset-library/eval-source-batch.py">원문 비교</a> · <a href="../../tools/asset-library/eval-grade.py">채점기</a> · <a href="frozen-inputs.json">사전 고정 해시</a> · <a href="source-frozen-inputs.json">조회 고정 해시</a></p>'))
 css='body{font-family:system-ui,"Malgun Gothic",sans-serif;line-height:1.75;color:#172b3a;background:#f5f7fa;margin:0}main{max-width:1160px;margin:auto;padding:36px 28px}header,section{background:white;border:1px solid #dde4eb;border-radius:12px;padding:26px 30px;margin:0 0 22px}h1{font-size:32px;line-height:1.4}h2{font-size:23px;color:#124767}h3{font-size:18px}.lead{font-size:20px;font-weight:600}.eyebrow,.refs{color:#52677a;font-size:14px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #d9e2eb;padding:12px}th{background:#edf3f8}.scroll{overflow-x:auto}a{color:#126393}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf3f8;padding:18px;font-size:13px}p{overflow-wrap:anywhere}@media print{body{background:white}main{padding:0}section,header{border:0;padding:12px 0}tr{break-inside:avoid}a{color:inherit}}'
 doc='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>게임 제작 방법론 교차 검증 · 2026-10-05</title><style>'+css+'</style></head><body><main>'+''.join(parts)+'</main></body></html>'
 (ROOT/'report.html').write_text(doc,encoding='utf8')
 (ROOT/'source-citation-review.json').write_text(json.dumps({'reviewed':True,'method':'Inspected all unique cited source ranges and matched each answer to implementation; hash/range checks stored separately.','caveats':['Currency initial value is code default; serialized scene/prefab override not checked.','PlayerPrefs receipt-before-add statement is source order, not crash atomicity.','EventBus delegate behavior separately executed with Debug stub, not Unity runtime.']},indent=2),encoding='utf8')
 print('Generated report.html')

if __name__=='__main__':main()
