// ProjectHub Unity MCP — Tier 1 HTTP Bridge
//
// 위치: Assets/Editor/McpBridge.cs
// 시작: [InitializeOnLoad] → Editor 가동 시 자동 listener 시작
// 종료: EditorApplication.quitting → listener 정상 종료
//
// 파이프라인:
//   외부 RPC ──HTTP──> :7901 ──worker thread──> _mainThreadQueue ──EditorApplication.update──> Unity API
//                                       │
//                                       └── TaskCompletionSource로 worker thread에 응답
//
// 1차 슬라이스: inspect.scene.list 단일 핸들러. 검증 후 나머지 15 툴 추가.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace ProjectHub.Mcp
{
    [InitializeOnLoad]
    public static class McpBridge
    {
        private const string ListenerUrl = "http://localhost:7901/";
        private const int LogRingMax = 500;
        private static HttpListener _listener;
        private static Thread _listenerThread;
        private static readonly ConcurrentQueue<Action> _mainThreadQueue = new();
        private static readonly CancellationTokenSource _cts = new();

        // 로그 링 버퍼 — Application.logMessageReceivedThreaded 콜백
        private static readonly LinkedList<LogEntry> _logRing = new();
        private static readonly object _logLock = new();
        // 최근 컴파일 결과 — CompilationPipeline 이벤트
        private static readonly List<CompileMessage> _lastCompileMessages = new();
        private static volatile bool _isCompiling = false;

        struct LogEntry
        {
            public long unixMs;
            public string message;
            public string stack;
            public LogType type;
        }
        struct CompileMessage
        {
            public string file;
            public int line;
            public int column;
            public string message;
            public string assembly;
        }

        static McpBridge()
        {
            // 도메인 리로드 직전에 결정적으로 listener를 닫아야 http.sys 바인딩이 즉시 해제된다.
            // quitting만으로는 스크립트 저장→리컴파일 시 누수되어 다음 도메인이 EADDRINUSE를 맞는다.
            AssemblyReloadEvents.beforeAssemblyReload -= Stop;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.quitting -= Stop;
            EditorApplication.quitting += Stop;
            EditorApplication.update -= PumpMainThread;
            EditorApplication.update += PumpMainThread;

            // 로그/컴파일 이벤트 구독 (idempotent: -= 후 +=)
            Application.logMessageReceivedThreaded -= OnLogMessage;
            Application.logMessageReceivedThreaded += OnLogMessage;
            CompilationPipeline.compilationStarted -= OnCompileStarted;
            CompilationPipeline.compilationStarted += OnCompileStarted;
            CompilationPipeline.compilationFinished -= OnCompileFinished;
            CompilationPipeline.compilationFinished += OnCompileFinished;
            CompilationPipeline.assemblyCompilationFinished -= OnAssemblyCompiled;
            CompilationPipeline.assemblyCompilationFinished += OnAssemblyCompiled;

            try { Start(); }
            catch (Exception e) { Debug.LogError($"[McpBridge] start failed: {e.Message}"); }
        }

        // ── Log capture ──
        private static void OnLogMessage(string message, string stack, LogType type)
        {
            var e = new LogEntry
            {
                unixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                message = message ?? "",
                stack = stack ?? "",
                type = type,
            };
            lock (_logLock)
            {
                _logRing.AddLast(e);
                while (_logRing.Count > LogRingMax) _logRing.RemoveFirst();
            }
        }

        private static void OnCompileStarted(object _) { _isCompiling = true; }
        private static void OnCompileFinished(object _) { _isCompiling = false; }
        private static void OnAssemblyCompiled(string assembly, CompilerMessage[] messages)
        {
            if (messages == null) return;
            lock (_logLock)
            {
                // 새 어셈블리 컴파일 시작 시 해당 어셈블리 메시지만 교체
                _lastCompileMessages.RemoveAll(m => m.assembly == assembly);
                foreach (var m in messages)
                {
                    if (m.type != CompilerMessageType.Error && m.type != CompilerMessageType.Warning) continue;
                    _lastCompileMessages.Add(new CompileMessage
                    {
                        file = m.file ?? "",
                        line = m.line,
                        column = m.column,
                        message = m.message ?? "",
                        assembly = assembly ?? "",
                    });
                }
            }
        }

        private static void Start()
        {
            if (_listener != null && _listener.IsListening) return;

            _listener = new HttpListener();
            _listener.Prefixes.Add(ListenerUrl);
            _listener.Start();

            _listenerThread = new Thread(ListenLoop) { IsBackground = true, Name = "McpBridge-Listener" };
            _listenerThread.Start();

            Debug.Log($"[McpBridge] listening on {ListenerUrl}");
        }

        private static void Stop()
        {
            try
            {
                _cts.Cancel();
                if (_listener != null)
                {
                    if (_listener.IsListening) _listener.Stop();
                    _listener.Close();
                    _listener = null;
                }
                Debug.Log("[McpBridge] stopped");
            }
            catch (Exception e) { Debug.LogWarning($"[McpBridge] stop err: {e.Message}"); }
        }

        // ── Worker thread loop: accept → route → respond ──
        private static void ListenLoop()
        {
            while (!_cts.IsCancellationRequested && _listener != null && _listener.IsListening)
            {
                HttpListenerContext ctx;
                try { ctx = _listener.GetContext(); }
                catch (HttpListenerException) { return; }   // listener stopped
                catch (ObjectDisposedException) { return; }
                catch (Exception e) { Debug.LogWarning($"[McpBridge] accept err: {e.Message}"); continue; }

                ThreadPool.QueueUserWorkItem(_ => HandleRequest(ctx));
            }
        }

        private static void HandleRequest(HttpListenerContext ctx)
        {
            try
            {
                var path = ctx.Request.Url.AbsolutePath.Trim('/');
                string body = "";
                using (var sr = new StreamReader(ctx.Request.InputStream, Encoding.UTF8))
                    body = sr.ReadToEnd();

                var responseJson = RouteAsync(path, body).GetAwaiter().GetResult();

                ctx.Response.StatusCode = 200;
                ctx.Response.ContentType = "application/json; charset=utf-8";
                var bytes = Encoding.UTF8.GetBytes(responseJson);
                ctx.Response.ContentLength64 = bytes.Length;
                ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
                ctx.Response.OutputStream.Close();
            }
            catch (Exception e)
            {
                try
                {
                    ctx.Response.StatusCode = 500;
                    var msg = $"{{\"ok\":false,\"error\":{{\"code\":\"unity.bridge_error\",\"message\":{Quote(e.Message)}}}}}";
                    var bytes = Encoding.UTF8.GetBytes(msg);
                    ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
                    ctx.Response.OutputStream.Close();
                }
                catch { /* swallow */ }
            }
        }

        // ── Route ──
        private static async Task<string> RouteAsync(string path, string body)
        {
            switch (path)
            {
                case "inspect.scene.list":
                    return await DispatchToMainThread(InspectSceneList);
                case "inspect.console.read_errors":
                    return InspectConsoleReadErrors(body);   // 로그 버퍼는 락만 잡으면 됨, 메인 스레드 불필요
                case "inspect.compilation.status":
                    return InspectCompilationStatus();
                case "ping":
                    return "{\"ok\":true,\"pong\":true}";
                default:
                    return $"{{\"ok\":false,\"error\":{{\"code\":\"mcp.unknown_tool\",\"message\":{Quote(path)}}}}}";
            }
        }

        // ── Main thread marshalling ──
        private static Task<T> DispatchToMainThread<T>(Func<T> work)
        {
            var tcs = new TaskCompletionSource<T>();
            _mainThreadQueue.Enqueue(() =>
            {
                try { tcs.SetResult(work()); }
                catch (Exception e) { tcs.SetException(e); }
            });
            return tcs.Task;
        }

        private static void PumpMainThread()
        {
            while (_mainThreadQueue.TryDequeue(out var action))
            {
                try { action(); }
                catch (Exception e) { Debug.LogError($"[McpBridge] main pump err: {e}"); }
            }
        }

        // ── Tool: inspect.console.read_errors ──
        private static string InspectConsoleReadErrors(string bodyJson)
        {
            // 파라미터 파싱 — naive (since/limit). 빈 body면 default.
            long since = 0;
            int limit = 100;
            if (!string.IsNullOrEmpty(bodyJson))
            {
                var sinceIdx = bodyJson.IndexOf("\"since_unix_ms\"");
                if (sinceIdx >= 0)
                {
                    var colon = bodyJson.IndexOf(':', sinceIdx);
                    var rest = bodyJson.Substring(colon + 1);
                    long.TryParse(new string(rest.TakeWhile(c => char.IsDigit(c)).ToArray()), out since);
                }
                var limitIdx = bodyJson.IndexOf("\"limit\"");
                if (limitIdx >= 0)
                {
                    var colon = bodyJson.IndexOf(':', limitIdx);
                    var rest = bodyJson.Substring(colon + 1).TrimStart();
                    int.TryParse(new string(rest.TakeWhile(c => char.IsDigit(c)).ToArray()), out limit);
                }
            }
            if (limit <= 0) limit = 100;

            var sb = new StringBuilder();
            sb.Append("{\"ok\":true,\"data\":{\"errors\":[");
            int n = 0;
            lock (_logLock)
            {
                // 최신부터 역순으로 limit개 — Error/Exception만
                var rev = new List<LogEntry>(_logRing);
                rev.Reverse();
                bool first = true;
                foreach (var e in rev)
                {
                    if (e.type != LogType.Error && e.type != LogType.Exception && e.type != LogType.Assert) continue;
                    if (e.unixMs < since) continue;
                    if (n >= limit) break;
                    if (!first) sb.Append(',');
                    first = false;
                    sb.Append("{\"timestamp_ms\":").Append(e.unixMs)
                      .Append(",\"type\":\"").Append(e.type.ToString()).Append("\"")
                      .Append(",\"message\":").Append(Quote(e.message))
                      .Append(",\"stack\":").Append(Quote(e.stack))
                      .Append("}");
                    n++;
                }
            }
            sb.Append("],\"returned\":").Append(n);
            sb.Append(",\"server_time_ms\":").Append(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
            sb.Append("}}");
            return sb.ToString();
        }

        // ── Tool: inspect.compilation.status ──
        private static string InspectCompilationStatus()
        {
            var sb = new StringBuilder();
            sb.Append("{\"ok\":true,\"data\":{");
            sb.Append("\"is_compiling\":").Append(_isCompiling ? "true" : "false");
            sb.Append(",\"messages\":[");
            int errorCount = 0, warnCount = 0;
            lock (_logLock)
            {
                bool first = true;
                foreach (var m in _lastCompileMessages)
                {
                    var isErr = m.message.Contains("error CS") || m.message.StartsWith("error ");
                    if (isErr) errorCount++; else warnCount++;
                    if (!first) sb.Append(',');
                    first = false;
                    sb.Append("{\"file\":").Append(Quote(m.file))
                      .Append(",\"line\":").Append(m.line)
                      .Append(",\"column\":").Append(m.column)
                      .Append(",\"assembly\":").Append(Quote(m.assembly))
                      .Append(",\"message\":").Append(Quote(m.message))
                      .Append(",\"is_error\":").Append(isErr ? "true" : "false")
                      .Append("}");
                }
            }
            sb.Append("],\"error_count\":").Append(errorCount);
            sb.Append(",\"warning_count\":").Append(warnCount);
            sb.Append("}}");
            return sb.ToString();
        }

        // ── Tool: inspect.scene.list ──
        private static string InspectSceneList()
        {
            var build = EditorBuildSettings.scenes
                .Where(s => s.enabled)
                .Select(s => s.path)
                .ToArray();

            var open = new System.Collections.Generic.List<string>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                var sc = SceneManager.GetSceneAt(i);
                if (sc.IsValid()) open.Add(sc.path);
            }
            var active = SceneManager.GetActiveScene().path ?? "";

            var sb = new StringBuilder();
            sb.Append("{\"ok\":true,\"data\":{");
            sb.Append("\"build_settings\":[").Append(string.Join(",", build.Select(Quote))).Append("],");
            sb.Append("\"open_scenes\":[").Append(string.Join(",", open.Select(Quote))).Append("],");
            sb.Append("\"active_scene\":").Append(Quote(active));
            sb.Append("}}");
            return sb.ToString();
        }

        // ── JSON 문자열 escape (Unity JsonUtility는 dictionary/array 직렬화 약함) ──
        private static string Quote(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder(s.Length + 8);
            sb.Append('"');
            foreach (var c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.AppendFormat("\\u{0:x4}", (int)c);
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
            return sb.ToString();
        }
    }
}
