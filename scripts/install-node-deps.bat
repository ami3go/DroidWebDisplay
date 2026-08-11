@echo off
setlocal
set ROOT=%~dp0..
pushd "%ROOT%\packages\scrcpy-protocol"
call npm.cmd ci --ignore-scripts || exit /b 1
popd
pushd "%ROOT%\apps\web-client"
call npm.cmd ci --ignore-scripts || exit /b 1
popd
echo Package-local Node.js dependencies installed.
endlocal
