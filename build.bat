@echo off
CALL "%userprofile%\miniforge3\Scripts\activate.bat"
CALL conda activate hkbeditor

REM "=== RUNNING PYINSTALLER ==="
IF EXIST dist RMDIR /S /Q dist
pyinstaller main.py --onefile

REM "=== COPYING ADDITIONAL FILES ==="
REN dist\main.exe hkbeditor.exe
COPY LICENSE dist\
COPY README.md dist\
COPY user_layout.ini dist\default_layout.ini
ROBOCOPY templates dist\templates /E