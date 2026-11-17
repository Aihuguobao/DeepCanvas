@echo off
rem Double-click to RESTART the canvas: stop the running server, then start it again.
rem Only the canvas port (8766) is touched; ComfyUI (8188) is never touched.
setlocal
cd /d "%~dp0"
set "PORT=8766"

set "COMFY_ROOT="
if exist "%~dp0comfy-root.txt" for /f "usebackq delims=" %%i in ("%~dp0comfy-root.txt") do set "COMFY_ROOT=%%i"
set "PYW="
if defined COMFY_ROOT if exist "%COMFY_ROOT%\python\pythonw.exe" set "PYW=%COMFY_ROOT%\python\pythonw.exe"
if not defined PYW if exist "..\python\pythonw.exe" set "PYW=..\python\pythonw.exe"
if not defined PYW if exist "..\..\python\pythonw.exe" set "PYW=..\..\python\pythonw.exe"
if not defined PYW (
  where pythonw >nul 2>nul
  if not errorlevel 1 set "PYW=pythonw"
)

echo [1/3] stopping the canvas on port %PORT% ...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" >nul 2>nul
timeout /t 1 >nul

echo [2/3] starting the canvas ...
if defined PYW (
  start "" "%PYW%" tools\launch_canvas.py --no-browser
  goto done
)
echo.
echo [ERROR] Python not found. Put your ComfyUI folder path in comfy-root.txt,
echo or run the dependency installer first.
echo This window closes in 20 seconds.
timeout /t 20 >nul
exit /b 1

:done
echo [3/3] done. Refresh the page that is already open; no new tab is started.
timeout /t 2 >nul
exit /b 0
