// HW1ClassicFix-Setup - installer for the Homeworld 1 Classic fix (Homeworld Remastered Collection,
// 2023 build 2.303 of Homeworld1Classic\exe\Homeworld.exe).
//
// Built with the in-box .NET Framework C# compiler (C# 5): scripts\build_installer.ps1.
// The byte table (PatchTable.cs) is generated from scripts\dockfix_patch.py.
//
//   HW1ClassicFix-Setup.exe                      window: detect, Browse, Install, Remove
//   HW1ClassicFix-Setup.exe --check   <folder>   console: report the state of the exe
//   HW1ClassicFix-Setup.exe --install <folder>   console: install (exit 0 = ok)
//   HW1ClassicFix-Setup.exe --remove  <folder>   console: restore the original bytes
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Homeworld 1 Classic Fix")]
[assembly: AssemblyDescription("Docking, widescreen and Windows 10/11 fixes for Homeworld 1 Classic (Homeworld Remastered Collection)")]
[assembly: AssemblyProduct("Homeworld 1 Classic Fix")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace HW1ClassicFix
{
    public sealed class Site
    {
        public readonly uint Va;
        public readonly byte[] Old;
        public readonly byte[] New;
        public readonly string Group;
        public readonly string Note;
        public readonly byte[][] Legacy;

        public Site(uint va, string oldHex, string newHex, string group, string note, string[] legacyHex)
        {
            Va = va; Old = Hex(oldHex); New = Hex(newHex); Group = group; Note = note;
            if (legacyHex != null)
            {
                Legacy = new byte[legacyHex.Length][];
                for (int i = 0; i < legacyHex.Length; i++) Legacy[i] = Hex(legacyHex[i]);
            }
            if (Old.Length != New.Length) throw new InvalidDataException("size mismatch at 0x" + va.ToString("x"));
        }

        static byte[] Hex(string s)
        {
            byte[] b = new byte[s.Length / 2];
            for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(s.Substring(2 * i, 2), 16);
            return b;
        }
    }

    sealed class Section { public uint Va; public uint Size; public uint Raw; }

    /// <summary>Same logic as dockfix_patch.py: per-site classification, idempotent apply / revert.</summary>
    public sealed class Patcher
    {
        public readonly byte[] Data;
        readonly List<Section> secs = new List<Section>();

        public Patcher(byte[] data)
        {
            Data = data;
            if (data.Length < 0x40) return;
            try
            {
                int pe = BitConverter.ToInt32(data, 0x3c);
                int nsec = BitConverter.ToUInt16(data, pe + 6);
                int optsz = BitConverter.ToUInt16(data, pe + 20);
                uint imageBase = BitConverter.ToUInt32(data, pe + 24 + 28);
                for (int i = 0; i < nsec; i++)
                {
                    int o = pe + 24 + optsz + 40 * i;
                    uint vsize = BitConverter.ToUInt32(data, o + 8);
                    uint va = BitConverter.ToUInt32(data, o + 12);
                    uint rsize = BitConverter.ToUInt32(data, o + 16);
                    uint raw = BitConverter.ToUInt32(data, o + 20);
                    secs.Add(new Section { Va = imageBase + va, Size = Math.Max(vsize, rsize), Raw = raw });
                }
            }
            catch (Exception) { secs.Clear(); }
        }

        public bool RightSize { get { return Data.Length == PatchTable.PeSize && secs.Count > 0; } }

        int Va2Off(uint va)
        {
            foreach (Section s in secs)
                if (va >= s.Va && va < s.Va + s.Size) return (int)(s.Raw + (va - s.Va));
            throw new InvalidDataException("address 0x" + va.ToString("x") + " is outside the file");
        }

        static bool Eq(byte[] data, int off, byte[] b)
        {
            if (off < 0 || off + b.Length > data.Length) return false;
            for (int i = 0; i < b.Length; i++) if (data[off + i] != b[i]) return false;
            return true;
        }

        public string Classify(Site s)
        {
            int off = Va2Off(s.Va);
            if (Eq(Data, off, s.Old)) return "original";
            if (Eq(Data, off, s.New)) return "patched";
            if (s.Legacy != null) foreach (byte[] l in s.Legacy) if (Eq(Data, off, l)) return "legacy";
            return "foreign";
        }

        public Dictionary<string, int> Counts(List<string> foreignNotes)
        {
            var c = new Dictionary<string, int> { { "original", 0 }, { "patched", 0 }, { "legacy", 0 }, { "foreign", 0 } };
            foreach (Site s in PatchTable.Sites)
            {
                string st = Classify(s);
                c[st]++;
                if (st == "foreign" && foreignNotes != null) foreignNotes.Add("0x" + s.Va.ToString("x") + " (" + s.Note + ")");
            }
            return c;
        }

        /// <summary>Apply (forward) or revert every site. Sites already in the target state are skipped.
        /// A site with unknown bytes aborts before anything is written.</summary>
        public int Transform(bool forward, out int skipped)
        {
            skipped = 0;
            var todo = new List<Site>();
            foreach (Site s in PatchTable.Sites)
            {
                string st = Classify(s);
                string want = forward ? "patched" : "original";
                string src = forward ? "original" : "patched";
                if (st == want) { skipped++; continue; }
                if (st != src && st != "legacy")
                    throw new InvalidOperationException("the bytes at 0x" + s.Va.ToString("x") + " (" + s.Note + ") were changed by something else");
                todo.Add(s);
            }
            foreach (Site s in todo)
            {
                byte[] b = forward ? s.New : s.Old;
                Array.Copy(b, 0, Data, Va2Off(s.Va), b.Length);
            }
            return todo.Count;
        }

        public static string Sha256Hex(byte[] d)
        {
            using (var sha = SHA256.Create())
            {
                var sb = new StringBuilder();
                foreach (byte b in sha.ComputeHash(d)) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }
    }

    public static class Locator
    {
        public const string ExeRel = "Homeworld1Classic\\exe\\Homeworld.exe";

        public static List<string> AutoDetect()
        {
            var found = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            Action<string> add = delegate(string root)
            {
                if (string.IsNullOrEmpty(root)) return;
                string p;
                try { p = Path.GetFullPath(Path.Combine(root, ExeRel)); } catch (Exception) { return; }
                if (File.Exists(p) && seen.Add(p)) found.Add(p);
            };

            foreach (string steam in SteamRoots())
            {
                add(Path.Combine(steam, "steamapps\\common\\Homeworld"));
                string vdf = Path.Combine(steam, "steamapps\\libraryfolders.vdf");
                try
                {
                    if (File.Exists(vdf))
                        foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\"path\"\\s+\"([^\"]+)\""))
                            add(Path.Combine(m.Groups[1].Value.Replace("\\\\", "\\"), "steamapps\\common\\Homeworld"));
                }
                catch (Exception) { }
            }

            try
            {
                using (var hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry32))
                using (var games = hklm.OpenSubKey("SOFTWARE\\GOG.com\\Games"))
                {
                    if (games != null)
                        foreach (string name in games.GetSubKeyNames())
                            using (var g = games.OpenSubKey(name))
                            {
                                if (g == null) continue;
                                add(g.GetValue("path") as string);
                                add(g.GetValue("workingDir") as string);
                                string exe = g.GetValue("exe") as string;
                                if (!string.IsNullOrEmpty(exe)) { try { add(Path.GetDirectoryName(exe)); } catch (Exception) { } }
                            }
                }
            }
            catch (Exception) { }

            string pf86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
            string pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
            foreach (string b in new[] { pf86, pf })
            {
                if (string.IsNullOrEmpty(b)) continue;
                add(Path.Combine(b, "Steam\\steamapps\\common\\Homeworld"));
                add(Path.Combine(b, "GOG Galaxy\\Games\\Homeworld Remastered"));
                add(Path.Combine(b, "GOG Galaxy\\Games\\Homeworld Remastered Collection"));
            }
            try
            {
                foreach (DriveInfo d in DriveInfo.GetDrives())
                {
                    if (d.DriveType != DriveType.Fixed) continue;
                    string r = d.RootDirectory.FullName;
                    add(Path.Combine(r, "SteamLibrary\\steamapps\\common\\Homeworld"));
                    add(Path.Combine(r, "Steam\\steamapps\\common\\Homeworld"));
                    add(Path.Combine(r, "Games\\Steam\\steamapps\\common\\Homeworld"));
                    add(Path.Combine(r, "GOG Games\\Homeworld Remastered Collection"));
                    add(Path.Combine(r, "Games\\GOG\\Homeworld Remastered Collection"));
                    add(Path.Combine(r, "Games\\Homeworld Remastered Collection"));
                }
            }
            catch (Exception) { }
            return found;
        }

        static List<string> SteamRoots()
        {
            var list = new List<string>();
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey("Software\\Valve\\Steam"))
                    if (k != null) { string p = k.GetValue("SteamPath") as string; if (!string.IsNullOrEmpty(p)) list.Add(p.Replace('/', '\\')); }
            }
            catch (Exception) { }
            try
            {
                using (var hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry32))
                using (var k = hklm.OpenSubKey("SOFTWARE\\Valve\\Steam"))
                    if (k != null) { string p = k.GetValue("InstallPath") as string; if (!string.IsNullOrEmpty(p)) list.Add(p); }
            }
            catch (Exception) { }
            return list;
        }

        /// <summary>The user picked a folder: accept the collection root, Homeworld1Classic, its exe folder,
        /// or any folder inside the collection (we look in the folder, its children and up to five parents).</summary>
        public static string ResolveFromFolder(string folder)
        {
            string dir = folder;
            for (int up = 0; up < 6 && !string.IsNullOrEmpty(dir); up++)
            {
                foreach (string c in new[] { Path.Combine(dir, ExeRel), Path.Combine(dir, "exe\\Homeworld.exe"), Path.Combine(dir, "Homeworld.exe") })
                {
                    try { if (File.Exists(c) && LooksLikeClassic(c)) return Path.GetFullPath(c); } catch (Exception) { }
                }
                try { DirectoryInfo p = Directory.GetParent(dir); dir = p == null ? null : p.FullName; } catch (Exception) { dir = null; }
            }
            return null;
        }

        static bool LooksLikeClassic(string exe)
        {
            try
            {
                if (exe.EndsWith("\\" + ExeRel, StringComparison.OrdinalIgnoreCase)) return true;
                return new FileInfo(exe).Length == PatchTable.PeSize;
            }
            catch (Exception) { return false; }
        }

        public static string RootOf(string exe)
        {
            try
            {
                if (exe.EndsWith("\\" + ExeRel, StringComparison.OrdinalIgnoreCase))
                    return exe.Substring(0, exe.Length - ExeRel.Length - 1);
                return Path.GetDirectoryName(exe);
            }
            catch (Exception) { return exe; }
        }
    }

    public static class Settings
    {
        const string Sub = "SOFTWARE\\Sierra On-Line\\Homeworld";

        /// <summary>The patched game keeps its settings under HKEY_CURRENT_USER. Copy the old machine-wide
        /// values there once, so an existing player keeps the resolution they had.</summary>
        public static string Migrate()
        {
            try
            {
                using (var user = Registry.CurrentUser.CreateSubKey(Sub))
                {
                    if (user.GetValue("screenWidth") != null) return "Your saved game settings are already in your user profile.";
                    using (var hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry32))
                    using (var old = hklm.OpenSubKey(Sub))
                    {
                        if (old == null || old.GetValue("screenWidth") == null)
                            return "No earlier settings found: the game will start at your desktop resolution.";
                        int n = 0;
                        foreach (string name in old.GetValueNames())
                        {
                            user.SetValue(name, old.GetValue(name), old.GetValueKind(name));
                            n++;
                        }
                        return "Copied " + n + " saved settings (" + old.GetValue("screenWidth") + "x" + old.GetValue("screenHeight") + ") into your user profile.";
                    }
                }
            }
            catch (Exception ex)
            {
                return "Settings were not copied (" + ex.Message + "); the game will start at your desktop resolution.";
            }
        }
    }

    public sealed class Result
    {
        public bool Ok;
        public string Message;
        public string Detail;
        public static Result Fail(string m, string d) { return new Result { Ok = false, Message = m, Detail = d }; }
        public static Result Good(string m, string d) { return new Result { Ok = true, Message = m, Detail = d }; }
    }

    public static class Installer
    {
        const string Unsupported = "This Homeworld.exe is not the 2023 build (2.303) that this fix was made for. If Steam shows the game as up to date, use 'Verify integrity of game files' and run the installer again.";

        public static bool GameRunning()
        {
            try { return Process.GetProcessesByName("Homeworld").Length > 0; } catch (Exception) { return false; }
        }

        static string Describe(Dictionary<string, int> c)
        {
            int total = PatchTable.Sites.Length;
            if (c["foreign"] > 0) return "unsupported build (" + c["foreign"] + " of " + total + " places hold unexpected bytes)";
            if (c["patched"] == total) return "fix " + PatchTable.Version + " installed";
            if (c["original"] == total) return "fix not installed";
            return "an earlier version of the fix is installed (" + c["patched"] + " of " + total + " changes present)";
        }

        public static Result Inspect(string exe)
        {
            byte[] data;
            try { data = File.ReadAllBytes(exe); } catch (Exception ex) { return Result.Fail("Could not read " + exe, ex.Message); }
            var p = new Patcher(data);
            if (!p.RightSize) return Result.Fail(Unsupported, "size " + data.Length + ", expected " + PatchTable.PeSize);
            var notes = new List<string>();
            var c = p.Counts(notes);
            string d = "original " + c["original"] + ", patched " + c["patched"] + ", earlier build " + c["legacy"] + ", unexpected " + c["foreign"] + " of " + PatchTable.Sites.Length;
            if (c["foreign"] > 0) return Result.Fail(Unsupported + "\n\nUnexpected bytes at: " + string.Join(", ", notes.ToArray()), d);
            return Result.Good(Describe(c), d);
        }

        public static Result Install(string exe, Action<string> log)
        {
            if (GameRunning()) return Result.Fail("Homeworld 1 Classic appears to be running. Close the game and try again.", null);
            byte[] data;
            try { data = File.ReadAllBytes(exe); } catch (Exception ex) { return Result.Fail("Could not read " + exe, ex.Message); }
            var p = new Patcher(data);
            if (!p.RightSize) return Result.Fail(Unsupported, "size " + data.Length + ", expected " + PatchTable.PeSize);
            var notes = new List<string>();
            var c = p.Counts(notes);
            if (c["foreign"] > 0)
                return Result.Fail("Another modification already changed " + c["foreign"] + " of the places this fix needs, so the two cannot be combined.\n\n" + string.Join("\n", notes.ToArray()), null);
            string sha = Patcher.Sha256Hex(data);
            int skipped, changed;
            try { changed = p.Transform(true, out skipped); }
            catch (Exception ex) { return Result.Fail("Nothing was changed: " + ex.Message, null); }
            if (changed == 0) return Result.Good("The fix (version " + PatchTable.Version + ") is already installed. Nothing to do.", null);
            try
            {
                string bak = exe + (sha == PatchTable.OriginalSha256 ? ".orig-2.303" : ".before-dockfix");
                if (!File.Exists(bak)) { File.Copy(exe, bak); log("Backup saved: " + Path.GetFileName(bak)); }
                else log("Backup already present: " + Path.GetFileName(bak));
                File.WriteAllBytes(exe, p.Data);
            }
            catch (UnauthorizedAccessException)
            {
                return Result.Fail("Windows did not allow writing to the game folder. Right-click the installer, choose 'Run as administrator' and try again.", exe);
            }
            catch (IOException ex)
            {
                return Result.Fail("The game file could not be written (" + ex.Message + "). Make sure the game and its launcher are closed.", exe);
            }
            log("Applied " + changed + " change(s)" + (skipped > 0 ? ", " + skipped + " already in place" : "") + ".");
            log(Settings.Migrate());
            return Result.Good("Fix " + PatchTable.Version + " installed.", null);
        }

        public static Result Remove(string exe, Action<string> log)
        {
            if (GameRunning()) return Result.Fail("Homeworld 1 Classic appears to be running. Close the game and try again.", null);
            byte[] data;
            try { data = File.ReadAllBytes(exe); } catch (Exception ex) { return Result.Fail("Could not read " + exe, ex.Message); }
            var p = new Patcher(data);
            if (!p.RightSize) return Result.Fail(Unsupported, null);
            int skipped, changed;
            try { changed = p.Transform(false, out skipped); }
            catch (Exception ex) { return Result.Fail("Nothing was changed: " + ex.Message, null); }
            if (changed == 0) return Result.Good("The fix is not installed. Nothing to do.", null);
            try { File.WriteAllBytes(exe, p.Data); }
            catch (UnauthorizedAccessException)
            {
                return Result.Fail("Windows did not allow writing to the game folder. Right-click the installer, choose 'Run as administrator' and try again.", exe);
            }
            catch (IOException ex)
            {
                return Result.Fail("The game file could not be written (" + ex.Message + "). Make sure the game and its launcher are closed.", exe);
            }
            string sha = Patcher.Sha256Hex(p.Data);
            log("Restored " + changed + " change(s)" + (sha == PatchTable.OriginalSha256 ? "; the file is byte-for-byte the original again." : "; other modifications remain."));
            return Result.Good("Fix removed.", null);
        }
    }

    public sealed class MainForm : Form
    {
        readonly TextBox pathBox = new TextBox();
        readonly Label status = new Label();
        readonly Button browse = new Button();
        readonly Button install = new Button();
        readonly Button remove = new Button();
        readonly Button close = new Button();
        readonly TextBox log = new TextBox();
        string exePath;

        public MainForm()
        {
            Text = "Homeworld 1 Classic Fix " + PatchTable.Version;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Font;
            Font = new Font("Segoe UI", 9f);
            ClientSize = new Size(600, 380);

            var intro = new Label
            {
                Text = "Fixes fighters and corvettes that circle the Mothership instead of docking, lists every resolution your display supports, corrects the move order at widescreen ratios, and makes the game keep its settings on Windows 10/11.",
                Location = new Point(12, 10), Size = new Size(576, 48)
            };
            var pathLabel = new Label { Text = "Homeworld Remastered Collection folder:", Location = new Point(12, 64), AutoSize = true };
            pathBox.Location = new Point(12, 84); pathBox.Size = new Size(480, 23); pathBox.ReadOnly = true;
            browse.Text = "Browse..."; browse.Location = new Point(500, 83); browse.Size = new Size(88, 25);
            browse.Click += delegate { Browse(); };
            status.Location = new Point(12, 114); status.Size = new Size(576, 40);
            install.Text = "Install fix"; install.Location = new Point(12, 158); install.Size = new Size(120, 30);
            install.Click += delegate { DoInstall(); };
            remove.Text = "Remove fix"; remove.Location = new Point(140, 158); remove.Size = new Size(120, 30);
            remove.Click += delegate { DoRemove(); };
            close.Text = "Close"; close.Location = new Point(468, 158); close.Size = new Size(120, 30);
            close.Click += delegate { Close(); };
            log.Location = new Point(12, 198); log.Size = new Size(576, 170);
            log.Multiline = true; log.ReadOnly = true; log.ScrollBars = ScrollBars.Vertical;
            Controls.AddRange(new Control[] { intro, pathLabel, pathBox, browse, status, install, remove, close, log });
            AcceptButton = install;
            CancelButton = close;
            Load += delegate { Detect(); };
        }

        void Log(string s)
        {
            log.AppendText(s + Environment.NewLine);
        }

        void Detect()
        {
            List<string> found = Locator.AutoDetect();
            if (found.Count == 0)
            {
                Log("No Homeworld Remastered Collection install was found automatically. Click Browse... and pick its folder.");
                exePath = null;
            }
            else
            {
                exePath = found[0];
                Log("Found: " + Locator.RootOf(exePath));
                for (int i = 1; i < found.Count; i++) Log("Also found (use Browse... to pick it instead): " + Locator.RootOf(found[i]));
            }
            Refresh();
        }

        new void Refresh()
        {
            if (exePath == null)
            {
                pathBox.Text = "";
                status.Text = "Game not found. Use Browse... to select the Homeworld Remastered Collection folder.";
                install.Enabled = remove.Enabled = false;
                return;
            }
            pathBox.Text = Locator.RootOf(exePath);
            Result r = Installer.Inspect(exePath);
            status.Text = r.Ok ? "Homeworld 1 Classic found: " + r.Message + "." : r.Message;
            install.Enabled = r.Ok && r.Message != "fix " + PatchTable.Version + " installed";
            remove.Enabled = r.Ok && r.Message != "fix not installed";
            if (!r.Ok && r.Detail != null) Log(r.Detail);
        }

        void Browse()
        {
            using (var dlg = new FolderBrowserDialog())
            {
                dlg.Description = "Select the Homeworld Remastered Collection folder (it contains 'Homeworld1Classic'), or any folder inside it.";
                dlg.ShowNewFolderButton = false;
                if (exePath != null) dlg.SelectedPath = Locator.RootOf(exePath);
                while (true)
                {
                    if (dlg.ShowDialog(this) != DialogResult.OK) return;
                    string exe = Locator.ResolveFromFolder(dlg.SelectedPath);
                    if (exe != null)
                    {
                        exePath = exe;
                        Log("Selected: " + Locator.RootOf(exe));
                        Refresh();
                        return;
                    }
                    MessageBox.Show(this,
                        "Homeworld 1 Classic was not found under:\n" + dlg.SelectedPath +
                        "\n\nPick the Homeworld Remastered Collection folder (the one that contains 'Homeworld1Classic'), or any folder inside it, and try again.",
                        "Not found", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            }
        }

        void DoInstall()
        {
            Result r = Installer.Install(exePath, Log);
            Log(r.Message);
            MessageBox.Show(this, r.Message + (r.Detail != null ? "\n\n" + r.Detail : ""), r.Ok ? "Done" : "Not installed",
                MessageBoxButtons.OK, r.Ok ? MessageBoxIcon.Information : MessageBoxIcon.Error);
            Refresh();
        }

        void DoRemove()
        {
            if (MessageBox.Show(this, "Restore the original Homeworld.exe (all changes made by this fix are undone)?", "Remove fix",
                MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            Result r = Installer.Remove(exePath, Log);
            Log(r.Message);
            MessageBox.Show(this, r.Message + (r.Detail != null ? "\n\n" + r.Detail : ""), r.Ok ? "Done" : "Not removed",
                MessageBoxButtons.OK, r.Ok ? MessageBoxIcon.Information : MessageBoxIcon.Error);
            Refresh();
        }
    }

    static class Program
    {
        [DllImport("kernel32.dll")] static extern bool AttachConsole(int pid);
        [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int h);

        [STAThread]
        static int Main(string[] args)
        {
            if (args.Length >= 1 && args[0].StartsWith("--")) return Cli(args);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
            return 0;
        }

        static int Cli(string[] a)
        {
            IntPtr h = GetStdHandle(-11);
            if (h == IntPtr.Zero || h == new IntPtr(-1)) AttachConsole(-1);
            string cmd = a[0].ToLowerInvariant();
            if (cmd == "--detect")
            {
                List<string> found = Locator.AutoDetect();
                foreach (string f in found) Console.WriteLine("found: " + Locator.RootOf(f) + "  (" + Installer.Inspect(f).Message + ")");
                if (found.Count == 0) Console.WriteLine("no Homeworld Remastered Collection install found automatically");
                return found.Count > 0 ? 0 : 2;
            }
            if (a.Length < 2) { Console.WriteLine("usage: --detect | --check <folder> | --install <folder> | --remove <folder>"); return 2; }
            string target = a[1];
            string exe = File.Exists(target) ? Path.GetFullPath(target) : Locator.ResolveFromFolder(target);
            if (exe == null) { Console.WriteLine("No Homeworld 1 Classic found under " + target); return 2; }
            Console.WriteLine("exe: " + exe);
            Result r;
            if (cmd == "--install") r = Installer.Install(exe, Console.WriteLine);
            else if (cmd == "--remove") r = Installer.Remove(exe, Console.WriteLine);
            else r = Installer.Inspect(exe);
            Console.WriteLine(r.Message);
            if (r.Detail != null) Console.WriteLine(r.Detail);
            return r.Ok ? 0 : 1;
        }
    }
}
