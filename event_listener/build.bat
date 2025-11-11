@echo off

cargo +nightly build --release --target x86_64-pc-windows-msvc
copy target\x86_64-pc-windows-msvc\release\hkb_event_listener.dll .\
pause