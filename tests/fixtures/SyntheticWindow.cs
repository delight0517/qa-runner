using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

internal static class SyntheticWindow
{
    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Length > 0)
        {
            var child = Process.Start(new ProcessStartInfo
            {
                FileName = Environment.GetEnvironmentVariable("COMSPEC") ?? "cmd.exe",
                Arguments = "/c timeout /t 60 /nobreak >nul",
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            });
            if (child == null) throw new InvalidOperationException("Synthetic child process did not start.");
            File.WriteAllText(args[0], child.Id.ToString());
        }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var form = new Form
        {
            Text = "QA Runner Synthetic Private Window",
            ClientSize = new Size(560, 320),
            StartPosition = FormStartPosition.CenterScreen,
            BackColor = Color.FromArgb(35, 45, 60)
        };
        form.Controls.Add(new Label
        {
            Text = "Disposable test fixture",
            ForeColor = Color.White,
            AutoSize = true,
            Location = new Point(32, 42)
        });
        Application.Run(form);
    }
}
