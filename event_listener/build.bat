@echo off

set "LUA_DIR=.\lua-5.1.5_Win64_dll17_lib"

echo "> Compiling minisocket.dll"
gcc -shared -o minisocket.dll minisocket.c -I"%LUA_DIR%\include" -lws2_32 -O2

pause