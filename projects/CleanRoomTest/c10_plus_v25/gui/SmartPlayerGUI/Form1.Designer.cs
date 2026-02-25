namespace SmartPlayerGUI;

partial class Form1
{
    private System.ComponentModel.IContainer components = null;

    protected override void Dispose(bool disposing)
    {
        if (disposing && (components != null))
            components.Dispose();
        base.Dispose(disposing);
    }

    #region Windows Form Designer generated code

    private void InitializeComponent()
    {
        // ===== Controls =====
        lblGame = new Label();
        cboGame = new ComboBox();
        btnAddGame = new Button();
        lblTag = new Label();
        cboTag = new ComboBox();

        btnRecord = new Button();
        btnMimic = new Button();
        btnSaveData = new Button();
        btnStop = new Button();

        lblCommand = new Label();
        txtCommand = new TextBox();
        btnSend = new Button();

        grpRecording = new GroupBox();
        lblRecInfo = new Label();

        grpStatus = new GroupBox();
        txtLog = new RichTextBox();

        grpPatternDB = new GroupBox();
        lblPatternStats = new Label();
        lstPatterns = new ListBox();
        btnDeletePattern = new Button();

        tabGuide = new TabControl();
        tabUsage = new TabPage();
        txtGuide = new RichTextBox();
        tabTags = new TabPage();
        txtTagGuide = new RichTextBox();

        // ===== Layout =====
        SuspendLayout();

        // --- Row 1: Game + Tag ---
        lblGame.Text = "Game:";
        lblGame.Location = new Point(16, 18);
        lblGame.AutoSize = true;

        cboGame.Location = new Point(60, 14);
        cboGame.Size = new Size(180, 25);
        cboGame.DropDownStyle = ComboBoxStyle.DropDownList;

        btnAddGame.Text = "+";
        btnAddGame.Location = new Point(245, 13);
        btnAddGame.Size = new Size(30, 26);
        btnAddGame.Font = new Font("Segoe UI", 10F, FontStyle.Bold);

        lblTag.Text = "Tag:";
        lblTag.Location = new Point(290, 18);
        lblTag.AutoSize = true;

        cboTag.Location = new Point(325, 14);
        cboTag.Size = new Size(200, 25);
        cboTag.DropDownStyle = ComboBoxStyle.DropDownList;

        // --- Row 2: Action buttons ---
        btnRecord.Text = "녹화 Record";
        btnRecord.Location = new Point(16, 48);
        btnRecord.Size = new Size(120, 40);
        btnRecord.BackColor = Color.FromArgb(220, 53, 69);
        btnRecord.ForeColor = Color.White;
        btnRecord.FlatStyle = FlatStyle.Flat;
        btnRecord.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold);

        btnMimic.Text = "AI 모방 Mimic";
        btnMimic.Location = new Point(145, 48);
        btnMimic.Size = new Size(130, 40);
        btnMimic.BackColor = Color.FromArgb(0, 123, 255);
        btnMimic.ForeColor = Color.White;
        btnMimic.FlatStyle = FlatStyle.Flat;
        btnMimic.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold);

        btnSaveData.Text = "패턴 저장 Save";
        btnSaveData.Location = new Point(284, 48);
        btnSaveData.Size = new Size(140, 40);
        btnSaveData.BackColor = Color.FromArgb(40, 167, 69);
        btnSaveData.ForeColor = Color.White;
        btnSaveData.FlatStyle = FlatStyle.Flat;
        btnSaveData.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold);

        btnStop.Text = "Stop";
        btnStop.Location = new Point(433, 48);
        btnStop.Size = new Size(60, 40);
        btnStop.BackColor = Color.FromArgb(108, 117, 125);
        btnStop.ForeColor = Color.White;
        btnStop.FlatStyle = FlatStyle.Flat;
        btnStop.Enabled = false;

        // --- Row 3: Command ---
        lblCommand.Text = "Cmd:";
        lblCommand.Location = new Point(16, 100);
        lblCommand.AutoSize = true;

        txtCommand.Location = new Point(52, 97);
        txtCommand.Size = new Size(370, 25);
        txtCommand.PlaceholderText = "run.py ash_n_veil --skip-capture  (or any python command)";

        btnSend.Text = "Run";
        btnSend.Location = new Point(430, 95);
        btnSend.Size = new Size(60, 28);

        // --- Recording info ---
        grpRecording.Text = "Recording";
        grpRecording.Location = new Point(16, 126);
        grpRecording.Size = new Size(510, 48);

        lblRecInfo.Text = "No recording";
        lblRecInfo.Location = new Point(10, 20);
        lblRecInfo.AutoSize = true;
        lblRecInfo.Font = new Font("Consolas", 8.5F);
        grpRecording.Controls.Add(lblRecInfo);

        // --- Status log ---
        grpStatus.Text = "Log";
        grpStatus.Location = new Point(16, 178);
        grpStatus.Size = new Size(510, 200);

        txtLog.Location = new Point(6, 18);
        txtLog.Size = new Size(498, 175);
        txtLog.ReadOnly = true;
        txtLog.BackColor = Color.FromArgb(25, 25, 30);
        txtLog.ForeColor = Color.FromArgb(200, 200, 200);
        txtLog.Font = new Font("Consolas", 8.5F);
        txtLog.BorderStyle = BorderStyle.None;
        txtLog.WordWrap = false;
        grpStatus.Controls.Add(txtLog);

        // --- Pattern DB ---
        grpPatternDB.Text = "Behavior Pattern DB";
        grpPatternDB.Location = new Point(16, 382);
        grpPatternDB.Size = new Size(510, 160);

        lblPatternStats.Text = "Total: 0";
        lblPatternStats.Location = new Point(10, 20);
        lblPatternStats.AutoSize = true;
        lblPatternStats.Font = new Font("Segoe UI", 8.5F, FontStyle.Bold);

        lstPatterns.Location = new Point(10, 40);
        lstPatterns.Size = new Size(410, 110);
        lstPatterns.Font = new Font("Consolas", 8.5F);

        btnDeletePattern.Text = "Del";
        btnDeletePattern.Location = new Point(428, 40);
        btnDeletePattern.Size = new Size(72, 26);

        grpPatternDB.Controls.Add(lblPatternStats);
        grpPatternDB.Controls.Add(lstPatterns);
        grpPatternDB.Controls.Add(btnDeletePattern);

        // --- Guide tabs (right side) ---
        tabGuide.Location = new Point(540, 14);
        tabGuide.Size = new Size(330, 528);

        tabUsage.Text = "사용법";
        txtGuide.Dock = DockStyle.Fill;
        txtGuide.ReadOnly = true;
        txtGuide.BackColor = Color.FromArgb(250, 250, 245);
        txtGuide.Font = new Font("Segoe UI", 9F);
        txtGuide.BorderStyle = BorderStyle.None;
        tabUsage.Controls.Add(txtGuide);

        tabTags.Text = "Tag 설명";
        txtTagGuide.Dock = DockStyle.Fill;
        txtTagGuide.ReadOnly = true;
        txtTagGuide.BackColor = Color.FromArgb(250, 250, 245);
        txtTagGuide.Font = new Font("Segoe UI", 9F);
        txtTagGuide.BorderStyle = BorderStyle.None;
        tabTags.Controls.Add(txtTagGuide);

        tabGuide.TabPages.Add(tabUsage);
        tabGuide.TabPages.Add(tabTags);

        // ===== Form =====
        AutoScaleDimensions = new SizeF(7F, 15F);
        AutoScaleMode = AutoScaleMode.Font;
        ClientSize = new Size(882, 556);
        Text = "Smart Player — AI Behavior Pattern Builder";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;

        Controls.Add(lblGame);
        Controls.Add(cboGame);
        Controls.Add(btnAddGame);
        Controls.Add(lblTag);
        Controls.Add(cboTag);
        Controls.Add(btnRecord);
        Controls.Add(btnMimic);
        Controls.Add(btnSaveData);
        Controls.Add(btnStop);
        Controls.Add(lblCommand);
        Controls.Add(txtCommand);
        Controls.Add(btnSend);
        Controls.Add(grpRecording);
        Controls.Add(grpStatus);
        Controls.Add(grpPatternDB);
        Controls.Add(tabGuide);

        ResumeLayout(false);
        PerformLayout();
    }

    #endregion

    private Label lblGame;
    private ComboBox cboGame;
    private Button btnAddGame;
    private Label lblTag;
    private ComboBox cboTag;
    private Button btnRecord;
    private Button btnMimic;
    private Button btnSaveData;
    private Button btnStop;
    private Label lblCommand;
    private TextBox txtCommand;
    private Button btnSend;
    private GroupBox grpRecording;
    private Label lblRecInfo;
    private GroupBox grpStatus;
    private RichTextBox txtLog;
    private GroupBox grpPatternDB;
    private Label lblPatternStats;
    private ListBox lstPatterns;
    private Button btnDeletePattern;
    private TabControl tabGuide;
    private TabPage tabUsage;
    private RichTextBox txtGuide;
    private TabPage tabTags;
    private RichTextBox txtTagGuide;
}
