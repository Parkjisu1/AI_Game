namespace SmartPlayerGUI;

/// <summary>
/// 게임 시스템 태그 — 행동 패턴의 의도/맥락 분류.
/// AI가 자율 플레이 시 "지금 뭘 하는 중인지"를 판단하는 핵심 축.
/// </summary>
public enum SystemTag
{
    // ── 전투 ──
    Battle_Normal,          // 일반 전투 (자동/수동)
    Battle_Boss,            // 보스전 (특수 패턴)
    Battle_PvP,             // PvP/아레나

    // ── 성장 ──
    Character_LevelUp,      // 캐릭터 레벨업/스탯 확인
    Skill_Upgrade,          // 스킬 레벨업/장착
    Equipment_Enhance,      // 장비 강화/교체
    Pet_Companion,          // 펫/동료 관리

    // ── 재화 ──
    Gacha_Summon,           // 가챠/소환
    Shop_Purchase,          // 상점 구매
    Economy_Collect,        // 재화 수집 (방치보상/우편함)
    Ad_Watch,               // 보상형 광고 시청

    // ── 콘텐츠 ──
    Stage_Select,           // 스테이지/챕터 선택
    Quest_Mission,          // 퀘스트/일일미션
    Dungeon_Raid,           // 던전/레이드 입장
    Event_Limited,          // 한정 이벤트 참여

    // ── UI/시스템 ──
    Menu_Navigate,          // 메뉴 탐색 (탭 이동)
    Tutorial_Follow,        // 튜토리얼 따라가기
    Popup_Dismiss,          // 팝업/공지 닫기
    Settings_Change,        // 설정 변경

    // ── 메타 ──
    Full_Playthrough,       // 처음~끝 전체 플레이
    Daily_Routine,          // 일일 루틴 (접속→보상→퀘→가챠→전투)
    Exploration,            // 자유 탐색 (새로운 화면 발견)
    General                 // 기타
}

/// <summary>
/// 게임 등록 정보 — GUI에서 동적으로 추가 가능
/// </summary>
public class GameEntry
{
    public string Key { get; set; } = "";       // e.g. "ash_n_veil"
    public string Name { get; set; } = "";      // e.g. "Ash N Veil"
    public string Package { get; set; } = "";   // e.g. "studio.gameberry.anv"
    public string Genre { get; set; } = "";     // e.g. "idle_rpg"

    public override string ToString() => $"{Key} ({Name})";
}

/// <summary>
/// 하나의 행동 패턴 (녹화 세션 + 분류 + 태그)
/// </summary>
public class BehaviorPattern
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N")[..8];
    public string GameKey { get; set; } = "";
    public SystemTag Tag { get; set; } = SystemTag.General;
    public string Description { get; set; } = "";
    public DateTime RecordedAt { get; set; } = DateTime.Now;

    /// <summary>recording.json 파일 경로</summary>
    public string RecordingPath { get; set; } = "";

    /// <summary>classifications.json 파일 경로</summary>
    public string ClassificationsPath { get; set; } = "";

    /// <summary>nav_graph.json 파일 경로</summary>
    public string NavGraphPath { get; set; } = "";

    /// <summary>녹화된 이벤트 수</summary>
    public int EventCount { get; set; }

    /// <summary>분류된 프레임 수</summary>
    public int FrameCount { get; set; }

    /// <summary>그래프 노드 수</summary>
    public int GraphNodeCount { get; set; }

    /// <summary>그래프 엣지 수</summary>
    public int GraphEdgeCount { get; set; }

    /// <summary>패턴 신뢰도 (0.0~1.0, 사용 성공률 기반)</summary>
    public double Confidence { get; set; } = 0.5;

    /// <summary>AI 모방 시 사용 횟수</summary>
    public int UseCount { get; set; }

    /// <summary>AI 모방 성공 횟수</summary>
    public int SuccessCount { get; set; }

    /// <summary>사용자 메모</summary>
    public string Notes { get; set; } = "";

    public override string ToString()
        => $"[{Tag}] {GameKey} — {EventCount}evt {FrameCount}frm ({Confidence:P0})";
}
