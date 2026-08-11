using System;
using System.Diagnostics;
using System.IO;

internal static class GptBridgeLauncher
{
    private static string FirstExisting(params string[] candidates)
    {
        foreach (var candidate in candidates) if (File.Exists(candidate)) return candidate;
        return null;
    }

    public static int Main(string[] args)
    {
        string root = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string interpreter = FirstExisting(
            Path.Combine(root, "runtime", "python", "pythonw.exe"),
            Path.Combine(root, "runtime", "python", "python.exe"),
            Path.Combine(root, "runtime", "python", "Scripts", "pythonw.exe"),
            Path.Combine(root, "runtime", "python", "Scripts", "python.exe"),
            Path.Combine(root, ".venv", "Scripts", "pythonw.exe"),
            Path.Combine(root, ".venv", "Scripts", "python.exe")
        );
        if (interpreter == null)
        {
            Console.Error.WriteLine("Gpt-Bridge runtime is not installed. Run installer\\install.ps1 first.");
            return 2;
        }
        string script = Path.Combine(root, "tools", "run_bridge_service.py");
        string pid = Path.Combine(root, "data", "service.pid");
        var info = new ProcessStartInfo
        {
            FileName = interpreter,
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            Arguments = $"\"{script}\" --repo-root \"{root}\" --pid-file \"{pid}\" --open-browser"
        };
        try
        {
            var process = Process.Start(info);
            return process == null ? 3 : 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.Message);
            return 3;
        }
    }
}
