@echo off


set "LUA_DIR=.\lua-5.1.5_Win64_dll17_lib"

echo.
echo "> Generating lua import library"
gendef "%LUA_DIR%\lua51.dll"
dlltool -D "%LUA_DIR%\lua51.dll" -d lua51.def -l liblua51.a

echo.
echo "> Compiling minisocket.dll"
gcc -shared -o minisocket.dll minisocket.c -I"%LUA_DIR%\include" -L. -llua51 -lws2_32 -O2

del lua51.def 
del liblua51.a

pause