@echo off
rem Double-click to open the canvas (no console window).
rem All real logic lives in tools\launch_canvas.py
rem Pass-through args:  this-file --port 8770   or   set CANVAS_PORT=8770
rem
rem ---- which python ----
rem The canvas does not ship a python. It normally lives inside the ComfyUI
rem package (ComfyUI-aki-v3\python\python.exe), so we look there first:
rem   1. COMFY_ROOT env var, or comfy-root.txt next to this file (ComfyUI root)
rem   2. ..\python and ..\..\python   (canvas placed inside the package)
rem   3. pythonw / python / py on PATH
cd /d "%~dp0"

set "COMFY_ROOT="
if exist "%~dp0comfy-root.txt" for /f "usebackq delims=" %%i in ("%~dp0comfy-root.txt") do set "COMFY_ROOT=%%i"
if defined COMFY_ROOT if exist "%COMFY_ROOT%\python\pythonw.exe" (
  start "" "%COMFY_ROOT%\python\pythonw.exe" tools\launch_canvas.py %*
  exit /b 0
)
if exist "..\python\pythonw.exe" (
  start "" "..\python\pythonw.exe" tools\launch_canvas.py %*
  exit /b 0
)
if exist "..\..\python\pythonw.exe" (
  start "" "..\..\python\pythonw.exe" tools\launch_canvas.py %*
  exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw tools\launch_canvas.py %*
  exit /b 0
)

if defined COMFY_ROOT if exist "%COMFY_ROOT%\python\python.exe" (
  start "" "%COMFY_ROOT%\python\python.exe" tools\launch_canvas.py %*
  exit /b 0
)
if exist "..\python\python.exe" (
  start "" "..\python\python.exe" tools\launch_canvas.py %*
  exit /b 0
)
if exist "..\..\python\python.exe" (
  start "" "..\..\python\python.exe" tools\launch_canvas.py %*
  exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 (
  start "" python tools\launch_canvas.py %*
  exit /b 0
)
where py >nul 2>nul
if not errorlevel 1 (
  start "" py tools\launch_canvas.py %*
  exit /b 0
)

echo Python not found.
echo Put your ComfyUI folder path in comfy-root.txt next to this file,
echo or install Python 3.10+ and run the dependency installer first.
echo This window closes in 20 seconds.
timeout /t 20 >nul
exit /b 1
