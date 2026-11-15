@echo off
rem ==========================================================================
rem  One-click dependency setup for the canvas.
rem
rem  1) finds a Python interpreter (portable ..\python, PATH python, py launcher)
rem  2) if none, downloads the official installer and installs it per-user
rem     (no admin rights needed, PATH is updated, pip is included)
rem  3) runs tools\setup_deps.py which pip-installs requirements.txt
rem
rem  This file is pure ASCII on purpose: cmd parses .bat as GBK, and any
rem  non-ASCII byte can corrupt the following lines (hit twice already).
rem ==========================================================================
cd /d "%~dp0"
title Canvas dependency setup

echo ==========================================================
echo  Canvas dependency setup
echo  work dir : %CD%
echo ==========================================================
echo.

set "PY="
if exist "..\python\python.exe" set "PY=..\python\python.exe"
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if defined PY goto :have_python

echo [1/3] Python not found. Downloading the official installer...
set "INST=%TEMP%\python-3.12.10-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-amd64.exe'; $f='%INST%'; try { (New-Object Net.WebClient).DownloadFile($u,$f) } catch { try { (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe',$f) } catch { exit 1 } }"
if not exist "%INST%" (
  echo.
  echo [ERROR] Could not download Python.
  echo   Install Python 3.10+ by hand from https://www.python.org/downloads/
  echo   Tick "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)

echo [2/3] Installing Python for the current user (no admin needed)...
echo        This may take 1-3 minutes, please wait...
start /wait "" "%INST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
del "%INST%" >nul 2>nul

set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
  )
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo.
  echo [ERROR] Python was installed but cannot be found yet.
  echo   Close this window, open it again, and run this file once more.
  pause
  exit /b 1
)

:have_python
echo [3/3] Installing canvas packages with: %PY%
echo.
%PY% "tools\setup_deps.py"
set "RC=%ERRORLEVEL%"
echo.
echo ----------------------------------------------------------
if "%RC%"=="0" (
  echo  Done. Now double-click the canvas launcher in this folder.
) else (
  echo  Finished with errors ^(exit code %RC%^). Read the messages
  echo  above, fix the problem, then run this file again.
)
echo ----------------------------------------------------------
echo.
pause
exit /b %RC%
