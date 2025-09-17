@echo off
CALL "%userprofile%\miniforge3\Scripts\activate.bat"
CALL conda activate hkbeditor

REM "=== RUNNING PYINSTALLER ==="
IF EXIST dist RMDIR /S /Q dist
pyinstaller main.py --onefile --icon=icon_small.ico

REM "=== COPYING ADDITIONAL FILES ==="
REN dist\main.exe hkbeditor.exe
COPY LICENSE dist\
COPY README.md dist\
COPY user_layout.ini dist\default_layout.ini
COPY attributes.yaml dist\
COPY icon_small.ico dist\
COPY icon_large.png dist\
ROBOCOPY templates dist\templates /E