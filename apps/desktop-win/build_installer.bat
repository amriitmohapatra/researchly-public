@echo off
REM Build the STANDALONE Researchly installer for Windows — every
REM dependency inside the artifact: Python runtime + engine + spaCy model
REM (PyInstaller), LanguageTool pre-downloaded, and a trimmed private JRE
REM (jlink). An installed app needs NO Python, NO Java, NO first-run
REM download.
REM
REM   build_installer.bat            →  Output\Researchly-Setup-0.8.exe
REM   build_installer.bat --skip-jre    (grammar tier then needs system Java)
REM   build_installer.bat --skip-lt     (LanguageTool downloads on first use)
REM
REM Prereqs on the BUILD machine (end users need none of these):
REM   pip install -r ..\..\packages\core\requirements.txt -r requirements-win.txt pyinstaller
REM   python -m spacy download en_core_web_sm
REM   a JDK 17+  (Adoptium/Temurin MSI is fine; needed for jlink + the JRE)
REM   Inno Setup 6  (https://jrsoftware.org/isinfo.php — for the Setup.exe)
REM
REM NOTE: like everything in desktop-win, this awaits its first run on real
REM Windows hardware — docs/windows-smoke-checklist.md section 6 covers it.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set SKIP_JRE=0
set SKIP_LT=0
for %%A in (%*) do (
  if "%%A"=="--skip-jre" set SKIP_JRE=1
  if "%%A"=="--skip-lt" set SKIP_LT=1
)

REM --- prereqs ---------------------------------------------------------------
python -c "import PyInstaller" >NUL 2>&1 || (
  echo error: PyInstaller missing.  pip install pyinstaller & exit /b 1)
python -c "import spacy, en_core_web_sm, symspellpy, language_tool_python" >NUL 2>&1 || (
  echo error: engine deps missing.
  echo   pip install -r ..\..\packages\core\requirements.txt -r requirements-win.txt
  echo   python -m spacy download en_core_web_sm
  exit /b 1)

REM --- vendor\ : bundled third-party runtimes --------------------------------
echo ==^> preparing vendor\ (bundled dependencies)
if exist vendor rmdir /s /q vendor
mkdir vendor

if "%SKIP_LT%"=="0" (
  echo     LanguageTool: fetching into vendor\ ^(reuses %%USERPROFILE%%\.cache if present^)
  set "LTP_PATH=%CD%\vendor"
  python -c "import os, shutil, glob; cached = sorted(glob.glob(os.path.expanduser('~/.cache/language_tool_python/LanguageTool*'))); cached and shutil.copytree(cached[-1], os.path.join('vendor', os.path.basename(cached[-1]))) or __import__('language_tool_python.download_lt', fromlist=['download_lt']).download_lt()" || exit /b 1
  set "LTP_PATH="
  dir /b vendor\LanguageTool* >NUL 2>&1 || (
    echo error: LanguageTool did not land in vendor\ & exit /b 1)
)

if "%SKIP_JRE%"=="0" (
  echo     JRE: jlink from the build machine's JDK
  for /f "delims=" %%J in ('python -c "import sys; sys.path.insert(0,'../../packages/core'); from researchly.health import find_java; print(find_java() or '')"') do set "JAVA_BIN=%%J"
  if "!JAVA_BIN!"=="" (
    echo error: no JDK 17+ found. Install Adoptium Temurin 17+ or rerun with --skip-jre
    exit /b 1)
  for %%D in ("!JAVA_BIN!") do set "JAVA_DIR=%%~dpD"
  if not exist "!JAVA_DIR!jlink.exe" (
    echo error: !JAVA_DIR!jlink.exe not found — that Java is a JRE, not a JDK.
    exit /b 1)
  REM jdk.httpserver is REQUIRED (LanguageTool's server uses
  REM com.sun.net.httpserver, which java.se does not include).
  "!JAVA_DIR!jlink.exe" --add-modules java.se,jdk.httpserver,jdk.unsupported ^
      --strip-debug --no-man-pages --no-header-files --compress=2 ^
      --output vendor\jre || exit /b 1
  vendor\jre\bin\java.exe -version || (
    echo error: bundled JRE does not run & exit /b 1)
)

REM --- the app (PyInstaller, onedir) ----------------------------------------
echo ==^> building dist\Researchly (PyInstaller)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --noconfirm --onedir --windowed --name Researchly ^
  --collect-all spacy --collect-all en_core_web_sm ^
  --collect-all symspellpy --collect-all thinc ^
  --collect-all language_tool_python ^
  --collect-all certifi ^
  --hidden-import requests --hidden-import charset_normalizer ^
  --add-data "..\..\packages\core\researchly;researchly" ^
  --add-data "..\desktop-mac\panel_html.py;." ^
  --add-data "vendor;vendor" ^
  researchly_win.py || exit /b 1

REM --- verification (test the artifact, not the intent) ----------------------
echo ==^> verifying the bundle
set FAIL=0
if not exist dist\Researchly\Researchly.exe (
  echo     MISSING: Researchly.exe & set FAIL=1)
set "VDIR=dist\Researchly\_internal\vendor"
if not exist "!VDIR!" set "VDIR=dist\Researchly\vendor"
if not exist "!VDIR!" (
  echo     MISSING: vendor\ inside the bundle & set FAIL=1)
if "%SKIP_JRE%"=="0" if exist "!VDIR!" (
  "!VDIR!\jre\bin\java.exe" -version >NUL 2>&1 || (
    echo     BROKEN: bundled JRE does not run & set FAIL=1))
if "%SKIP_LT%"=="0" if exist "!VDIR!" (
  dir /b "!VDIR!\LanguageTool*" >NUL 2>&1 || (
    echo     MISSING: bundled LanguageTool & set FAIL=1))
if "%FAIL%"=="1" (echo error: bundle verification failed & exit /b 1)

REM --- the installer (Inno Setup) -------------------------------------------
set "ISCC=iscc"
where iscc >NUL 2>&1 || set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" where iscc >NUL 2>&1 || (
  echo error: Inno Setup not found. Install from jrsoftware.org, or take
  echo        dist\Researchly\ as a portable folder build.
  exit /b 1)
echo ==^> building the Setup.exe (Inno Setup)
"%ISCC%" installer.iss || exit /b 1

echo.
echo Done:  Output\Researchly-Setup-0.8.exe
echo   - per-user install, no admin needed
echo   - end users need no Python, no Java, no downloads
echo   - unsigned: SmartScreen will warn once ("More info" -^> "Run anyway")
endlocal
