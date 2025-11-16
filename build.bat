@echo off
CALL "%userprofile%\miniforge3\Scripts\activate.bat"
CALL conda activate hkbeditor

REM "=== RUNNING PYINSTALLER ==="
IF EXIST dist RMDIR /S /Q dist
pyinstaller main.py --onefile --icon=icon.ico

REM "=== COPYING ADDITIONAL FILES ==="
REN dist\main.exe hkbeditor.exe
COPY LICENSE dist\
COPY README.md dist\
COPY user_layout.ini dist\default_layout.ini
COPY attributes.yaml dist\
COPY icon.ico dist\
ROBOCOPY templates dist\templates /E
ROBOCOPY doc dist\doc /E
ROBOCOPY event_listener dist\event_listener hkb_event_listener.dll hkb_event_listener.yaml