using System.Text.Json;

namespace SmartPlayerGUI;

/// <summary>
/// 게임 목록 관리 — games.json에서 로드/저장.
/// 새 게임은 GUI에서 추가하거나 ADB에서 자동 탐지.
/// </summary>
public class GameRegistry
{
    private readonly string _path;
    private List<GameEntry> _games = new();

    private static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

    public IReadOnlyList<GameEntry> Games => _games.AsReadOnly();

    public GameRegistry(string baseDir)
    {
        _path = Path.Combine(baseDir, "games.json");
        Load();
        EnsureDefaults();
    }

    public void Add(GameEntry game)
    {
        if (_games.Any(g => g.Key == game.Key)) return;
        _games.Add(game);
        Save();
    }

    public void Remove(string key)
    {
        _games.RemoveAll(g => g.Key == key);
        Save();
    }

    public GameEntry? Find(string key) => _games.FirstOrDefault(g => g.Key == key);

    public void Save()
    {
        try
        {
            File.WriteAllText(_path, JsonSerializer.Serialize(_games, JsonOpts));
        }
        catch { }
    }

    private void Load()
    {
        if (!File.Exists(_path)) return;
        try
        {
            _games = JsonSerializer.Deserialize<List<GameEntry>>(File.ReadAllText(_path), JsonOpts) ?? new();
        }
        catch { _games = new(); }
    }

    private void EnsureDefaults()
    {
        // 기존 genres/ 모듈에 등록된 게임들
        var defaults = new GameEntry[]
        {
            new() { Key = "ash_n_veil", Name = "Ash N Veil", Package = "studio.gameberry.anv", Genre = "idle_rpg" },
            new() { Key = "carmatch", Name = "Car Match", Package = "com.grandgames.carmatch", Genre = "puzzle" },
            new() { Key = "magicsort", Name = "Magic Sort", Package = "com.grandgames.magicsort", Genre = "puzzle" },
            new() { Key = "tapshift", Name = "Tap Shift", Package = "com.paxiegames.tapshift", Genre = "puzzle" },
        };

        bool changed = false;
        foreach (var d in defaults)
        {
            if (!_games.Any(g => g.Key == d.Key))
            {
                _games.Add(d);
                changed = true;
            }
        }
        if (changed) Save();
    }
}
