namespace SmartPlayerGUI;

/// <summary>
/// 새 게임 추가 다이얼로그.
/// ADB 패키지 목록에서 선택하거나 수동 입력.
/// </summary>
public class AddGameDialog : Form
{
    private TextBox txtKey = new();
    private TextBox txtName = new();
    private TextBox txtPackage = new();
    private ComboBox cboGenre = new();
    private Button btnOK = new();
    private Button btnCancel = new();

    public GameEntry? Result { get; private set; }

    public AddGameDialog(List<string>? adbPackages = null)
    {
        Text = "Add Game";
        Size = new Size(400, 260);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterParent;
        MaximizeBox = false;
        MinimizeBox = false;

        int y = 16;
        AddRow("Game Key:", txtKey, ref y, "my_game");
        AddRow("Display Name:", txtName, ref y, "My Game");

        // Package — editable combo if ADB packages available
        var lblPkg = new Label { Text = "Package:", Location = new Point(16, y + 3), AutoSize = true };
        if (adbPackages is { Count: > 0 })
        {
            var cboPkg = new ComboBox
            {
                Location = new Point(120, y), Size = new Size(240, 25),
                DropDownStyle = ComboBoxStyle.DropDown,
            };
            foreach (var p in adbPackages) cboPkg.Items.Add(p);
            cboPkg.TextChanged += (_, _) => txtPackage.Text = cboPkg.Text;
            Controls.Add(lblPkg);
            Controls.Add(cboPkg);
            txtPackage.Visible = false;
        }
        else
        {
            AddRow("Package:", txtPackage, ref y, "com.example.game");
            y -= 32; // undo since AddRow already incremented
        }
        y += 32;

        // Genre
        var lblGenre = new Label { Text = "Genre:", Location = new Point(16, y + 3), AutoSize = true };
        cboGenre.Location = new Point(120, y);
        cboGenre.Size = new Size(240, 25);
        cboGenre.DropDownStyle = ComboBoxStyle.DropDownList;
        cboGenre.Items.AddRange(new object[] { "idle_rpg", "puzzle", "merge", "slg", "tycoon", "simulation", "other" });
        cboGenre.SelectedIndex = 0;
        Controls.Add(lblGenre);
        Controls.Add(cboGenre);
        y += 40;

        // Buttons
        btnOK.Text = "Add";
        btnOK.Location = new Point(180, y);
        btnOK.Size = new Size(80, 30);
        btnOK.DialogResult = DialogResult.OK;
        btnOK.Click += (_, _) =>
        {
            if (string.IsNullOrWhiteSpace(txtKey.Text) || string.IsNullOrWhiteSpace(txtPackage.Text))
            {
                MessageBox.Show("Key and Package are required.", "Error");
                DialogResult = DialogResult.None;
                return;
            }
            Result = new GameEntry
            {
                Key = txtKey.Text.Trim().Replace(" ", "_").ToLower(),
                Name = string.IsNullOrWhiteSpace(txtName.Text) ? txtKey.Text : txtName.Text.Trim(),
                Package = txtPackage.Text.Trim(),
                Genre = cboGenre.Text,
            };
        };

        btnCancel.Text = "Cancel";
        btnCancel.Location = new Point(270, y);
        btnCancel.Size = new Size(80, 30);
        btnCancel.DialogResult = DialogResult.Cancel;

        Controls.Add(btnOK);
        Controls.Add(btnCancel);
        AcceptButton = btnOK;
        CancelButton = btnCancel;
    }

    private void AddRow(string label, TextBox tb, ref int y, string placeholder)
    {
        var lbl = new Label { Text = label, Location = new Point(16, y + 3), AutoSize = true };
        tb.Location = new Point(120, y);
        tb.Size = new Size(240, 25);
        tb.PlaceholderText = placeholder;
        Controls.Add(lbl);
        Controls.Add(tb);
        y += 32;
    }
}
