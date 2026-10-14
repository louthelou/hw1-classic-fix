Homeworld 1 Classic Fix 1.0.0
=============================
For Homeworld Remastered Collection (Steam or GOG), Homeworld 1 Classic, 2023 game build.

What it does
------------
- Fighters and corvettes dock with the Kushan Mothership again instead of circling it forever
  (a bug introduced by the July 2023 update).
- The Video options list every resolution your display supports, sorted by colour depth,
  height and width, instead of five 4:3 modes.
- The move order's destination disc follows the cursor at any aspect ratio, including after
  changing resolution in-game.
- The game keeps its settings on Windows 10 and 11 without any compatibility mode, and starts
  at your desktop size the first time.
- 32-bit colour by default, plus a few smaller flight and camera fixes from the same bug.

Install
-------
1. Close the game and its launcher.
2. Run HW1ClassicFix-Setup.exe. Windows may show a "Windows protected your PC" prompt because
   the installer is not code-signed: choose "More info", then "Run anyway".
3. The installer finds your Homeworld Remastered Collection folder (Steam and GOG). If it does
   not, or it picked the wrong copy, click Browse... and select the collection folder (it
   contains "Homeworld1Classic") or any folder inside it.
4. Click "Install fix". Your original Homeworld.exe is kept next to the patched one as
   Homeworld.exe.orig-2.303.
5. Start the game normally. Pick your resolution under Options > Video.

Remove
------
Run the installer again and click "Remove fix", or copy Homeworld.exe.orig-2.303 back over
Homeworld.exe in Homeworld1Classic\exe.

Notes
-----
- Steam's "Verify integrity of game files" restores the unpatched exe. Just run the installer
  again afterwards.
- Compatibility modes (Windows 7 etc.) are no longer needed for Homeworld 1 Classic and can be
  turned off in the exe's Properties.
- Your settings now live under HKEY_CURRENT_USER\SOFTWARE\Sierra On-Line\Homeworld. The
  installer copies any earlier settings there the first time.
- The fix changes only the game executable, in place, after checking every byte it touches.
  It refuses to install over a different build or over another patch that changed the same
  bytes. Game data files are untouched, so data mods keep working.
- UI scaling is not part of this fix; at very high resolutions the text is small. Choosing a
  lower resolution with the same aspect ratio is the usual remedy.

The installer and patch tools are released under the MIT License. Homeworld is the property
of Gearbox Software; no game files are distributed.
