@echo off
REM Build Researchly.exe (UNTESTED scaffold - expect a debugging session).
REM Run from this folder:  build_win.bat
pyinstaller --noconfirm --onedir --windowed --name Researchly ^
  --collect-all spacy --collect-all en_core_web_sm ^
  --collect-all symspellpy --collect-all thinc ^
  --add-data "..\..\packages\core\researchly;researchly" ^
  --add-data "..\desktop-mac\panel_html.py;." ^
  researchly_win.py
echo Built: dist\Researchly\Researchly.exe
