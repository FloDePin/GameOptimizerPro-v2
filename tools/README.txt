GameOptimizerPro — tools/ folder
================================

Put optional external helper binaries here.

PresentMon (for the Diagnose tab → live FPS/Frametime capture)
--------------------------------------------------------------
GameOptimizerPro does NOT bundle PresentMon (it is a separate open-source
tool by Intel, MIT-licensed). To enable *live* FPS capture:

  1. Download PresentMon from:
       https://github.com/GameTechDev/PresentMon/releases
  2. Drop the executable (e.g. PresentMon.exe or PresentMon-x64.exe) into
       this  tools/  folder.
  3. Restart GameOptimizerPro → Diagnose tab → "Live-Capture".

Without PresentMon you can still use the Diagnose tab's "CSV analysieren"
button to analyze any PresentMon / CapFrameX / OCAT frametime CSV you already
have — that path needs no external binary.

Nothing here is required for the rest of the app.
