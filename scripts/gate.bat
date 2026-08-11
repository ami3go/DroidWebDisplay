@echo off
setlocal
set ROOT=%~dp0..
python "%ROOT%\tools\release_gate.py" --output "%ROOT%\evidence\release\gate.json" %*
