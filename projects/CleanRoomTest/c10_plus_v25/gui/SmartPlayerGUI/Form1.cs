namespace SmartPlayerGUI;

public partial class Form1 : Form
{
    private readonly PythonBridge _bridge = new();
    private PatternDatabase _db = null!;
    private GameRegistry _registry = null!;

    public Form1()
    {
        InitializeComponent();
        InitBridge();
        InitDatabase();
        InitGameDropdown();
        InitTagDropdown();
        SetupEvents();
        RefreshRecordingInfo();
        LoadGuideText();
    }

    // ================================================================
    // Init
    // ================================================================

    private void SetupEvents()
    {
        btnRecord.Click += BtnRecord_Click;
        btnMimic.Click += BtnMimic_Click;
        btnSaveData.Click += BtnSaveData_Click;
        btnStop.Click += BtnStop_Click;
        btnSend.Click += BtnSend_Click;
        btnAddGame.Click += BtnAddGame_Click;
        btnDeletePattern.Click += BtnDeletePattern_Click;
        txtCommand.KeyDown += (s, e) => { if (e.KeyCode == Keys.Enter) BtnSend_Click(s, e); };
        cboGame.SelectedIndexChanged += (_, _) =>
        {
            if (cboGame.SelectedItem is GameEntry g)
            {
                _bridge.GameKey = g.Key;
                RefreshRecordingInfo();
                RefreshPatternList();
            }
        };

        _bridge.OnOutput += line => SafeInvoke(() => AppendLog(line, Color.FromArgb(200, 200, 200)));
        _bridge.OnError += line => SafeInvoke(() => AppendLog(line, Color.FromArgb(255, 150, 150)));
        _bridge.OnExited += code => SafeInvoke(() =>
        {
            AppendLog($"--- Process exited (code={code}) ---",
                code == 0 ? Color.FromArgb(100, 255, 100) : Color.Orange);
            SetRunningState(false);
            RefreshRecordingInfo();
        });
    }

    private void SafeInvoke(Action action)
    {
        if (IsDisposed) return;
        try { Invoke(action); } catch (ObjectDisposedException) { }
    }

    private void InitBridge()
    {
        var candidates = new[]
        {
            @"C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe",
            @"C:\Users\user\AppData\Local\Programs\Python\Python310\python.exe",
        };
        foreach (var p in candidates)
            if (File.Exists(p)) { _bridge.PythonExe = p; break; }

        _bridge.ScriptDir = @"E:\AI\projects\CleanRoomTest\c10_plus_v25";
    }

    private void InitDatabase()
    {
        _db = new PatternDatabase(_bridge.ScriptDir);
        _registry = new GameRegistry(_bridge.ScriptDir);
    }

    private void InitGameDropdown()
    {
        cboGame.Items.Clear();
        foreach (var g in _registry.Games)
            cboGame.Items.Add(g);

        cboGame.DisplayMember = "Key";
        if (cboGame.Items.Count > 0)
        {
            cboGame.SelectedIndex = 0;
            _bridge.GameKey = _registry.Games[0].Key;
        }
    }

    private void InitTagDropdown()
    {
        cboTag.Items.Clear();
        foreach (var tag in Enum.GetValues<SystemTag>())
            cboTag.Items.Add(tag);
        // Default to Full_Playthrough
        cboTag.SelectedItem = SystemTag.Full_Playthrough;
    }

    // ================================================================
    // Button Handlers
    // ================================================================

    private void BtnRecord_Click(object? sender, EventArgs e)
    {
        try
        {
            var game = cboGame.SelectedItem as GameEntry;
            AppendLog($"[Record] {game?.Name ?? _bridge.GameKey} 녹화 시작", Color.FromArgb(255, 100, 100));
            AppendLog("[Record] BlueStacks에서 게임을 플레이하세요. Stop으로 중지.", Color.Yellow);
            _bridge.StartRecording();
            SetRunningState(true);
        }
        catch (Exception ex) { AppendLog($"ERROR: {ex.Message}", Color.Red); }
    }

    private void BtnMimic_Click(object? sender, EventArgs e)
    {
        var info = _bridge.GetRecordingInfo();
        if (info == null)
        {
            AppendLog("[AI Mimic] 녹화 데이터가 없습니다! 먼저 녹화하세요.", Color.Orange);
            return;
        }

        try
        {
            AppendLog($"[AI Mimic] 스마트 캡처 시작 (그래프: {info.GraphNodeCount}N/{info.GraphEdgeCount}E)",
                Color.FromArgb(100, 180, 255));
            _bridge.StartSmartCapture();
            SetRunningState(true);
        }
        catch (Exception ex) { AppendLog($"ERROR: {ex.Message}", Color.Red); }
    }

    private void BtnSaveData_Click(object? sender, EventArgs e)
    {
        var info = _bridge.GetRecordingInfo();
        if (info == null)
        {
            AppendLog("[Save] 저장할 녹화 데이터가 없습니다!", Color.Orange);
            return;
        }

        var tag = (SystemTag)(cboTag.SelectedItem ?? SystemTag.General);
        var pattern = new BehaviorPattern
        {
            GameKey = _bridge.GameKey,
            Tag = tag,
            RecordingPath = info.RecordingPath,
            ClassificationsPath = info.ClassificationsPath,
            NavGraphPath = info.NavGraphPath,
            EventCount = info.EventCount,
            FrameCount = info.FrameCount,
            GraphNodeCount = info.GraphNodeCount,
            GraphEdgeCount = info.GraphEdgeCount,
            Description = $"{tag} pattern — {info.EventCount}evt, {info.FrameCount}frm",
        };

        _db.Add(pattern);
        RefreshPatternList();

        AppendLog($"[Save] 패턴 저장 완료: [{tag}] {info.EventCount}evt {info.FrameCount}frm "
                + $"graph={info.GraphNodeCount}N/{info.GraphEdgeCount}E",
            Color.FromArgb(100, 255, 100));
    }

    private void BtnStop_Click(object? sender, EventArgs e)
    {
        _bridge.Stop();
        AppendLog("[Stop] 프로세스 중지 중...", Color.Yellow);
    }

    private void BtnSend_Click(object? sender, EventArgs e)
    {
        var cmd = txtCommand.Text.Trim();
        if (string.IsNullOrEmpty(cmd)) return;

        try
        {
            AppendLog($"[CMD] {cmd}", Color.FromArgb(180, 180, 255));
            _bridge.RunCustomCommand(cmd);
            SetRunningState(true);
            txtCommand.Clear();
        }
        catch (Exception ex) { AppendLog($"ERROR: {ex.Message}", Color.Red); }
    }

    private void BtnAddGame_Click(object? sender, EventArgs e)
    {
        using var dlg = new AddGameDialog();
        if (dlg.ShowDialog(this) == DialogResult.OK && dlg.Result != null)
        {
            _registry.Add(dlg.Result);
            InitGameDropdown();
            // Select the newly added game
            for (int i = 0; i < cboGame.Items.Count; i++)
            {
                if (cboGame.Items[i] is GameEntry g && g.Key == dlg.Result.Key)
                {
                    cboGame.SelectedIndex = i;
                    break;
                }
            }
            AppendLog($"[Game] 추가: {dlg.Result.Key} ({dlg.Result.Package})", Color.Cyan);
        }
    }

    private void BtnDeletePattern_Click(object? sender, EventArgs e)
    {
        if (lstPatterns.SelectedIndex < 0) return;

        var gamePatterns = _db.FindByGame(_bridge.GameKey);
        if (lstPatterns.SelectedIndex >= gamePatterns.Count) return;

        var pattern = gamePatterns[lstPatterns.SelectedIndex];
        _db.Remove(pattern.Id);
        RefreshPatternList();
        AppendLog($"[DB] 패턴 삭제: {pattern}", Color.Gray);
    }

    // ================================================================
    // UI Helpers
    // ================================================================

    private void SetRunningState(bool running)
    {
        btnRecord.Enabled = !running;
        btnMimic.Enabled = !running;
        btnSaveData.Enabled = !running;
        btnSend.Enabled = !running;
        btnStop.Enabled = running;
    }

    private void AppendLog(string text, Color color)
    {
        var time = DateTime.Now.ToString("HH:mm:ss");
        txtLog.SelectionStart = txtLog.TextLength;
        txtLog.SelectionColor = Color.DimGray;
        txtLog.AppendText($"[{time}] ");
        txtLog.SelectionStart = txtLog.TextLength;
        txtLog.SelectionColor = color;
        txtLog.AppendText(text + "\n");
        txtLog.ScrollToCaret();
    }

    private void RefreshRecordingInfo()
    {
        var info = _bridge.GetRecordingInfo();
        if (info == null)
        {
            lblRecInfo.Text = "녹화 없음 — [녹화] 버튼으로 시작";
            lblRecInfo.ForeColor = Color.Gray;
            return;
        }

        lblRecInfo.Text = $"Evt:{info.EventCount}  Frm:{info.FrameCount}  "
                        + $"Cls:{info.ClassifiedCount}  "
                        + $"Graph:{info.GraphNodeCount}N/{info.GraphEdgeCount}E  "
                        + $"({info.RecordedAt})";
        lblRecInfo.ForeColor = info.GraphNodeCount > 0 ? Color.DarkGreen : Color.DarkOrange;
    }

    private void RefreshPatternList()
    {
        lstPatterns.Items.Clear();
        var patterns = _db.FindByGame(_bridge.GameKey);
        foreach (var p in patterns)
            lstPatterns.Items.Add(p.ToString());

        var stats = _db.GetTagStats();
        var parts = stats.Select(kv => $"{kv.Key}:{kv.Value}");
        lblPatternStats.Text = $"Total: {_db.Patterns.Count}"
                             + (stats.Count > 0 ? $"  ({string.Join(", ", parts)})" : "");
    }

    private void LoadGuideText()
    {
        txtGuide.Text = @"=== Smart Player 사용법 ===

[ 기본 워크플로우 ]

  Step 1. 게임 선택
    - Game 드롭다운에서 게임 선택
    - 새 게임은 [+] 버튼으로 추가

  Step 2. 녹화 (Record)
    - Tag를 선택 (어떤 행동을 녹화할 건지)
    - [녹화] 클릭 → BlueStacks에서 플레이
    - 원하는 만큼 플레이 후 [Stop]
    - 터치 이벤트 + 스크린샷이 자동 저장됨

  Step 3. 패턴 저장 (Save)
    - 적절한 Tag 선택 후 [패턴 저장] 클릭
    - 녹화 데이터가 행동 패턴 DB에 저장됨
    - 같은 게임에 여러 Tag로 반복 가능

  Step 4. AI 모방 (Mimic)
    - [AI 모방] 클릭
    - AI가 녹화 데이터를 분석하여:
      1) 화면 타입 분류 (Claude Vision)
      2) 네비게이션 그래프 구축
      3) 10개 미션 자동 수행
    - 결과 스크린샷이 output/ 에 저장

[ Tag 활용 전략 ]

  한 게임에 여러 Tag로 녹화하면 AI가 더 풍부한
  행동 패턴을 학습합니다:

  예시 (Idle RPG):
    1회차: Full_Playthrough — 처음부터 자유 플레이
    2회차: Battle_Normal — 전투만 집중
    3회차: Gacha_Summon — 소환 화면 집중 탐색
    4회차: Equipment_Enhance — 장비 강화 과정
    5회차: Daily_Routine — 일상 루틴 순서대로

  → 이 패턴들이 합쳐져서 AI가 모든 화면을
    자율적으로 탐색할 수 있게 됩니다.

[ Command 입력 예시 ]

  run.py ash_n_veil --skip-capture
  run.py ash_n_veil --replay --replay-speed 2.0
  run.py --list";

        txtTagGuide.Text = @"=== System Tag 설명 ===

── 전투 ──
  Battle_Normal     일반 전투 (자동/수동)
  Battle_Boss       보스전 (특수 패턴)
  Battle_PvP        PvP/아레나

── 성장 ──
  Character_LevelUp 캐릭터 레벨업/스탯 확인
  Skill_Upgrade     스킬 레벨업/장착
  Equipment_Enhance 장비 강화/교체
  Pet_Companion     펫/동료 관리

── 재화 ──
  Gacha_Summon      가챠/소환
  Shop_Purchase     상점 구매
  Economy_Collect   재화 수집 (방치보상/우편함)
  Ad_Watch          보상형 광고 시청

── 콘텐츠 ──
  Stage_Select      스테이지/챕터 선택
  Quest_Mission     퀘스트/일일미션
  Dungeon_Raid      던전/레이드 입장
  Event_Limited     한정 이벤트 참여

── UI/시스템 ──
  Menu_Navigate     메뉴 탐색 (탭 이동)
  Tutorial_Follow   튜토리얼 따라가기
  Popup_Dismiss     팝업/공지 닫기
  Settings_Change   설정 변경

── 메타 (복합 행동) ──
  Full_Playthrough  처음~끝 전체 플레이
  Daily_Routine     일일 루틴 순서대로
  Exploration       자유 탐색 (새 화면 발견)
  General           기타

=== AI가 패턴을 사용하는 방식 ===

  1. 녹화된 터치 이벤트 → 화면별 분류
  2. 화면 전환 그래프 (NavGraph) 구축
  3. Tag별로 그래프 병합
     → ""이 화면에서 저 화면으로 가려면
        어디를 탭해야 하는지"" 학습
  4. AI 자율 플레이 시:
     - 현재 화면 인식 (스크린샷 분류)
     - 목표 화면까지 경로 탐색 (BFS)
     - 경로대로 탭/스와이프 실행
     - 팝업 감지 시 자동 닫기

  패턴이 많을수록 그래프가 풍부해지고
  AI의 탐색 범위가 넓어집니다.";
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _bridge.Stop();
        base.OnFormClosing(e);
    }
}
