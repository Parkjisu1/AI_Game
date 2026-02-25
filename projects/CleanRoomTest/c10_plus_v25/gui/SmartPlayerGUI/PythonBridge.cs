using System.Diagnostics;
using System.Text.Json;

namespace SmartPlayerGUI;

/// <summary>
/// Python smart_player 시스템과의 브릿지.
/// subprocess로 Python 스크립트를 호출하고 결과를 파싱합니다.
/// </summary>
public class PythonBridge
{
    public string PythonExe { get; set; } = @"C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe";
    public string ScriptDir { get; set; } = @"E:\AI\projects\CleanRoomTest\c10_plus_v25";
    public string GameKey { get; set; } = "ash_n_veil";

    /// <summary>실행 중인 프로세스 (녹화/모방은 장시간)</summary>
    private Process? _activeProcess;

    public bool IsRunning => _activeProcess is { HasExited: false };

    public event Action<string>? OnOutput;
    public event Action<string>? OnError;
    public event Action<int>? OnExited;

    // ----- Record (녹화) -----

    public void StartRecording()
    {
        if (IsRunning) throw new InvalidOperationException("이미 프로세스 실행 중");
        RunAsync("run.py", $"{GameKey} record");
    }

    // ----- Smart Capture (AI 모방) -----

    public void StartSmartCapture()
    {
        if (IsRunning) throw new InvalidOperationException("이미 프로세스 실행 중");
        RunAsync("run.py", $"{GameKey} --smart");
    }

    // ----- Build Nav Graph (그래프 빌드만) -----

    public void BuildNavGraph()
    {
        if (IsRunning) throw new InvalidOperationException("이미 프로세스 실행 중");
        var script = "from smart_player.smart_capture import build_nav_graph; "
                   + "from genres import load_all_genres, find_game; "
                   + "load_all_genres(); "
                   + $"g, _ = find_game('{GameKey}'); "
                   + $"build_nav_graph('{GameKey}', g)";
        RunAsync("-c", script);
    }

    // ----- Custom Command -----

    public void RunCustomCommand(string command)
    {
        if (IsRunning) throw new InvalidOperationException("이미 프로세스 실행 중");

        if (command.StartsWith("python "))
            command = command[7..];

        if (command.StartsWith("run.py"))
            RunAsync("run.py", command[6..].Trim());
        else
            RunAsync("-c", command);
    }

    // ----- Stop -----

    public void Stop()
    {
        if (_activeProcess is { HasExited: false })
        {
            try
            {
                // Write stop signal file for graceful shutdown
                var stopFile = Path.Combine(ScriptDir, "recordings", GameKey, ".stop");
                Directory.CreateDirectory(Path.GetDirectoryName(stopFile)!);
                File.WriteAllText(stopFile, "stop");
            }
            catch { }

            // Wait a few seconds for graceful shutdown
            try
            {
                if (!_activeProcess.WaitForExit(5000))
                {
                    // Force kill if still running after 5s
                    _activeProcess.Kill(entireProcessTree: true);
                }
            }
            catch { }
        }
    }

    // ----- Recording Info -----

    public RecordingInfo? GetRecordingInfo()
    {
        var recPath = Path.Combine(ScriptDir, "recordings", GameKey, "recording.json");
        if (!File.Exists(recPath)) return null;

        try
        {
            var json = File.ReadAllText(recPath);
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            var info = new RecordingInfo
            {
                RecordingPath = recPath,
                GameKey = root.TryGetProperty("game", out var g) ? g.GetString() ?? "" : "",
                EventCount = root.TryGetProperty("events", out var e) ? e.GetArrayLength() : 0,
                RecordedAt = root.TryGetProperty("recorded_at", out var d) ? d.GetString() ?? "" : "",
            };

            // Count frames
            var framesDir = Path.Combine(ScriptDir, "recordings", GameKey, "frames");
            if (Directory.Exists(framesDir))
                info.FrameCount = Directory.GetFiles(framesDir, "*.png").Length;

            // Check for classifications
            var clsPath = Path.Combine(ScriptDir, "recordings", GameKey, "classifications.json");
            if (File.Exists(clsPath))
            {
                info.ClassificationsPath = clsPath;
                using var clsDoc = JsonDocument.Parse(File.ReadAllText(clsPath));
                info.ClassifiedCount = clsDoc.RootElement.EnumerateObject().Count();
            }

            // Check for nav graph
            var graphPath = Path.Combine(ScriptDir, "recordings", GameKey, "nav_graph.json");
            if (File.Exists(graphPath))
            {
                info.NavGraphPath = graphPath;
                using var graphDoc = JsonDocument.Parse(File.ReadAllText(graphPath));
                if (graphDoc.RootElement.TryGetProperty("nodes", out var nodes))
                    info.GraphNodeCount = nodes.EnumerateObject().Count();
                if (graphDoc.RootElement.TryGetProperty("edges", out var edges))
                    info.GraphEdgeCount = edges.GetArrayLength();
            }

            return info;
        }
        catch
        {
            return null;
        }
    }

    // ----- Internal -----

    private void RunAsync(string scriptOrFlag, string args = "")
    {
        var psi = new ProcessStartInfo
        {
            FileName = PythonExe,
            Arguments = scriptOrFlag.EndsWith(".py")
                ? $"\"{Path.Combine(ScriptDir, scriptOrFlag)}\" {args}"
                : $"{scriptOrFlag} \"{args}\"",
            WorkingDirectory = ScriptDir,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = System.Text.Encoding.UTF8,
            StandardErrorEncoding = System.Text.Encoding.UTF8,
        };

        // Clean env to avoid Claude Code interference
        psi.Environment.Remove("ANTHROPIC_API_KEY");
        psi.Environment.Remove("CLAUDECODE");
        psi.Environment.Remove("CLAUDE_CODE_ENTRYPOINT");
        psi.Environment["PYTHONIOENCODING"] = "utf-8";

        _activeProcess = new Process { StartInfo = psi, EnableRaisingEvents = true };

        _activeProcess.OutputDataReceived += (_, e) =>
        {
            if (e.Data != null) OnOutput?.Invoke(e.Data);
        };
        _activeProcess.ErrorDataReceived += (_, e) =>
        {
            if (e.Data != null) OnError?.Invoke(e.Data);
        };
        _activeProcess.Exited += (_, _) =>
        {
            OnExited?.Invoke(_activeProcess.ExitCode);
        };

        _activeProcess.Start();
        _activeProcess.BeginOutputReadLine();
        _activeProcess.BeginErrorReadLine();
    }
}

public class RecordingInfo
{
    public string RecordingPath { get; set; } = "";
    public string GameKey { get; set; } = "";
    public int EventCount { get; set; }
    public int FrameCount { get; set; }
    public string RecordedAt { get; set; } = "";
    public string ClassificationsPath { get; set; } = "";
    public int ClassifiedCount { get; set; }
    public string NavGraphPath { get; set; } = "";
    public int GraphNodeCount { get; set; }
    public int GraphEdgeCount { get; set; }
}
