@echo off
rem Double-click to CLOSE the canvas server (default port 8766).
rem Only kills the python process holding that port. Never touches ComfyUI (8188).
rem All real logic lives in tools\stop_canvas.py
rem This window closes by itself; no key press needed.
cd /d "%~dp0"

set "COMFY_ROOT="
if exist "%~dp0comfy-root.txt" for /f "usebackq delims=" %%i in ("%~dp0comfy-root.txt") do set "COMFY_ROOT=%%i"
if defined COMFY_ROOT if exist "%COMFY_ROOT%\python\python.exe" (
  "%COMFY_ROOT%\python\python.exe" tools\stop_canvas.py %*
  goto check
)
if exist "..\python\python.exe" (
  "..\python\python.exe" tools\stop_canvas.py %*
  goto check
)
if exist "..\..\python\python.exe" (
  "..\..\python\python.exe" tools\stop_canvas.py %*
  goto check
)
where python >nul 2>nul
if not errorlevel 1 (
  python tools\stop_canvas.py %*
  goto check
)

echo Python not found, cannot stop the canvas.
echo Put your ComfyUI folder path in comfy-root.txt next to this file.
timeout /t 15 >nul
exit /b 1

:check
exit /b %errorlevel%
