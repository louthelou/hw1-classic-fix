# build_installer.ps1 - build HW1ClassicFix-Setup.exe with the C# compiler that ships inside
# Windows (.NET Framework 4.x, no SDK or Visual Studio needed), optionally self-test it against an
# unmodified 2023 Homeworld.exe, and optionally stage a release zip.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
#       [-Version 1.0.0]            version string compiled into the installer
#       [-OriginalExe <path>]       an unmodified Homeworld1Classic\exe\Homeworld.exe (2023 build,
#                                   sha256 421c114e...) used for the self-test; tests are skipped
#                                   when it is absent
#       [-StageDir <dir>]           copy the exe + README there and zip them (release packaging)
#       [-SkipTests]
#
# Output: build\HW1ClassicFix-Setup.exe. The patch table (installer\PatchTable.cs) is regenerated
# from scripts\dockfix_patch.py when Python 3 is available; otherwise the committed copy is used.
param(
    [string]$Version = "1.0.0",
    [string]$OriginalExe = "",
    [string]$StageDir = "",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { throw "csc.exe not found at $csc (needs .NET Framework 4.x, part of Windows 10/11)" }
New-Item -ItemType Directory -Force build | Out-Null

$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    & python -I scripts\gen_patchtable.py installer\PatchTable.cs $Version
    if ($LASTEXITCODE) { throw "patch table generation failed" }
} else {
    "python not found: using the committed installer\PatchTable.cs"
}

$exe = "build\HW1ClassicFix-Setup.exe"
& $csc /nologo /target:winexe /platform:anycpu /optimize+ /warn:3 `
    /win32manifest:installer\app.manifest `
    /r:System.dll /r:System.Core.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll `
    /out:$exe installer\Program.cs installer\PatchTable.cs
if ($LASTEXITCODE) { throw "compile failed" }
"built $exe ($((Get-Item $exe).Length) bytes)  sha256 $((Get-FileHash $exe -Algorithm SHA256).Hash.ToLower())"

if (-not $OriginalExe) {
    $candidate = "_extract\exe\Homeworld-2.303-20231108.exe"
    if (Test-Path $candidate) { $OriginalExe = $candidate }
}
if (-not $SkipTests -and $OriginalExe -and (Test-Path $OriginalExe)) {
    $OriginalSha = "421c114e832c56bd1994fe97c342969ef69881bb74399e67bef979c6923df381"
    if ((Get-FileHash $OriginalExe -Algorithm SHA256).Hash.ToLower() -ne $OriginalSha) {
        throw "$OriginalExe is not the unmodified 2023 build (sha256 $OriginalSha)"
    }
    # throwaway copy laid out like the real install
    $work = Join-Path $env:TEMP "hw1fix-selftest"
    $t = Join-Path $work "Homeworld\Homeworld1Classic\exe"
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $t | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $work "Homeworld\Homeworld1Classic\Data") | Out-Null
    Copy-Item $OriginalExe (Join-Path $t "Homeworld.exe")
    $gameRoot = Join-Path $work "Homeworld"
    $log = Join-Path $work "cli.log"
    function Run($argv) {
        $p = Start-Process -FilePath (Resolve-Path $exe) -ArgumentList $argv -Wait -PassThru -NoNewWindow -RedirectStandardOutput $log
        $o = Get-Content $log -Raw
        Write-Host ("  [" + $p.ExitCode + "] " + ($argv -join ' '))
        $o -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Write-Host ("      " + $_.TrimEnd()) }
        return $p.ExitCode
    }
    "self-test:"
    if ((Run @("--check", "`"$gameRoot`"")) -ne 0) { throw "check failed on the original" }
    if ((Run @("--install", "`"$gameRoot\Homeworld1Classic\Data`"")) -ne 0) { throw "install via a subfolder failed" }
    if ((Run @("--install", "`"$gameRoot`"")) -ne 0) { throw "second install (idempotent) failed" }
    $patched = (Get-FileHash (Join-Path $t "Homeworld.exe") -Algorithm SHA256).Hash.ToLower()
    # cross-check against the Python patcher when available
    if ($py) {
        $ref = Join-Path $work "ref.exe"
        & python -I scripts\dockfix_patch.py apply $OriginalExe $ref --full --video | Out-Null
        $want = (Get-FileHash $ref -Algorithm SHA256).Hash.ToLower()
        if ($patched -ne $want) { throw "installer output $patched differs from the Python patcher $want" }
        "  installer output matches the Python patcher ($($patched.Substring(0,8))...)"
    } else {
        "  installed exe sha256 $patched"
    }
    if (-not (Test-Path (Join-Path $t "Homeworld.exe.orig-2.303"))) { throw "backup missing" }
    if ((Run @("--remove", "`"$t`"")) -ne 0) { throw "remove failed" }
    if ((Get-FileHash (Join-Path $t "Homeworld.exe") -Algorithm SHA256).Hash.ToLower() -ne $OriginalSha) { throw "remove did not restore the original" }
    "  remove restored the original"
    if ((Run @("--check", "`"$env:TEMP`"")) -eq 0) { throw "check should fail on a folder without the game" }
    "  wrong folder rejected"
    Remove-Item $work -Recurse -Force
} elseif (-not $SkipTests) {
    "self-test skipped: no unmodified 2023 Homeworld.exe given (-OriginalExe <path>)"
}

if ($StageDir) {
    $stage = Join-Path $StageDir "HW1ClassicFix-$Version"
    New-Item -ItemType Directory -Force $stage | Out-Null
    Copy-Item $exe $stage -Force
    Copy-Item installer\README.txt $stage -Force
    $zip = Join-Path $StageDir "HW1ClassicFix-$Version.zip"
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path "$stage\*" -DestinationPath $zip
    "staged: $stage"
    "zip:    $zip  sha256 $((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower())"
}
