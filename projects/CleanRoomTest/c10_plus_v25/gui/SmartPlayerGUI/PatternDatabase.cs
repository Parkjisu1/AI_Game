using System.Text.Json;
using System.Text.Json.Serialization;

namespace SmartPlayerGUI;

/// <summary>
/// JSON 기반 행동 패턴 DB.
/// 저장 위치: {BaseDir}/patterns/pattern_db.json
/// </summary>
public class PatternDatabase
{
    private readonly string _dbPath;
    private List<BehaviorPattern> _patterns = new();

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() }
    };

    public IReadOnlyList<BehaviorPattern> Patterns => _patterns.AsReadOnly();

    public PatternDatabase(string baseDir)
    {
        var dir = Path.Combine(baseDir, "patterns");
        Directory.CreateDirectory(dir);
        _dbPath = Path.Combine(dir, "pattern_db.json");
        Load();
    }

    public void Add(BehaviorPattern pattern)
    {
        _patterns.Add(pattern);
        Save();
    }

    public void Update(BehaviorPattern pattern)
    {
        var idx = _patterns.FindIndex(p => p.Id == pattern.Id);
        if (idx >= 0)
            _patterns[idx] = pattern;
        Save();
    }

    public void Remove(string patternId)
    {
        _patterns.RemoveAll(p => p.Id == patternId);
        Save();
    }

    public List<BehaviorPattern> FindByTag(SystemTag tag)
        => _patterns.Where(p => p.Tag == tag).ToList();

    public List<BehaviorPattern> FindByGame(string gameKey)
        => _patterns.Where(p => p.GameKey == gameKey).ToList();

    /// <summary>태그별 패턴 수 통계</summary>
    public Dictionary<SystemTag, int> GetTagStats()
        => _patterns.GroupBy(p => p.Tag)
                    .ToDictionary(g => g.Key, g => g.Count());

    public void Save()
    {
        try
        {
            var json = JsonSerializer.Serialize(_patterns, JsonOpts);
            File.WriteAllText(_dbPath, json);
        }
        catch { /* UI에서 에러 표시 */ }
    }

    public void Load()
    {
        if (!File.Exists(_dbPath)) return;
        try
        {
            var json = File.ReadAllText(_dbPath);
            _patterns = JsonSerializer.Deserialize<List<BehaviorPattern>>(json, JsonOpts) ?? new();
        }
        catch
        {
            _patterns = new();
        }
    }
}
