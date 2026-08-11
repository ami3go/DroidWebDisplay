@echo off
setlocal
set ROOT=%~dp0..
python "%ROOT%\tools\run_bridge_service.py" --repo-root "%ROOT%" --open-browser %*
