// Machine B의 C:/projects/balloonflow/Assets/Editor/BalloonflowBuilder.cs 에 설치.
// Unity batch-mode에서 CLI로 호출:
//   Unity.exe -batchmode -quit -projectPath C:/projects/balloonflow \
//     -buildTarget Android -executeMethod Hermes.BalloonflowBuilder.BuildAndroid \
//     -logFile - -versionTag v1.2.3 -outputPath C:/projects/balloonflow/builds/latest.apk

using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Hermes
{
    public static class BalloonflowBuilder
    {
        public static void BuildAndroid()
        {
            string outputPath = GetArg("-outputPath") ?? "builds/latest.apk";
            string versionTag = GetArg("-versionTag");

            // 디렉토리 생성
            string dir = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                Directory.CreateDirectory(dir);

            // 활성 Scene 목록 수집 (Build Settings 기준)
            var scenes = new System.Collections.Generic.List<string>();
            foreach (var s in EditorBuildSettings.scenes)
            {
                if (s.enabled) scenes.Add(s.path);
            }
            if (scenes.Count == 0)
            {
                Debug.LogError("[BalloonflowBuilder] No enabled scenes in Build Settings");
                EditorApplication.Exit(1);
                return;
            }

            if (!string.IsNullOrEmpty(versionTag))
            {
                PlayerSettings.bundleVersion = versionTag;
                Debug.Log($"[BalloonflowBuilder] bundleVersion = {versionTag}");
            }

            // Android 설정 확인
            EditorUserBuildSettings.buildAppBundle = false;  // APK (AAB 아님)
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;

            var options = new BuildPlayerOptions
            {
                scenes = scenes.ToArray(),
                locationPathName = outputPath,
                target = BuildTarget.Android,
                options = BuildOptions.None,
            };

            var report = BuildPipeline.BuildPlayer(options);
            var summary = report.summary;

            Debug.Log($"[BalloonflowBuilder] result={summary.result} size={summary.totalSize} errors={summary.totalErrors} warnings={summary.totalWarnings}");
            if (summary.result == BuildResult.Succeeded)
            {
                Debug.Log($"[BalloonflowBuilder] APK_PATH={Path.GetFullPath(outputPath)}");
                EditorApplication.Exit(0);
            }
            else
            {
                Debug.LogError($"[BalloonflowBuilder] BUILD FAILED: {summary.result}");
                EditorApplication.Exit(1);
            }
        }

        private static string GetArg(string name)
        {
            var args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == name) return args[i + 1];
            }
            return null;
        }
    }
}
